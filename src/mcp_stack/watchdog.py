"""Lightweight macOS LaunchAgent watchdog with failure threshold and recovery cooldown."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint
from mcp_stack.service import (
    GATEWAY_LABEL,
    LOG_DIR,
    MLFLOW_MCP_LABEL,
    _launchctl_info,
    rotate_log_file,
)

DEFAULT_STATE_PATH = Path.home() / ".local/share/mcp-workshop-stack/watchdog-state.json"
DEFAULT_LOG_PATH = LOG_DIR / "watchdog.log"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"components": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("components"), dict):
            return loaded
    except Exception:
        pass
    return {"components": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_log(log_path: Path, event: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_file(log_path, max_bytes=10 * 1024 * 1024, keep=3)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _default_probe(settings: MCPStackSettings) -> dict[str, dict[str, Any]]:
    uid = os.getuid()
    results: dict[str, dict[str, Any]] = {}

    # 1. Docker OSS Unity Catalog
    uc_ok = False
    uc_detail = ""
    try:
        r = httpx.get(
            f"{settings.unity_catalog.effective_api_base}/catalogs",
            params={"max_results": 1},
            timeout=2.5,
        )
        uc_ok = r.status_code == 200
        if not uc_ok:
            uc_detail = f"HTTP {r.status_code}"
    except Exception as exc:
        uc_detail = str(exc)
    results["unity_catalog"] = {"healthy": uc_ok, "detail": uc_detail}

    # 2. LaunchAgent mlflow[mcp]
    ml_info = _launchctl_info(uid, MLFLOW_MCP_LABEL)
    ml_probe = asyncio.run(probe_mcp_http_endpoint(settings.mlflow.mcp_url, timeout=2.5))
    ml_ok = bool(ml_info.get("loaded")) and bool(ml_probe.get("reachable"))
    results["mlflow_mcp"] = {
        "healthy": ml_ok,
        "detail": "" if ml_ok else f"launchctl={ml_info.get('state')} probe={ml_probe}",
    }

    # 3. LaunchAgent mcp-workshop-gateway
    gw_info = _launchctl_info(uid, GATEWAY_LABEL)
    gw_ok = False
    gw_detail = ""
    try:
        r = httpx.get(
            f"http://{settings.gateway.host}:{settings.gateway.port}/ready",
            timeout=2.5,
        )
        body = r.json()
        gw_ok = (
            bool(gw_info.get("loaded"))
            and r.status_code == 200
            and body.get("status") == "ready"
        )
        if not gw_ok:
            gw_detail = f"launchctl={gw_info.get('state')} ready={body.get('status')}"
    except Exception as exc:
        gw_detail = f"launchctl={gw_info.get('state')} err={exc}"
    results["gateway"] = {"healthy": gw_ok, "detail": gw_detail}

    return results


def _default_recover(component: str) -> dict[str, Any]:
    uid = os.getuid()
    if component == "unity_catalog":
        proc = subprocess.run(
            ["docker", "start", "mcp-unity-catalog"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "command": "docker start mcp-unity-catalog",
            "ok": proc.returncode == 0,
            "detail": (proc.stderr or proc.stdout).strip()[:200],
        }
    label = MLFLOW_MCP_LABEL if component == "mlflow_mcp" else GATEWAY_LABEL
    proc = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": f"launchctl kickstart -k gui/{uid}/{label}",
        "ok": proc.returncode == 0,
        "detail": (proc.stderr or proc.stdout).strip()[:200],
    }


def run_watchdog_once(
    settings: MCPStackSettings,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    failure_threshold: int = 2,
    cooldown_seconds: float = 180.0,
    dry_run: bool = False,
    probe_fn: Callable[[MCPStackSettings], dict[str, dict[str, Any]]] | None = None,
    recover_fn: Callable[[str], dict[str, Any]] | None = None,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Run one watchdog probe + cooldown-guarded recovery pass and persist state."""
    now = clock()
    iso_now = datetime.now(UTC).isoformat()
    state = _load_state(state_path)
    components_state: dict[str, dict[str, Any]] = state.setdefault("components", {})

    probe_impl = probe_fn or _default_probe
    recover_impl = recover_fn or _default_recover
    probes = probe_impl(settings)

    actions: dict[str, str] = {}
    recovery_details: dict[str, Any] = {}
    should_log = False

    for name, check in probes.items():
        comp = dict(components_state.get(name) or {})
        prev_failures = int(comp.get("consecutive_failures", 0))
        last_recovery = float(comp.get("last_recovery_ts", 0.0))

        if check.get("healthy"):
            if prev_failures > 0:
                actions[name] = "recovered"
                should_log = True
            else:
                actions[name] = "ok"
            comp["consecutive_failures"] = 0
            comp["last_detail"] = ""
        else:
            failures = prev_failures + 1
            comp["consecutive_failures"] = failures
            comp["last_detail"] = str(check.get("detail") or "unhealthy")
            should_log = True

            if failures < failure_threshold:
                actions[name] = "degraded_pending_threshold"
            elif (now - last_recovery) < cooldown_seconds:
                actions[name] = "cooldown_active"
            elif dry_run:
                actions[name] = "would_recover"
            else:
                rec = recover_impl(name)
                recovery_details[name] = rec
                comp["last_recovery_ts"] = now
                actions[name] = "restarted" if rec.get("ok") else "recovery_failed"

        comp["healthy"] = bool(check.get("healthy"))
        comp["last_checked_at"] = iso_now
        components_state[name] = comp

    state["last_run_at"] = iso_now
    state["last_actions"] = actions
    _save_state(state_path, state)

    summary: dict[str, Any] = {
        "timestamp": iso_now,
        "overall": "healthy" if all(v.get("healthy") for v in probes.values()) else "degraded",
        "actions": actions,
        "components": components_state,
    }
    if recovery_details:
        summary["recoveries"] = recovery_details

    if should_log:
        _append_log(
            log_path,
            {
                "timestamp": iso_now,
                "overall": summary["overall"],
                "actions": actions,
                "recoveries": recovery_details,
            },
        )

    return summary
