"""Health, readiness, Prometheus metrics, watchdog, and live ops telemetry routes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Body, Response
from fastapi.responses import StreamingResponse

from mcp_stack import __version__
from mcp_stack.core.metrics import render_metrics
from mcp_stack.gateway.state import GatewayRuntimeState
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint
from mcp_stack.watchdog import (
    DEFAULT_LOG_PATH,
    DEFAULT_STATE_PATH,
    _default_eval_regression_probe,
    _load_state,
)


def build_ops_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            "composedRoute": "/mcp",
            "defaultProfile": settings.gateway.default_client_profile,
            "mlflowUiUrl": settings.gateway.mlflow_ui_url or settings.mlflow.tracking_uri,
            "servers": state.server_inventory,
            "profiles": state.profile_inventory,
        }

    @router.get("/ready")
    async def ready() -> dict[str, Any]:
        checks: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                r = await client.get(
                    f"{settings.mlflow.tracking_uri.rstrip('/')}/api/2.0/mlflow/experiments/search",
                    params={"max_results": 1},
                )
                mlflow_check: dict[str, Any] = {
                    "healthy": r.status_code == 200,
                    "status_code": r.status_code,
                    "url": settings.mlflow.tracking_uri,
                }
                if r.status_code != 200:
                    mlflow_check["detail"] = r.text[:200]
                checks["mlflow_tracking"] = mlflow_check
            except Exception as exc:
                checks["mlflow_tracking"] = {
                    "healthy": False,
                    "url": settings.mlflow.tracking_uri,
                    "error": str(exc),
                }

            try:
                r = await client.get(
                    f"{settings.unity_catalog.effective_api_base}/catalogs",
                    params={"max_results": 1},
                )
                checks["unity_catalog"] = {
                    "healthy": r.status_code == 200,
                    "status_code": r.status_code,
                    "url": settings.unity_catalog.effective_api_base,
                }
            except Exception as exc:
                checks["unity_catalog"] = {
                    "healthy": False,
                    "url": settings.unity_catalog.effective_api_base,
                    "error": str(exc),
                }

        checks["mlflow_mcp_upstream"] = await probe_mcp_http_endpoint(
            settings.mlflow.mcp_url, timeout=2.0
        )
        all_healthy = all(
            c.get("healthy", c.get("reachable", False)) for c in checks.values()
        )
        return {
            "status": "ready" if all_healthy else "degraded",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        }

    @router.get("/api/v1/watchdog")
    async def watchdog_status_api() -> dict[str, Any]:
        wd_state = await asyncio.to_thread(_load_state, DEFAULT_STATE_PATH)
        recent_events: list[dict[str, Any]] = []
        try:
            if DEFAULT_LOG_PATH.exists():
                raw_lines = DEFAULT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-25:]
                for line in reversed(raw_lines):
                    if not line.strip():
                        continue
                    try:
                        recent_events.append(json.loads(line))
                    except Exception:
                        recent_events.append({"raw": line})
        except Exception as exc:
            recent_events.append({"error": str(exc)})
        eval_regression = wd_state.get("eval_regression")
        if eval_regression is None:
            eval_regression = await asyncio.to_thread(
                _default_eval_regression_probe, settings, timeout=0.6
            )
        return {
            "statePath": str(DEFAULT_STATE_PATH),
            "logPath": str(DEFAULT_LOG_PATH),
            "lastRunAt": wd_state.get("last_run_at"),
            "lastActions": wd_state.get("last_actions") or {},
            "components": wd_state.get("components") or {},
            "evalRegression": eval_regression,
            "recentEvents": recent_events,
        }

    @router.post("/api/v1/actions/watchdog")
    async def action_watchdog(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        import mcp_stack.gateway.app as app_mod

        dry_run = True if not isinstance(payload, dict) else bool(payload.get("dry_run", True))
        res = await asyncio.to_thread(app_mod.run_watchdog_once, settings, dry_run=dry_run)
        state.activity_bus.record(
            "watchdog_tick",
            status="ok" if res.get("overall") == "healthy" else "warn",
            summary=f"Watchdog {res.get('overall')} (dry_run={dry_run})",
        )
        return res

    @router.get("/api/v1/ops/secrets-health")
    async def ops_secrets_health_api() -> dict[str, Any]:
        diag = state.secret_resolver.diagnostics()
        auth_req = [
            {
                "slug": str(u.get("slug") or ""),
                "reasonCode": u.get("authReasonCode"),
                "detail": u.get("detail"),
            }
            for u in state.server_inventory
            if u.get("external") and u.get("connectionStatus") == "auth_required"
        ]
        return {**diag, "authRequiredUpstreams": auth_req}

    @router.post("/api/v1/ops/reprobe-auth-required")
    async def ops_reprobe_auth_required_api() -> dict[str, Any]:
        state.secret_resolver.clear_cache()
        reprobed: list[dict[str, Any]] = []
        for raw_key, cfg in list(settings.gateway.upstream_servers.items()):
            slug = raw_key.strip().replace("_", "-").lower()
            cur_status = str(
                (state.federated_meta.get(slug) or {}).get("connectionStatus") or ""
            )
            if cur_status == "auth_required" or not cur_status:
                updated = await state.sync_upstream_runtime(slug, cfg)
                reprobed.append(
                    {
                        "slug": slug,
                        "connectionStatus": updated.get("connectionStatus"),
                        "toolCount": updated.get("toolCount", 0),
                    }
                )
        return {
            "reprobed": reprobed,
            "diagnostics": state.secret_resolver.diagnostics(),
        }

    @router.get("/api/v1/ops/metrics-series")
    async def ops_metrics_series_api(
        bucket_seconds: int = 300,
        buckets: int = 12,
    ) -> dict[str, Any]:
        series = state.activity_bus.metrics_series(
            bucket_seconds=bucket_seconds,
            buckets=buckets,
        )
        return {
            "bucketSeconds": bucket_seconds,
            "series": series,
            "recent": state.activity_bus.recent(limit=25),
        }

    @router.get("/api/v1/ops/stream")
    async def ops_stream_api() -> StreamingResponse:
        return StreamingResponse(
            state.activity_bus.stream_sse(replay_limit=30),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/metrics")
    async def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return router
