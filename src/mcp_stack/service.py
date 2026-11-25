"""macOS LaunchAgent lifecycle management and log rotation for mcp-workshop-stack."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from mcp_stack.core.config import MCPStackSettings

MLFLOW_MCP_LABEL = "com.spencer.mcp-mlflow-mcp"
GATEWAY_LABEL = "com.spencer.mcp-workshop-gateway"
WATCHDOG_LABEL = "com.spencer.mcp-workshop-watchdog"
LOG_DIR = Path.home() / "Library/Logs/mcp-workshop-stack"
LAUNCH_AGENTS_DIR = Path.home() / "Library/LaunchAgents"
WATCHDOG_STATE_PATH = Path.home() / ".local/share/mcp-workshop-stack/watchdog-state.json"


def rotate_log_file(path: Path, *, max_bytes: int = 10 * 1024 * 1024, keep: int = 3) -> bool:
    """Rotate a log file if it exceeds max_bytes, keeping up to `keep` numbered archives."""
    if not path.exists() or path.stat().st_size <= max_bytes:
        return False
    for idx in range(keep, 0, -1):
        src = path if idx == 1 else path.with_name(f"{path.name}.{idx - 1}")
        dst = path.with_name(f"{path.name}.{idx}")
        if idx == keep and dst.exists():
            dst.unlink()
        if src.exists():
            src.replace(dst)
    path.touch()
    return True


def rotate_service_logs(
    log_dir: Path = LOG_DIR,
    *,
    max_mb: float = 10.0,
    keep: int = 3,
) -> dict[str, Any]:
    """Rotate oversized .log files under log_dir."""
    max_bytes = int(max_mb * 1024 * 1024)
    log_dir.mkdir(parents=True, exist_ok=True)
    rotated: list[str] = []
    scanned = 0
    for item in sorted(log_dir.glob("*.log")):
        scanned += 1
        if rotate_log_file(item, max_bytes=max_bytes, keep=keep):
            rotated.append(str(item))
    return {"log_dir": str(log_dir), "scanned": scanned, "rotated": rotated, "max_mb": max_mb}


def _launchctl_info(uid: int, label: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"loaded": False, "state": "unloaded", "pid": None}
    state = "unknown"
    pid: int | None = None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state ="):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid ="):
            val = stripped.split("=", 1)[1].strip()
            if val.isdigit():
                pid = int(val)
    return {"loaded": True, "state": state, "pid": pid}


def get_service_status(settings: MCPStackSettings) -> dict[str, Any]:
    """Inspect LaunchAgents, Docker Unity Catalog, and gateway /ready."""
    uid = os.getuid()
    services = {
        MLFLOW_MCP_LABEL: _launchctl_info(uid, MLFLOW_MCP_LABEL),
        GATEWAY_LABEL: _launchctl_info(uid, GATEWAY_LABEL),
        WATCHDOG_LABEL: _launchctl_info(uid, WATCHDOG_LABEL),
    }
    ready: dict[str, Any] = {}
    url = f"http://{settings.gateway.host}:{settings.gateway.port}/ready"
    try:
        r = httpx.get(url, timeout=2.0)
        ready = r.json()
    except Exception as exc:
        ready = {"status": "unreachable", "error": str(exc)}
    watchdog_state: dict[str, Any] | None = None
    if WATCHDOG_STATE_PATH.exists():
        try:
            watchdog_state = json.loads(WATCHDOG_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            watchdog_state = None
    return {
        "uid": uid,
        "launchagents": services,
        "gateway_ready": ready,
        "watchdog_state": watchdog_state,
    }


def _wait_ready(settings: MCPStackSettings, timeout_s: float = 25.0) -> dict[str, Any]:
    url = f"http://{settings.gateway.host}:{settings.gateway.port}/ready"
    deadline = time.monotonic() + timeout_s
    last: Any = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            body = r.json()
            last = body
            if r.status_code == 200 and body.get("status") == "ready":
                return dict(body)
        except Exception as exc:
            last = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Gateway did not report ready within {timeout_s}s: {last}")


def install_launchagents(
    settings: MCPStackSettings,
    repo_root: Path,
    *,
    agents_dir: Path = LAUNCH_AGENTS_DIR,
    log_dir: Path = LOG_DIR,
) -> dict[str, Any]:
    """Install deploy/launchd plists into LaunchAgents and bootstrap both services."""
    uid = os.getuid()
    src_dir = repo_root / "deploy/launchd"
    log_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for label in (MLFLOW_MCP_LABEL, GATEWAY_LABEL, WATCHDOG_LABEL):
        src = src_dir / f"{label}.plist"
        dst = agents_dir / f"{label}.plist"
        shutil.copy2(src, dst)
        subprocess.run(["plutil", "-lint", str(dst)], check=True, capture_output=True, text=True)
        installed.append(str(dst))

    for label in (WATCHDOG_LABEL, GATEWAY_LABEL, MLFLOW_MCP_LABEL):
        bootout = subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{label}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if bootout.returncode == 0:
            unload_deadline = time.monotonic() + 3.0
            while time.monotonic() < unload_deadline:
                probe = subprocess.run(
                    ["launchctl", "print", f"gui/{uid}/{label}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if probe.returncode != 0:
                    break
                time.sleep(0.2)

    for label in (MLFLOW_MCP_LABEL, GATEWAY_LABEL, WATCHDOG_LABEL):
        plist_path = str(agents_dir / f"{label}.plist")
        last_err = ""
        for attempt in range(3):
            res = subprocess.run(
                ["launchctl", "bootstrap", f"gui/{uid}", plist_path],
                check=False,
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                break
            last_err = (res.stderr or res.stdout or f"exit {res.returncode}").strip()
            if res.returncode == 5 and attempt < 2:
                time.sleep(0.5)
                continue
            raise RuntimeError(
                f"launchctl bootstrap failed for {label} (exit {res.returncode}): {last_err}"
            )

    ready = _wait_ready(settings)
    return {"installed": installed, "uid": uid, "ready": ready}


def restart_launchagents(settings: MCPStackSettings) -> dict[str, Any]:
    """Kickstart LaunchAgents in dependency order and verify /ready."""
    uid = os.getuid()
    rotate_service_logs()
    for label in (MLFLOW_MCP_LABEL, GATEWAY_LABEL):
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"],
            check=True,
            capture_output=True,
            text=True,
        )
    ready = _wait_ready(settings)
    return {"restarted": [MLFLOW_MCP_LABEL, GATEWAY_LABEL], "ready": ready}


def tail_service_logs(
    *,
    service: str = "all",
    lines: int = 40,
    log_dir: Path = LOG_DIR,
) -> dict[str, str]:
    """Return trailing lines from LaunchAgent logs."""
    targets = {
        "gateway": ["gateway.log", "gateway.err.log"],
        "mlflow-mcp": ["mlflow-mcp.log", "mlflow-mcp.err.log"],
        "watchdog": ["watchdog.log"],
    }
    names = (
        [*targets["gateway"], *targets["mlflow-mcp"], *targets["watchdog"]]
        if service == "all"
        else targets.get(service, [])
    )
    out: dict[str, str] = {}
    for fname in names:
        p = log_dir / fname
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace").splitlines()
            out[fname] = "\n".join(content[-lines:])
        else:
            out[fname] = ""
    return out
