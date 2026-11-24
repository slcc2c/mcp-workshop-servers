"""Unit tests for LaunchAgent watchdog threshold/cooldown and ~/.zshrc token hook."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_stack.client_configs import install_shell_hook
from mcp_stack.watchdog import run_watchdog_once


def test_watchdog_two_failure_threshold_cooldown_and_recovery(
    make_settings, tmp_path: Path
) -> None:
    settings = make_settings()
    state_path = tmp_path / "state/watchdog-state.json"
    log_path = tmp_path / "logs/watchdog.log"
    now = 1000.0
    recoveries: list[str] = []

    def unhealthy_uc(_settings):
        return {
            "unity_catalog": {"healthy": False, "detail": "down"},
            "mlflow_mcp": {"healthy": True, "detail": ""},
            "gateway": {"healthy": True, "detail": ""},
        }

    def healthy_all(_settings):
        return {
            "unity_catalog": {"healthy": True, "detail": ""},
            "mlflow_mcp": {"healthy": True, "detail": ""},
            "gateway": {"healthy": True, "detail": ""},
        }

    def fake_recover(comp: str):
        recoveries.append(comp)
        return {"command": comp, "ok": True, "detail": ""}

    # 1st failure -> pending threshold, no restart yet
    r1 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        recover_fn=fake_recover,
        clock=lambda: now,
    )
    assert r1["actions"]["unity_catalog"] == "degraded_pending_threshold"
    assert recoveries == []

    # 2nd consecutive failure -> triggers recovery
    now += 60.0
    r2 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        recover_fn=fake_recover,
        clock=lambda: now,
    )
    assert r2["actions"]["unity_catalog"] == "restarted"
    assert recoveries == ["unity_catalog"]

    # 3rd failure inside 180s cooldown -> blocked by cooldown
    now += 60.0
    r3 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        recover_fn=fake_recover,
        clock=lambda: now,
    )
    assert r3["actions"]["unity_catalog"] == "cooldown_active"
    assert recoveries == ["unity_catalog"]

    # Healthy probe resets consecutive_failures and logs recovery
    now += 60.0
    r4 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=healthy_all,
        recover_fn=fake_recover,
        clock=lambda: now,
    )
    assert r4["actions"]["unity_catalog"] == "recovered"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["components"]["unity_catalog"]["consecutive_failures"] == 0
    assert log_path.exists()


def test_install_shell_hook_idempotent_with_backup(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    rc.write_text('export PATH="$HOME/bin:$PATH"\n', encoding="utf-8")

    first = install_shell_hook(tmp_path, shell_rc=rc)
    assert first["status"] == "appended"
    assert first["backup"] and Path(first["backup"]).exists()
    content1 = rc.read_text(encoding="utf-8")
    assert content1.count("# >>> mcp-workshop-stack tokens >>>") == 1
    assert "load_mcp_tokens.sh" in content1

    second = install_shell_hook(tmp_path, shell_rc=rc)
    assert second["status"] == "updated"
    content2 = rc.read_text(encoding="utf-8")
    assert content2.count("# >>> mcp-workshop-stack tokens >>>") == 1
    assert 'export PATH="$HOME/bin:$PATH"' in content2
