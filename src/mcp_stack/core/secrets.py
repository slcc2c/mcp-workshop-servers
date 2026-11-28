"""Secret resolution with env:, dual-mode 1Password CLI (op://), and diagnostics."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from mcp_stack.core.config import SecretsSettings


class SecretResolutionError(RuntimeError):
    """Base error for secret resolution failures."""

    def __init__(self, message: str, *, reason_code: str = "error") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class SecretAccessDeniedError(SecretResolutionError):
    """Raised when access to a vault or secret provider is denied."""


class SecretNotFoundError(SecretResolutionError):
    """Raised when a requested secret cannot be found."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str]], CommandResult]


def _sanitized_op_env(*, include_account: bool = True) -> dict[str, str]:
    keys = [
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "OP_SERVICE_ACCOUNT_TOKEN",
        "OP_CONFIG_DIR",
        "XDG_CONFIG_HOME",
    ]
    if include_account:
        keys.append("OP_ACCOUNT")
    env: dict[str, str] = {}
    for key in keys:
        val = os.getenv(key)
        if val:
            env[key] = val
    return env


def _default_runner(args: list[str], *, include_account: bool = False) -> CommandResult:
    try:
        proc = subprocess.run(
            args,
            shell=False,
            env=_sanitized_op_env(include_account=include_account),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    except subprocess.TimeoutExpired:
        return CommandResult(
            returncode=124,
            stdout="",
            stderr="1Password CLI timed out — unlock 1Password or set OP_SERVICE_ACCOUNT_TOKEN",
        )
    except OSError as exc:
        return CommandResult(returncode=127, stdout="", stderr=str(exc))


def _classify_op_error(returncode: int, stderr: str) -> tuple[str, str]:
    clean = " ".join(stderr.strip().splitlines()).strip() or "unknown 1Password CLI error"
    lowered = clean.lower()
    if returncode == 124 or "timed out" in lowered:
        return (
            "timeout",
            "1Password Desktop did not respond within 10s — unlock 1Password or configure "
            "OP_SERVICE_ACCOUNT_TOKEN",
        )
    if returncode == 127 or "no such file" in lowered or "not found" in lowered and "op" in lowered:
        if "isn't an item" in lowered or "vault" in lowered or "secret not found" in lowered:
            return "not_found", clean
        return "cli_missing", clean
    if "not found" in lowered or "isn't an item" in lowered:
        return "not_found", clean
    if (
        "not signed in" in lowered
        or "account is locked" in lowered
        or "biometric" in lowered
        or "session expired" in lowered
    ):
        return (
            "locked",
            "1Password session is locked — unlock 1Password Desktop or set "
            "OP_SERVICE_ACCOUNT_TOKEN",
        )
    if "unauthorized" in lowered or "permission" in lowered or "denied" in lowered:
        return "vault_denied", clean
    return "cli_error", clean


class SecretResolver:
    """Resolve literal secrets, env:VAR references, and op://<vault>/<item>/<field>."""

    def __init__(
        self,
        settings: SecretsSettings,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._custom_runner = runner
        self._runner = runner or _default_runner
        self._clock = clock
        self._cache: dict[str, tuple[str, float]] = {}
        self._last_error: str | None = None
        self._last_error_code: str | None = None
        self._last_success_at: str | None = None

    def onepassword_mode(self) -> str:
        """Return active 1Password mode."""
        if not self._settings.onepassword_enabled:
            return "disabled"
        if os.getenv("OP_SERVICE_ACCOUNT_TOKEN", "").strip():
            return "service-account"
        if self._settings.onepassword_mode == "desktop-cli":
            return "desktop-cli"
        return "service-account-missing"

    def resolve(self, raw: str | SecretStr | None) -> str | None:
        """Resolve a configured secret string synchronously."""
        if raw is None:
            return None
        value = raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)
        value = value.strip()
        if not value:
            return None

        if value.startswith("env:"):
            env_name = value[4:].strip()
            if not env_name:
                raise SecretNotFoundError("Empty env: secret reference", reason_code="not_found")
            resolved = os.getenv(env_name, "").strip()
            if not resolved:
                raise SecretNotFoundError(
                    f"Environment variable '{env_name}' is not set",
                    reason_code="env_missing",
                )
            return resolved

        if value.startswith("op://"):
            return self._resolve_onepassword(value)

        return value

    def _record_error(self, code: str, message: str) -> None:
        self._last_error_code = code
        self._last_error = message[:240]

    def _resolve_onepassword(self, ref: str) -> str:
        if not self._settings.onepassword_enabled:
            msg = "1Password CLI is disabled (set OP_ENABLED=true to enable)"
            self._record_error("provider_disabled", msg)
            raise SecretAccessDeniedError(msg, reason_code="provider_disabled")

        remainder = ref[5:]
        parts = [p for p in remainder.split("/") if p]
        if len(parts) < 3:
            msg = f"Invalid reference '{ref}'; expected op://<vault>/<item>/<field>"
            self._record_error("invalid_ref", msg)
            raise SecretResolutionError(msg, reason_code="invalid_ref")

        vault = parts[0]
        allowed = self._settings.onepassword_allowed_vaults
        if allowed and vault not in allowed:
            msg = f"1Password vault '{vault}' is not in allowed vaults {allowed}"
            self._record_error("vault_denied", msg)
            raise SecretAccessDeniedError(msg, reason_code="vault_denied")

        now = self._clock()
        cached = self._cache.get(ref)
        if cached is not None:
            cached_val, expires_at = cached
            if now < expires_at:
                return cached_val

        mode = self.onepassword_mode()
        if mode == "service-account-missing":
            msg = (
                "OP_SERVICE_ACCOUNT_TOKEN is not set; refusing interactive 1Password Desktop CLI "
                "fallback (use the gateway daemon or set OP_MODE=desktop-cli explicitly)"
            )
            self._record_error("service_account_missing", msg)
            raise SecretAccessDeniedError(msg, reason_code="service_account_missing")

        cmd = [self._settings.onepassword_cli, "read", ref]
        try:
            if self._custom_runner is not None:
                result = self._custom_runner(cmd)
            else:
                result = _default_runner(cmd, include_account=(mode == "desktop-cli"))
        except subprocess.TimeoutExpired as exc:
            code, msg = _classify_op_error(124, str(exc) or "timed out")
            self._record_error(code, msg)
            raise SecretResolutionError(msg, reason_code=code) from exc
        except OSError as exc:
            self._record_error("cli_missing", str(exc))
            raise SecretResolutionError(str(exc), reason_code="cli_missing") from exc

        if result.returncode != 0:
            code, msg = _classify_op_error(result.returncode, result.stderr)
            self._record_error(code, msg)
            if code == "not_found":
                raise SecretNotFoundError(msg, reason_code=code)
            if code in {"locked", "vault_denied"}:
                raise SecretAccessDeniedError(msg, reason_code=code)
            raise SecretResolutionError(msg, reason_code=code)

        resolved = result.stdout.strip()
        if not resolved:
            msg = f"1Password item field '{ref}' is empty"
            self._record_error("empty_value", msg)
            raise SecretNotFoundError(msg, reason_code="empty_value")

        ttl = max(0, self._settings.cache_ttl_seconds)
        if ttl > 0:
            self._cache[ref] = (resolved, now + ttl)
        self._last_error = None
        self._last_error_code = None
        self._last_success_at = datetime.now(UTC).isoformat()
        return resolved

    def clear_cache(self) -> int:
        cleared = len(self._cache)
        self._cache.clear()
        return cleared

    def diagnostics(self) -> dict[str, Any]:
        """Return strictly non-secret telemetry about secret providers."""
        cli_cmd = self._settings.onepassword_cli
        cli_resolved = shutil.which(cli_cmd) if "/" not in cli_cmd else cli_cmd
        cli_available = bool(cli_resolved and os.path.exists(cli_resolved))
        now = self._clock()
        live_cache = sum(1 for _val, exp in self._cache.values() if now < exp)
        return {
            "onepasswordEnabled": self._settings.onepassword_enabled,
            "configuredMode": self._settings.onepassword_mode,
            "mode": self.onepassword_mode(),
            "serviceAccountConfigured": bool(os.getenv("OP_SERVICE_ACCOUNT_TOKEN", "").strip()),
            "cliPath": cli_cmd,
            "cliAvailable": cli_available,
            "allowedVaults": list(self._settings.onepassword_allowed_vaults),
            "cacheEntries": live_cache,
            "cacheTtlSeconds": self._settings.cache_ttl_seconds,
            "lastSuccessAt": self._last_success_at,
            "lastErrorCode": self._last_error_code,
            "lastError": self._last_error,
        }
