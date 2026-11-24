"""FastAPI + FastMCP unified gateway composing /mcp and isolated /servers/<slug>/mcp routes."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Body, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack import __version__
from mcp_stack.core.auth import GatewayAuthMiddleware
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.metrics import render_metrics
from mcp_stack.evals import (
    _trace_duration_ms,
    is_expected_policy_refusal,
    run_trace_evaluation,
)
from mcp_stack.gateway.dashboard import render_dashboard_html
from mcp_stack.servers.docker_server import create_docker_server
from mcp_stack.servers.filesystem import create_filesystem_server
from mcp_stack.servers.github import create_github_server
from mcp_stack.servers.jupyter_server import create_jupyter_server
from mcp_stack.servers.kubernetes_server import create_kubernetes_server
from mcp_stack.servers.memory import create_memory_server
from mcp_stack.servers.mlflow_server import (
    create_mlflow_server,
    create_mlflow_upstream_proxy,
    probe_mcp_http_endpoint,
)
from mcp_stack.servers.mongodb import create_mongodb_server
from mcp_stack.servers.neo4j_server import create_neo4j_server
from mcp_stack.servers.photos import create_photos_server
from mcp_stack.servers.postgresql import create_postgresql_server
from mcp_stack.servers.redis_server import create_redis_server
from mcp_stack.servers.unity_catalog import (
    UCClientAdapter,
    create_unity_catalog_server,
    sync_uc_function_tools,
)
from mcp_stack.servers.xcodebuild import create_xcodebuild_server
from mcp_stack.watchdog import (
    DEFAULT_LOG_PATH,
    DEFAULT_STATE_PATH,
    _load_state,
    run_watchdog_once,
)


def _slug_for(server_key: str) -> str:
    return server_key.replace("_", "-")


class NormalizeMCPPathMiddleware:
    """Rewrite exact /mcp, /servers/<slug>/mcp, and /profiles/<name>/mcp to avoid 307."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/mcp" or (
                path.startswith(("/servers/", "/profiles/")) and path.endswith("/mcp")
            ):
                new_scope = dict(scope)
                new_scope["path"] = path + "/"
                raw_path = scope.get("raw_path")
                if isinstance(raw_path, bytes) and not raw_path.endswith(b"/"):
                    new_scope["raw_path"] = raw_path + b"/"
                scope = new_scope
        await self.app(scope, receive, send)


def build_server_instance(
    server_key: str,
    settings: MCPStackSettings,
    *,
    overrides: dict[str, FastMCP] | None = None,
) -> tuple[FastMCP, UCClientAdapter | None]:
    """Instantiate a single FastMCP server by key."""
    if overrides and server_key in overrides:
        return overrides[server_key], None

    normalized = server_key.replace("-", "_")
    if normalized == "unity_catalog":
        adapter = UCClientAdapter(settings)
        return create_unity_catalog_server(settings, adapter=adapter), adapter
    if normalized == "mlflow":
        return create_mlflow_server(settings), None
    if normalized == "memory":
        return create_memory_server(settings), None
    if normalized == "filesystem":
        return create_filesystem_server(settings), None
    if normalized == "github":
        return create_github_server(settings), None
    if normalized == "docker":
        return create_docker_server(settings), None
    if normalized == "photos":
        return create_photos_server(settings), None
    if normalized == "postgresql":
        return create_postgresql_server(settings), None
    if normalized == "redis":
        return create_redis_server(settings), None
    if normalized == "mongodb":
        return create_mongodb_server(settings), None
    if normalized == "neo4j":
        return create_neo4j_server(settings), None
    if normalized == "kubernetes":
        return create_kubernetes_server(settings), None
    if normalized == "jupyter":
        return create_jupyter_server(settings), None
    if normalized == "xcodebuild":
        return create_xcodebuild_server(settings), None
    raise ValueError(f"Unknown MCP server '{server_key}'")


