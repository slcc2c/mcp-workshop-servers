"""Unit tests for LaunchAgent watchdog threshold/cooldown and ~/.zshrc token hook."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from mcp_stack.client_configs import install_shell_hook
from mcp_stack.watchdog import (
    _default_eval_regression_probe,
    _default_probe,
    _default_recover,
    run_watchdog_once,
)


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


def test_watchdog_eval_regression_detection_and_fail_open(
    make_settings, tmp_path: Path, monkeypatch
) -> None:
    settings = make_settings()
    state_path = tmp_path / "state/watchdog-state.json"
    log_path = tmp_path / "logs/watchdog.log"
    recoveries: list[str] = []

    def healthy_all(_settings):
        return {
            "unity_catalog": {"healthy": True, "detail": ""},
            "mlflow_mcp": {"healthy": True, "detail": ""},
            "gateway": {"healthy": True, "detail": ""},
        }

    # Regression triggers log entry without restarting services
    res_reg = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=healthy_all,
        recover_fn=lambda comp: recoveries.append(comp) or {"ok": True},
        eval_probe_fn=lambda _s: {
            "status": "regression",
            "threshold": 1.0,
            "run_id": "run-reg-1",
            "min_score": 0.6,
            "failing_metrics": {"tool_execution_success/mean": 0.6},
        },
    )
    assert res_reg["overall"] == "healthy"
    assert res_reg["eval_regression"]["status"] == "regression"
    assert "drift" in res_reg
    assert res_reg["drift"]["status"] in {"ok", "drift_detected", "unavailable"}
    assert recoveries == []
    assert log_path.exists()

    # Probe exception fails open cleanly
    res_err = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=healthy_all,
        eval_probe_fn=lambda _s: (_ for _ in ()).throw(RuntimeError("mlflow down")),
    )
    assert res_err["eval_regression"]["status"] == "unavailable"

    # REST _default_eval_regression_probe detects regression from mocked MLflow responses
    class FakeHttpxClient:
        def __init__(self, timeout: float = 2.0) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url: str, params=None):
            assert "get-by-name" in url
            return httpx.Response(200, json={"experiment": {"experiment_id": "52"}})

        def post(self, url: str, json=None):
            assert "runs/search" in url
            return httpx.Response(
                200,
                json={
                    "runs": [
                        {
                            "info": {"run_id": "run-bad", "run_name": "eval-1", "start_time": 123},
                            "data": {
                                "metrics": [
                                    {"key": "tool_execution_success/mean", "value": 0.5},
                                    {"key": "tool_latency_sla/mean", "value": 1.0},
                                ]
                            },
                        }
                    ]
                },
            )

    monkeypatch.setattr(httpx, "Client", FakeHttpxClient)
    probed = _default_eval_regression_probe(settings)
    assert probed["status"] == "regression"
    assert probed["min_score"] == 0.5
    assert probed["failing_metrics"] == {"tool_execution_success/mean": 0.5}


def test_default_probe_decouples_gateway_health_from_ready_status(
    make_settings, monkeypatch
) -> None:
    import mcp_stack.watchdog as wd

    settings = make_settings()
    settings.unity_catalog.base_url = "http://100.85.39.109:8082"

    loaded_state = {"loaded": True, "state": "running", "pid": 1234}
    monkeypatch.setattr(wd, "_launchctl_info", lambda _uid, _label: dict(loaded_state))

    async def fake_probe_mcp(_url: str, timeout: float = 2.5):
        return {"reachable": True}

    monkeypatch.setattr(wd, "probe_mcp_http_endpoint", fake_probe_mcp)

    health_payload = {"status": "healthy"}
    health_code = 200
    ready_payload = {"status": "degraded"}

    def fake_get(url: str, params=None, timeout: float = 2.5):
        if url.endswith("/health"):
            return httpx.Response(health_code, json=health_payload)
        if url.endswith("/ready"):
            return httpx.Response(200, json=ready_payload)
        return httpx.Response(200, json={"catalogs": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    res = _default_probe(settings)
    assert res["gateway"]["healthy"] is True
    assert res["gateway"]["ready_status"] == "degraded"

    # Real /health failure or unloaded launchd marks gateway unhealthy
    health_code = 503
    health_payload = {"status": "unhealthy"}
    res_fail = _default_probe(settings)
    assert res_fail["gateway"]["healthy"] is False

    health_code = 200
    health_payload = {"status": "healthy"}
    loaded_state["loaded"] = False
    res_unloaded = _default_probe(settings)
    assert res_unloaded["gateway"]["healthy"] is False


def test_default_recover_gates_docker_start_to_loopback_urls(
    make_settings, tmp_path: Path, monkeypatch
) -> None:
    import mcp_stack.watchdog as wd

    settings = make_settings()
    settings.unity_catalog.base_url = "http://100.85.39.109:8082"

    docker_calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        docker_calls.append(list(cmd))

        class Proc:
            returncode = 0
            stdout = "mcp-unity-catalog"
            stderr = ""

        return Proc()

    monkeypatch.setattr(wd.subprocess, "run", fake_run)

    remote_rec = _default_recover("unity_catalog", settings=settings)
    assert remote_rec["skipped"] is True
    assert remote_rec["ok"] is False
    assert docker_calls == []

    # Loopback UC triggers local docker start
    settings.unity_catalog.base_url = "http://localhost:8082"
    local_rec = _default_recover("unity_catalog", settings=settings)
    assert local_rec["ok"] is True
    assert docker_calls == [["docker", "start", "mcp-unity-catalog"]]

    # run_watchdog_once records remote_unhealthy and respects cooldown when skipped
    settings.unity_catalog.base_url = "http://100.85.39.109:8082"
    state_path = tmp_path / "state/watchdog.json"
    log_path = tmp_path / "logs/watchdog.log"
    now = 2000.0

    def unhealthy_uc(_s):
        return {
            "unity_catalog": {"healthy": False, "detail": "timeout"},
            "mlflow_mcp": {"healthy": True, "detail": ""},
            "gateway": {"healthy": True, "detail": "", "ready_status": "degraded"},
        }

    run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        clock=lambda: now,
    )
    now += 60.0
    r2 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        clock=lambda: now,
    )
    assert r2["actions"]["unity_catalog"] == "remote_unhealthy"
    assert r2["components"]["gateway"]["ready_status"] == "degraded"
    assert docker_calls == [["docker", "start", "mcp-unity-catalog"]]

    now += 60.0
    r3 = run_watchdog_once(
        settings,
        state_path=state_path,
        log_path=log_path,
        probe_fn=unhealthy_uc,
        clock=lambda: now,
    )
    assert r3["actions"]["unity_catalog"] == "cooldown_active"
