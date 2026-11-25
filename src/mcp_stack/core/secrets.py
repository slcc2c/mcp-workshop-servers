"""Secret resolution with env:, optional 1Password CLI (op://), and TTL cache."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import SecretStr

from mcp_stack.core.config import SecretsSettings


class SecretResolutionError(RuntimeError):
    """Base error for secret resolution failures."""


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


def _default_runner(args: list[str]) -> CommandResult:
    proc = subprocess.run(
        args,
        shell=False,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


class SecretResolver:
    """Resolve literal secrets, env:VAR references, and op://<vault>/<item>/<field>."""

    def __init__(
        self,
        settings: SecretsSettings,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._runner = runner or _default_runner
        self._clock = clock
        self._cache: dict[str, tuple[str, float]] = {}

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
                raise SecretNotFoundError("Empty env: secret reference")
            resolved = os.getenv(env_name, "").strip()
            if not resolved:
                raise SecretNotFoundError(f"Environment variable '{env_name}' is not set")
            return resolved

        if value.startswith("op://"):
            return self._resolve_onepassword(value)

        return value

    def _resolve_onepassword(self, ref: str) -> str:
        if not self._settings.onepassword_enabled:
            raise SecretAccessDeniedError(
                "1Password CLI secret resolution is disabled (set OP_ENABLED=true to enable)"
            )

        remainder = ref[5:]
        parts = [p for p in remainder.split("/") if p]
        if len(parts) < 3:
            raise SecretResolutionError(
                f"Invalid 1Password reference '{ref}'; expected op://<vault>/<item>/<field>"
            )

        vault = parts[0]
        allowed = self._settings.onepassword_allowed_vaults
        if allowed and vault not in allowed:
            raise SecretAccessDeniedError(
                f"Access to 1Password vault '{vault}' is denied (allowed: {allowed})"
            )

        now = self._clock()
        cached = self._cache.get(ref)
        if cached is not None:
            cached_val, expires_at = cached
            if now < expires_at:
                return cached_val

        result = self._runner([self._settings.onepassword_cli, "read", ref])
        if result.returncode != 0:
            stderr = result.stderr.strip() or "unknown error"
            lowered = stderr.lower()
            if "not found" in lowered or "isn't an item" in lowered:
                raise SecretNotFoundError(f"1Password secret not found: {ref}")
            if "not signed in" in lowered or "unauthorized" in lowered or "permission" in lowered:
                raise SecretAccessDeniedError(f"1Password access denied for {ref}: {stderr}")
            raise SecretResolutionError(f"1Password CLI failed for {ref}: {stderr}")

        resolved = result.stdout.strip()
        if not resolved:
            raise SecretNotFoundError(f"1Password secret '{ref}' returned empty output")

        ttl = max(0, self._settings.cache_ttl_seconds)
        if ttl > 0:
            self._cache[ref] = (resolved, now + ttl)
        return resolved

    def clear_cache(self) -> None:
        self._cache.clear()