def build_gateway_app(
    settings: MCPStackSettings,
    *,
    server_overrides: dict[str, FastMCP] | None = None,
    upstream_proxy_factory: Callable[[MCPStackSettings], FastMCP] | None = None,
    compose_upstream_on_startup: bool | None = None,
) -> FastAPI:
    """Build the unified FastAPI + FastMCP Streamable HTTP gateway."""
    logger = get_logger("gateway")

    enabled_keys = [k.replace("-", "_") for k in settings.gateway.enabled_servers]
    if (
        settings.gateway.enable_photos_on_macos
        and sys.platform == "darwin"
        and "photos" not in enabled_keys
    ):
        enabled_keys.append("photos")
    elif sys.platform != "darwin" and "photos" in enabled_keys:
        enabled_keys = [k for k in enabled_keys if k != "photos"]

    if (
        settings.gateway.enable_xcode_on_macos
        and sys.platform == "darwin"
        and "xcodebuild" not in enabled_keys
    ):
        enabled_keys.append("xcodebuild")
    elif sys.platform != "darwin" and "xcodebuild" in enabled_keys:
        enabled_keys = [k for k in enabled_keys if k != "xcodebuild"]

    servers: dict[str, FastMCP] = {}
    uc_adapter: UCClientAdapter | None = None
    for key in enabled_keys:
        srv, adapter = build_server_instance(key, settings, overrides=server_overrides)
        servers[key] = srv
        if adapter is not None:
            uc_adapter = adapter

    composed = FastMCP("mcp-workshop-gateway")
    for _key, srv in servers.items():
        composed.mount(srv)

    upstream_proxy: FastMCP | None = None
    if settings.mlflow.proxy_upstream_mcp:
        factory = upstream_proxy_factory or create_mlflow_upstream_proxy
        upstream_proxy = factory(settings)

    composed_http = composed.http_app(path="/")
    per_server_http: dict[str, Any] = {
        _slug_for(key): srv.http_app(path="/") for key, srv in servers.items()
    }
    if upstream_proxy is not None:
        per_server_http["mlflow-upstream"] = upstream_proxy.http_app(path="/")

    profile_apps: dict[str, FastMCP] = {}
    profile_http: dict[str, Any] = {}
    profile_wants_upstream: dict[str, bool] = {}
    profile_inventory: list[dict[str, Any]] = []

    for profile_name, raw_members in settings.gateway.profiles.items():
        clean_profile = profile_name.strip()
        if not clean_profile:
            continue
        p_mcp = FastMCP(f"mcp-profile-{clean_profile}")
        resolved_slugs: list[str] = []
        wants_upstream = False
        for member in raw_members:
            norm = member.strip().replace("-", "_")
            if norm == "mlflow_upstream":
                if upstream_proxy is not None:
                    wants_upstream = True
                continue
            if norm in servers:
                p_mcp.mount(servers[norm])
                resolved_slugs.append(_slug_for(norm))
        profile_apps[clean_profile] = p_mcp
        profile_http[clean_profile] = p_mcp.http_app(path="/")
        profile_wants_upstream[clean_profile] = wants_upstream
        profile_inventory.append(
            {
                "name": clean_profile,
                "route": f"/profiles/{clean_profile}/mcp",
                "servers": resolved_slugs,
                "includesUpstreamMcp": wants_upstream,
            }
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            if (
                "unity_catalog" in servers
                and uc_adapter is not None
                and settings.unity_catalog.dynamic_function_tools
            ):
                try:
                    sync_res = await asyncio.wait_for(
                        sync_uc_function_tools(servers["unity_catalog"], uc_adapter, settings),
                        timeout=3.0,
                    )
                    if sync_res.get("registered"):
                        logger.info(
                            "Registered dynamic UC function tools",
                            tools=sync_res["registered"],
                        )
                except Exception as exc:
                    logger.debug("Initial UC function sync skipped", error=str(exc))

            if upstream_proxy is not None:
                should_compose = compose_upstream_on_startup
                if should_compose is None:
                    probe = await probe_mcp_http_endpoint(settings.mlflow.mcp_url, timeout=1.5)
                    should_compose = bool(probe.get("reachable"))
                if should_compose:
                    composed.mount(upstream_proxy)
                    for pname, p_mcp in profile_apps.items():
                        if profile_wants_upstream.get(pname):
                            p_mcp.mount(upstream_proxy)
                    logger.info(
                        "Composed upstream mlflow[mcp] into /mcp and enabled profiles",
                        url=settings.mlflow.mcp_url,
                    )
                else:
                    logger.info(
                        "Upstream mlflow[mcp] unreachable at startup; skipping /mcp composition",
                        url=settings.mlflow.mcp_url,
                    )

            await stack.enter_async_context(composed_http.lifespan(app))
            for _slug, sub_http in per_server_http.items():
                await stack.enter_async_context(sub_http.lifespan(app))
            for _pname, p_http in profile_http.items():
                await stack.enter_async_context(p_http.lifespan(app))
            yield

    app = FastAPI(
        title="MCP Workshop Stack Gateway",
        version=__version__,
        lifespan=lifespan,
    )

    server_inventory = [
        {
            "key": key,
            "slug": _slug_for(key),
            "route": f"/servers/{_slug_for(key)}/mcp",
            "status": "enabled",
        }
        for key in servers
    ]
    if upstream_proxy is not None:
        server_inventory.append(
            {
                "key": "mlflow_upstream",
                "slug": "mlflow-upstream",
                "route": "/servers/mlflow-upstream/mcp",
                "status": "proxy",
                "target": settings.mlflow.mcp_url,
            }
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            "composedRoute": "/mcp",
            "defaultProfile": settings.gateway.default_client_profile,
            "servers": server_inventory,
            "profiles": profile_inventory,
        }

    @app.get("/ready")
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

    @app.get("/api/v1/servers")
    async def list_servers() -> dict[str, Any]:
        return {
            "composedRoute": "/mcp",
            "servers": server_inventory,
        }

    @app.get("/api/v1/profiles")
    async def list_profiles() -> dict[str, Any]:
        return {
            "defaultProfile": settings.gateway.default_client_profile,
            "fullRoute": "/mcp",
            "profiles": profile_inventory,
        }

    @app.get("/ui", response_class=HTMLResponse)
    async def dashboard_ui() -> HTMLResponse:
        return HTMLResponse(content=render_dashboard_html(__version__))

    async def _collect_tools_for_server(slug: str, srv: FastMCP) -> list[dict[str, Any]]:
        try:
            items = await asyncio.wait_for(srv.list_tools(), timeout=2.0)
        except Exception as exc:
            logger.debug("Tool inspection skipped for server", server=slug, error=str(exc))
            return []
        collected: list[dict[str, Any]] = []
        for tool in items:
            params = getattr(tool, "parameters", None)
            if not isinstance(params, dict):
                params = {}
            collected.append(
                {
                    "name": getattr(tool, "name", ""),
                    "server": slug,
                    "description": (getattr(tool, "description", None) or "").strip(),
                    "parameters": params,
                }
            )
        return collected

    @app.get("/api/v1/tools")
    async def list_tools_api(
        server: str | None = None,
        profile: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        target_slugs: dict[str, FastMCP] = {
            _slug_for(k): srv for k, srv in servers.items()
        }
        if upstream_proxy is not None:
            target_slugs["mlflow-upstream"] = upstream_proxy

        allowed_by_profile: set[str] | None = None
        if profile:
            prof_entry = next((p for p in profile_inventory if p["name"] == profile), None)
            if prof_entry is None:
                return {"totalTools": 0, "profileCounts": {}, "tools": []}
            allowed_by_profile = set(prof_entry["servers"])
            if prof_entry.get("includesUpstreamMcp"):
                allowed_by_profile.add("mlflow-upstream")

        per_server_tools: dict[str, list[dict[str, Any]]] = {}
        for slug, srv in target_slugs.items():
            per_server_tools[slug] = await _collect_tools_for_server(slug, srv)

        profile_counts: dict[str, int] = {}
        for prof in profile_inventory:
            total = sum(len(per_server_tools.get(s, [])) for s in prof["servers"])
            if prof.get("includesUpstreamMcp"):
                total += len(per_server_tools.get("mlflow-upstream", []))
            profile_counts[str(prof["name"])] = total

        needle = (q or "").strip().lower()
        srv_filter = (server or "").strip().replace("_", "-").lower()

        filtered: list[dict[str, Any]] = []
        for slug, items in per_server_tools.items():
            if srv_filter and slug.lower() != srv_filter:
                continue
            if allowed_by_profile is not None and slug not in allowed_by_profile:
                continue
            for item in items:
                if needle:
                    hay = f"{item['name']} {item['description']} {slug}".lower()
                    if needle not in hay:
                        continue
                filtered.append(item)

        return {
            "totalTools": len(filtered),
            "profileCounts": profile_counts,
            "tools": filtered,
        }

    @app.get("/api/v1/watchdog")
    async def watchdog_status_api() -> dict[str, Any]:
        state = await asyncio.to_thread(_load_state, DEFAULT_STATE_PATH)
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
        return {
            "statePath": str(DEFAULT_STATE_PATH),
            "logPath": str(DEFAULT_LOG_PATH),
            "lastRunAt": state.get("last_run_at"),
            "lastActions": state.get("last_actions") or {},
            "components": state.get("components") or {},
            "recentEvents": recent_events,
        }

    @app.get("/api/v1/traces")
    async def recent_traces_api(limit: int = 20) -> dict[str, Any]:
        clamped = max(1, min(limit, 100))

        def _fetch() -> dict[str, Any]:
            import mlflow

            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            exp = client.get_experiment_by_name(settings.mlflow.experiment_name)
            if exp is None:
                return {
                    "available": True,
                    "experiment": settings.mlflow.experiment_name,
                    "traces": [],
                    "latestEvalRun": None,
                }
            traces = client.search_traces(
                locations=[exp.experiment_id],
                max_results=clamped,
                order_by=["timestamp_ms DESC"],
            )
            trace_rows: list[dict[str, Any]] = []
            for tr in traces:
                info = getattr(tr, "info", tr)
                spans = getattr(getattr(tr, "data", None), "spans", None) or []
                root_name = getattr(spans[0], "name", "") if spans else ""
                trace_rows.append(
                    {
                        "traceId": getattr(info, "trace_id", None)
                        or getattr(info, "request_id", None),
                        "name": root_name,
                        "state": str(getattr(info, "state", "")),
                        "policyRefusal": is_expected_policy_refusal(tr),
                        "durationMs": round(_trace_duration_ms(tr), 1),
                    }
                )
            latest_eval: dict[str, Any] | None = None
            try:
                runs = client.search_runs(
                    [exp.experiment_id],
                    order_by=["attributes.start_time DESC"],
                    max_results=10,
                )
                for run in runs:
                    metrics = {
                        k: round(float(v), 4)
                        for k, v in (run.data.metrics or {}).items()
                        if "/" in k or "tool_" in k or "policy_" in k
                    }
                    if metrics:
                        latest_eval = {
                            "run_id": run.info.run_id,
                            "metrics": metrics,
                        }
                        break
            except Exception:
                pass
            return {
                "available": True,
                "experiment": settings.mlflow.experiment_name,
                "experimentId": exp.experiment_id,
                "traces": trace_rows,
                "latestEvalRun": latest_eval,
            }

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            return {
                "available": False,
                "experiment": settings.mlflow.experiment_name,
                "error": str(exc),
                "traces": [],
                "latestEvalRun": None,
            }

    @app.post("/api/v1/actions/refresh-uc")
    async def action_refresh_uc() -> dict[str, Any]:
        if "unity_catalog" not in servers or uc_adapter is None:
            return {"status": "skipped", "reason": "unity_catalog server is not enabled"}
        return await sync_uc_function_tools(servers["unity_catalog"], uc_adapter, settings)

    @app.post("/api/v1/actions/watchdog")
    async def action_watchdog(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        dry_run = True if not isinstance(payload, dict) else bool(payload.get("dry_run", True))
        return await asyncio.to_thread(run_watchdog_once, settings, dry_run=dry_run)

    @app.post("/api/v1/actions/eval")
    async def action_eval(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        raw_limit = 20 if not isinstance(payload, dict) else int(payload.get("limit", 20))
        clamped = max(1, min(raw_limit, 100))
        return await asyncio.to_thread(run_trace_evaluation, settings, limit=clamped)

    @app.get("/metrics")
    async def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    app.mount("/mcp", composed_http)
    for slug, sub_http in per_server_http.items():
        app.mount(f"/servers/{slug}/mcp", sub_http)
    for pname, p_http in profile_http.items():
        app.mount(f"/profiles/{pname}/mcp", p_http)

    # Pure ASGI middlewares (outermost added last: CORS -> NormalizePath -> Auth)
    app.add_middleware(GatewayAuthMiddleware, settings=settings)
    app.add_middleware(NormalizeMCPPathMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.gateway.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
