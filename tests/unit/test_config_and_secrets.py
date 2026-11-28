"""Unit tests for Pydantic configuration and 1Password/env SecretResolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_stack.core.config import GatewaySettings, SecretsSettings, load_settings
from mcp_stack.core.secrets import (
    CommandResult,
    SecretAccessDeniedError,
    SecretNotFoundError,
    SecretResolver,
)

pytestmark = pytest.mark.unit


def test_gateway_auth_auto_enforced_on_non_loopback() -> None:
    loopback = GatewaySettings(host="127.0.0.1", auth_enabled=False)
    assert loopback.is_loopback is True
    assert loopback.effective_auth_enabled is False

    non_loopback = GatewaySettings(host="0.0.0.0", auth_enabled=False)
    assert non_loopback.is_loopback is False
    assert non_loopback.effective_auth_enabled is True

    explicit_override = GatewaySettings(
        host="0.0.0.0", auth_enabled=False, allow_unauthenticated_non_loopback=True
    )
    assert explicit_override.effective_auth_enabled is False


def test_load_settings_with_yaml_and_env_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "services.yaml"
    cfg.write_text(
        "gateway:\n  port: 9999\nmlflow:\n  experiment_name: yaml-exp\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "env-exp")
    monkeypatch.setenv("UC_FUNCTION_ALLOWLIST", "prod.ml, analytics.tools")

    settings = load_settings(config_file=cfg, load_dotenv=False)
    assert settings.gateway.port == 9999
    assert settings.mlflow.experiment_name == "env-exp"
    assert settings.unity_catalog.function_allowlist == ["prod.ml", "analytics.tools"]
    assert settings.effective_mlflow_registry_uri == "uc:http://localhost:8080"


def test_secret_resolver_literal_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = SecretResolver(SecretsSettings())
    assert resolver.resolve("plain-secret") == "plain-secret"
    assert resolver.resolve("   ") is None

    monkeypatch.setenv("MY_TEST_SECRET", "from-env")
    assert resolver.resolve("env:MY_TEST_SECRET") == "from-env"

    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(SecretNotFoundError):
        resolver.resolve("env:MISSING_VAR")


def test_secret_resolver_1password_vault_allowlist_and_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    now = 100.0
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "ops_test_token")

    def fake_runner(args: list[str]) -> CommandResult:
        calls.append(args)
        return CommandResult(returncode=0, stdout="op-secret-val\n", stderr="")

    resolver = SecretResolver(
        SecretsSettings(
            onepassword_enabled=True,
            onepassword_allowed_vaults=["AI"],
            cache_ttl_seconds=300,
        ),
        runner=fake_runner,
        clock=lambda: now,
    )

    # Disallowed vault must fail BEFORE calling op CLI
    with pytest.raises(SecretAccessDeniedError):
        resolver.resolve("op://Personal/GitHub/token")
    assert calls == []

    # Allowed vault invokes [op, read, ref] without shell interpolation
    assert resolver.resolve("op://AI/GitHub/token") == "op-secret-val"
    assert calls == [["op", "read", "op://AI/GitHub/token"]]

    # Cached within TTL
    assert resolver.resolve("op://AI/GitHub/token") == "op-secret-val"
    assert len(calls) == 1

    # Expired after TTL
    now = 500.0
    assert resolver.resolve("op://AI/GitHub/token") == "op-secret-val"
    assert len(calls) == 2


def test_secret_resolver_fails_closed_without_service_account_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)

    def fake_runner(args: list[str]) -> CommandResult:
        calls.append(args)
        return CommandResult(returncode=0, stdout="should-not-run\n", stderr="")

    resolver = SecretResolver(
        SecretsSettings(
            onepassword_enabled=True,
            onepassword_allowed_vaults=["AI"],
        ),
        runner=fake_runner,
    )
    assert resolver.onepassword_mode() == "service-account-missing"
    with pytest.raises(SecretAccessDeniedError) as exc_info:
        resolver.resolve("op://AI/GitHub/token")
    assert exc_info.value.reason_code == "service_account_missing"
    assert calls == []
    diag = resolver.diagnostics()
    assert diag["configuredMode"] == "service-account"
    assert diag["mode"] == "service-account-missing"
    assert diag["lastErrorCode"] == "service_account_missing"


def test_secret_resolver_explicit_desktop_cli_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)

    def fake_runner(args: list[str]) -> CommandResult:
        calls.append(args)
        return CommandResult(returncode=0, stdout="desktop-val\n", stderr="")

    resolver = SecretResolver(
        SecretsSettings(
            onepassword_enabled=True,
            onepassword_mode="desktop-cli",
            onepassword_allowed_vaults=["AI"],
        ),
        runner=fake_runner,
    )
    assert resolver.onepassword_mode() == "desktop-cli"
    assert resolver.resolve("op://AI/GitHub/token") == "desktop-val"
    assert calls == [["op", "read", "op://AI/GitHub/token"]]


def test_load_settings_parses_op_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "services.yaml"
    cfg.write_text("gateway:\n  port: 8090\n", encoding="utf-8")

    monkeypatch.delenv("OP_MODE", raising=False)
    default_settings = load_settings(config_file=cfg, load_dotenv=False)
    assert default_settings.secrets.onepassword_mode == "service-account"

    monkeypatch.setenv("OP_MODE", "desktop-cli")
    desktop_settings = load_settings(config_file=cfg, load_dotenv=False)
    assert desktop_settings.secrets.onepassword_mode == "desktop-cli"

    monkeypatch.setenv("OP_MODE", "bogus")
    with pytest.raises(ValueError, match="Invalid OP_MODE"):
        load_settings(config_file=cfg, load_dotenv=False)
