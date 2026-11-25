"""FastAPI + FastMCP unified gateway composing /mcp and isolated /servers/<slug>/mcp routes."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack import __version__
from mcp_stack.client_configs import generate_client_configs
from mcp_stack.core.auth import (
    UI_SESSION_COOKIE,
    GatewayAuthMiddleware,
    LoginNonceStore,
    caller_auth_method_var,
    caller_client_id_var,
    caller_client_policy_var,
    find_client_by_id,
    is_server_allowed,
    sign_ui_session,
    verify_ui_session,
)
from mcp_stack.core.config import ClientPolicy, MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.metrics import render_metrics
from mcp_stack.evals import (
    _POLICY_REFUSAL_MARKERS,
    GOLDEN_DATASET_NAME,
    _trace_duration_ms,
    is_expected_policy_refusal,
    run_golden_benchmark,
    run_trace_evaluation,
    sync_golden_dataset,
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
    _EVAL_SCORE_KEYS,
    DEFAULT_LOG_PATH,
    DEFAULT_STATE_PATH,
    _default_eval_regression_probe,
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
    login_nonces = LoginNonceStore()
    app.state.login_nonces = login_nonces

    def _set_session_cookie(response: Response, cookie_token: str, request: Request) -> None:
        fwd_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        is_https = request.url.scheme == "https" or fwd_proto == "https"
        response.set_cookie(
            key=UI_SESSION_COOKIE,
            value=cookie_token,
            max_age=settings.gateway.ui_session_ttl_s,
            path="/",
            httponly=True,
            samesite="strict",
            secure=is_https,
        )

    def _resolve_auth_identity(request: Request) -> tuple[ClientPolicy | None, str]:
        if not settings.gateway.effective_auth_enabled:
            return None, "open"
        auth_header = request.headers.get("authorization", "")
        bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        if bearer:
            return settings.gateway.clients.get(bearer), "bearer"
        cookie_val = request.cookies.get(UI_SESSION_COOKIE)
        cid = verify_ui_session(cookie_val, settings)
        if cid:
            return find_client_by_id(settings, cid), "cookie"
        return None, "anonymous"

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
            "clientSnippets": generate_client_configs(settings, repo_root=Path.cwd()),
        }

    @app.get("/ui", response_class=HTMLResponse)
    async def dashboard_ui() -> HTMLResponse:
        return HTMLResponse(content=render_dashboard_html(__version__))

    @app.post("/api/v1/auth/login-link", response_model=None)
    async def ui_login_link_api(request: Request) -> dict[str, Any] | JSONResponse:
        if settings.gateway.effective_auth_enabled and caller_auth_method_var.get() != "bearer":
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "BEARER_REQUIRED",
                        "message": "Minting a /ui login link requires Authorization: Bearer auth",
                    }
                },
            )
        client_id = caller_client_id_var.get() or "codex"
        if client_id == "anonymous":
            first = next(iter(settings.gateway.clients.values()), None)
            client_id = first.client_id if first is not None else "local"
        nonce = login_nonces.issue(client_id)
        origin = str(request.base_url).rstrip("/")
        return {
            "url": f"{origin}/ui/login?nonce={nonce}",
            "expiresInSeconds": 60,
            "clientId": client_id,
        }

    @app.get("/ui/login")
    async def ui_login_consume(request: Request, nonce: str = "") -> RedirectResponse:
        client_id = login_nonces.consume(nonce)
        if not client_id:
            return RedirectResponse(url="/ui?auth_error=invalid_link", status_code=303)
        session_val = sign_ui_session(client_id, settings)
        resp = RedirectResponse(url="/ui", status_code=303)
        _set_session_cookie(resp, session_val, request)
        return resp

    @app.post("/api/v1/auth/session", response_model=None)
    async def ui_session_create(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Response:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        if not token and isinstance(payload, dict):
            token = str(payload.get("token") or "").strip()

        if not settings.gateway.effective_auth_enabled:
            session_val = sign_ui_session("local", settings)
            resp = JSONResponse(
                {
                    "authenticated": True,
                    "authEnabled": False,
                    "clientId": "local",
                    "clientName": "Local (Auth Disabled)",
                    "allowedServers": ["*"],
                    "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
                }
            )
            _set_session_cookie(resp, session_val, request)
            return resp

        policy = settings.gateway.clients.get(token) if token else None
        if policy is None:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "AUTH_FAILED", "message": "Invalid Bearer token"}},
            )
        session_val = sign_ui_session(policy.client_id, settings)
        resp = JSONResponse(
            {
                "authenticated": True,
                "authEnabled": True,
                "clientId": policy.client_id,
                "clientName": policy.client_name,
                "allowedServers": list(policy.allowed_servers),
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
            }
        )
        _set_session_cookie(resp, session_val, request)
        return resp

    @app.get("/api/v1/auth/me")
    async def ui_session_me(request: Request) -> dict[str, Any]:
        policy, method = _resolve_auth_identity(request)
        if not settings.gateway.effective_auth_enabled:
            return {
                "authenticated": True,
                "authEnabled": False,
                "clientId": "local",
                "clientName": "Local (Auth Disabled)",
                "allowedServers": ["*"],
                "authMethod": "open",
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
            }
        if policy is None:
            return {
                "authenticated": False,
                "authEnabled": True,
                "clientId": None,
                "clientName": None,
                "allowedServers": [],
                "authMethod": "anonymous",
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
            }
        return {
            "authenticated": True,
            "authEnabled": True,
            "clientId": policy.client_id,
            "clientName": policy.client_name,
            "allowedServers": list(policy.allowed_servers),
            "authMethod": method,
            "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
        }

    @app.post("/api/v1/auth/logout")
    async def ui_session_logout() -> Response:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(key=UI_SESSION_COOKIE, path="/")
        return resp

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
        eval_regression = state.get("eval_regression")
        if eval_regression is None:
            eval_regression = await asyncio.to_thread(
                _default_eval_regression_probe, settings, timeout=0.6
            )
        return {
            "statePath": str(DEFAULT_STATE_PATH),
            "logPath": str(DEFAULT_LOG_PATH),
            "lastRunAt": state.get("last_run_at"),
            "lastActions": state.get("last_actions") or {},
            "components": state.get("components") or {},
            "evalRegression": eval_regression,
            "recentEvents": recent_events,
        }

    @app.get("/api/v1/traces")
    async def recent_traces_api(
        limit: int = 25,
        server: str = "",
        user: str = "",
        model_id: str = "",
        state: str = "",
        policy_refusal: str = "all",
        q: str = "",
    ) -> dict[str, Any]:
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
                    "facets": {"servers": [], "users": [], "modelIds": []},
                    "latestEvalRun": None,
                    "evalHistory": [],
                    "evalRegression": {
                        "status": "no_eval_runs",
                        "threshold": settings.gateway.eval_regression_threshold,
                    },
                }
            search_limit = max(clamped * 3, 60)
            traces = client.search_traces(
                locations=[exp.experiment_id],
                max_results=search_limit,
                order_by=["timestamp_ms DESC"],
            )
            all_rows: list[dict[str, Any]] = []
            facet_servers: set[str] = set()
            facet_users: set[str] = set()
            facet_models: set[str] = set()
            for tr in traces:
                info = getattr(tr, "info", tr)
                spans = getattr(getattr(tr, "data", None), "spans", None) or []
                root_name = getattr(spans[0], "name", "") if spans else ""
                tags = dict(getattr(info, "tags", None) or {})
                meta = dict(getattr(info, "trace_metadata", None) or {})
                srv_val = str(
                    tags.get("mcp.server")
                    or (root_name.split(".", 1)[0] if "." in root_name else "")
                ).strip()
                tool_val = str(
                    tags.get("mcp.tool")
                    or (root_name.split(".", 1)[1] if "." in root_name else "")
                ).strip()
                user_val = str(meta.get("mlflow.trace.user") or tags.get("mcp.user") or "").strip()
                model_val = str(
                    getattr(info, "model_id", None) or meta.get("mlflow.modelId") or ""
                ).strip()
                if srv_val:
                    facet_servers.add(srv_val)
                if user_val:
                    facet_users.add(user_val)
                if model_val:
                    facet_models.add(model_val)
                all_rows.append(
                    {
                        "traceId": getattr(info, "trace_id", None)
                        or getattr(info, "request_id", None),
                        "name": root_name,
                        "state": str(getattr(info, "state", "")),
                        "policyRefusal": is_expected_policy_refusal(tr),
                        "durationMs": round(_trace_duration_ms(tr), 1),
                        "timestampMs": getattr(info, "timestamp_ms", None),
                        "user": user_val or None,
                        "sessionId": meta.get("mlflow.trace.session"),
                        "modelId": model_val or None,
                        "server": srv_val or None,
                        "tool": tool_val or None,
                        "profile": tags.get("mcp.profile"),
                        "assessmentCount": len(getattr(info, "assessments", None) or []),
                    }
                )

            srv_f = server.strip().lower()
            usr_f = user.strip().lower()
            mdl_f = model_id.strip()
            st_f = state.strip().upper()
            pr_f = policy_refusal.strip().lower()
            q_f = q.strip().lower()

            filtered: list[dict[str, Any]] = []
            for row in all_rows:
                if srv_f and str(row.get("server") or "").lower() != srv_f:
                    continue
                if usr_f and str(row.get("user") or "").lower() != usr_f:
                    continue
                if mdl_f and str(row.get("modelId") or "") != mdl_f:
                    continue
                if st_f and st_f not in str(row.get("state") or "").upper():
                    continue
                if pr_f == "only" and not row["policyRefusal"]:
                    continue
                if pr_f == "exclude" and row["policyRefusal"]:
                    continue
                if q_f:
                    hay = (
                        f"{row.get('traceId', '')} {row.get('name', '')} "
                        f"{row.get('server', '')} {row.get('tool', '')} {row.get('user', '')}"
                    ).lower()
                    if q_f not in hay:
                        continue
                filtered.append(row)
                if len(filtered) >= clamped:
                    break

            eval_history: list[dict[str, Any]] = []
            try:
                runs = client.search_runs(
                    [exp.experiment_id],
                    order_by=["attributes.start_time DESC"],
                    max_results=25,
                )
                for run in runs:
                    metrics = {
                        k: round(float(v), 4)
                        for k, v in (run.data.metrics or {}).items()
                        if "/" in k or "tool_" in k or "policy_" in k
                    }
                    if metrics:
                        core_vals = [
                            metrics[k] for k in _EVAL_SCORE_KEYS if k in metrics
                        ] or list(metrics.values())
                        min_score = round(min(core_vals), 4)
                        eval_history.append(
                            {
                                "run_id": run.info.run_id,
                                "run_name": getattr(run.info, "run_name", None),
                                "timestamp_ms": getattr(run.info, "start_time", None),
                                "min_score": min_score,
                                "metrics": metrics,
                            }
                        )
                        if len(eval_history) >= 10:
                            break
            except Exception:
                pass

            latest_eval = eval_history[0] if eval_history else None
            threshold = settings.gateway.eval_regression_threshold
            if latest_eval is None:
                eval_regression: dict[str, Any] = {
                    "status": "no_eval_runs",
                    "threshold": threshold,
                }
            else:
                failing = {
                    k: v
                    for k, v in latest_eval["metrics"].items()
                    if k in _EVAL_SCORE_KEYS and v < threshold
                }
                eval_regression = {
                    "status": "regression" if failing else "ok",
                    "threshold": threshold,
                    "run_id": latest_eval["run_id"],
                    "run_name": latest_eval.get("run_name"),
                    "min_score": latest_eval["min_score"],
                    "failing_metrics": failing,
                }

            return {
                "available": True,
                "experiment": settings.mlflow.experiment_name,
                "experimentId": exp.experiment_id,
                "traces": filtered,
                "facets": {
                    "servers": sorted(facet_servers),
                    "users": sorted(facet_users),
                    "modelIds": sorted(facet_models),
                },
                "latestEvalRun": latest_eval,
                "evalHistory": eval_history,
                "evalRegression": eval_regression,
            }

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            return {
                "available": False,
                "experiment": settings.mlflow.experiment_name,
                "error": str(exc),
                "traces": [],
                "facets": {"servers": [], "users": [], "modelIds": []},
                "latestEvalRun": None,
                "evalHistory": [],
                "evalRegression": {
                    "status": "unavailable",
                    "threshold": settings.gateway.eval_regression_threshold,
                },
            }

    @app.get("/api/v1/traces/{trace_id}", response_model=None)
    async def trace_detail_api(trace_id: str) -> dict[str, Any] | JSONResponse:
        def _safe_json(val: Any) -> Any:
            try:
                return json.loads(json.dumps(val, default=str))
            except Exception:
                return str(val)

        def _fetch_one() -> dict[str, Any]:
            import mlflow

            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            trace = client.get_trace(trace_id)
            info = getattr(trace, "info", trace)
            raw_spans = getattr(getattr(trace, "data", None), "spans", None) or []
            spans_out: list[dict[str, Any]] = []
            for sp in raw_spans:
                start_ns = getattr(sp, "start_time_ns", None)
                end_ns = getattr(sp, "end_time_ns", None)
                dur_ms = (
                    round((end_ns - start_ns) / 1_000_000.0, 2)
                    if isinstance(start_ns, int)
                    and isinstance(end_ns, int)
                    and end_ns >= start_ns
                    else None
                )
                events_out: list[dict[str, Any]] = []
                for ev in getattr(sp, "events", None) or []:
                    attrs = getattr(ev, "attributes", None)
                    clean_attrs = (
                        {
                            k: v
                            for k, v in attrs.items()
                            if k != "exception.stacktrace"
                        }
                        if isinstance(attrs, dict)
                        else attrs
                    )
                    events_out.append(
                        {
                            "name": getattr(ev, "name", None),
                            "attributes": _safe_json(clean_attrs),
                        }
                    )
                spans_out.append(
                    {
                        "spanId": getattr(sp, "span_id", None),
                        "parentId": getattr(sp, "parent_id", None),
                        "name": getattr(sp, "name", ""),
                        "spanType": str(getattr(sp, "span_type", "")),
                        "status": str(getattr(sp, "status", "")),
                        "durationMs": dur_ms,
                        "inputs": _safe_json(getattr(sp, "inputs", None)),
                        "outputs": _safe_json(getattr(sp, "outputs", None)),
                        "events": events_out,
                    }
                )

            assessments_out: list[dict[str, Any]] = []
            for item in getattr(info, "assessments", None) or []:
                feedback = getattr(item, "feedback", None)
                expectation = getattr(item, "expectation", None)
                if feedback is not None:
                    kind = "feedback"
                    val = getattr(feedback, "value", None)
                elif expectation is not None:
                    kind = "expectation"
                    val = getattr(expectation, "value", None)
                else:
                    kind = "assessment"
                    val = getattr(item, "value", None)
                assessments_out.append(
                    {
                        "kind": kind,
                        "name": getattr(item, "name", None),
                        "value": _safe_json(val),
                        "rationale": getattr(item, "rationale", None),
                    }
                )

            tags = dict(getattr(info, "tags", None) or {})
            meta = dict(getattr(info, "trace_metadata", None) or {})
            return {
                "traceId": getattr(info, "trace_id", None) or trace_id,
                "state": str(getattr(info, "state", "")),
                "policyRefusal": is_expected_policy_refusal(trace),
                "durationMs": round(_trace_duration_ms(trace), 2),
                "timestampMs": getattr(info, "timestamp_ms", None),
                "user": meta.get("mlflow.trace.user"),
                "sessionId": meta.get("mlflow.trace.session"),
                "modelId": meta.get("mlflow.modelId") or getattr(info, "model_id", None),
                "tags": _safe_json(tags),
                "spans": spans_out,
                "assessments": assessments_out,
            }

        try:
            return await asyncio.to_thread(_fetch_one)
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            status_code = 404 if ("not found" in lowered or "does not exist" in lowered) else 503
            code = "NOT_FOUND" if status_code == 404 else "MLFLOW_UNAVAILABLE"
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": msg}},
            )

    @app.post("/api/v1/traces/{trace_id}/feedback", response_model=None)
    async def trace_feedback_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict) or "value" not in payload:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'value'"}},
            )
        name = str(payload.get("name") or "human_quality").strip() or "human_quality"
        value = payload["value"]
        rationale = (
            str(payload["rationale"]).strip()
            if payload.get("rationale") is not None
            else None
        )
        caller_id = caller_client_id_var.get() or "dashboard"

        def _log() -> dict[str, Any]:
            import mlflow
            from mlflow.entities.assessment_source import AssessmentSource, AssessmentSourceType

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            assessment = mlflow.log_feedback(
                trace_id=trace_id,
                name=name,
                value=value,
                rationale=rationale or None,
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN,
                    source_id=caller_id,
                ),
            )
            return {
                "logged": True,
                "traceId": trace_id,
                "assessmentId": getattr(assessment, "assessment_id", None),
                "name": name,
                "value": value,
            }

        try:
            return await asyncio.to_thread(_log)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @app.post("/api/v1/traces/{trace_id}/expectation", response_model=None)
    async def trace_expectation_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict) or "value" not in payload:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'value'"}},
            )
        name = str(payload.get("name") or "expected_outcome").strip() or "expected_outcome"
        value = payload["value"]
        caller_id = caller_client_id_var.get() or "dashboard"

        def _log() -> dict[str, Any]:
            import mlflow
            from mlflow.entities.assessment_source import AssessmentSource, AssessmentSourceType

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            assessment = mlflow.log_expectation(
                trace_id=trace_id,
                name=name,
                value=value,
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN,
                    source_id=caller_id,
                ),
            )
            return {
                "logged": True,
                "traceId": trace_id,
                "assessmentId": getattr(assessment, "assessment_id", None),
                "name": name,
                "value": value,
            }

        try:
            return await asyncio.to_thread(_log)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @app.post("/api/v1/traces/{trace_id}/tag", response_model=None)
    async def trace_tag_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        key = str((payload or {}).get("key") or "").strip() if isinstance(payload, dict) else ""
        val = str((payload or {}).get("value") or "").strip() if isinstance(payload, dict) else ""
        if not key:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'key'"}},
            )

        def _tag() -> dict[str, Any]:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            mlflow.set_trace_tag(trace_id=trace_id, key=key, value=val)
            return {"tagged": True, "traceId": trace_id, "key": key, "value": val}

        try:
            return await asyncio.to_thread(_tag)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @app.post("/api/v1/traces/{trace_id}/promote-to-dataset", response_model=None)
    async def trace_promote_to_dataset_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        dataset_name = str(body.get("dataset_name") or GOLDEN_DATASET_NAME).strip()
        expected_outcome = str(body.get("expected_outcome") or "").strip()
        must_contain = body.get("must_contain")

        def _promote() -> dict[str, Any]:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            trace = client.get_trace(trace_id)
            spans = getattr(getattr(trace, "data", None), "spans", None) or []
            if not spans:
                raise ValueError(f"Trace '{trace_id}' has no spans")
            root = spans[0]
            attrs = dict(getattr(root, "attributes", None) or {})
            raw_inputs = getattr(root, "inputs", None)
            inputs_dict = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}

            if {"server", "tool"} <= set(inputs_dict.keys()):
                srv_name = str(inputs_dict["server"])
                tool_name = str(inputs_dict["tool"])
                args_dict = dict(inputs_dict.get("arguments") or {})
            else:
                srv_name = str(attrs.get("mcp.server") or "")
                tool_name = str(attrs.get("mcp.tool") or "")
                span_name = str(getattr(root, "name", "") or "")
                if (not srv_name or not tool_name) and "." in span_name:
                    p_srv, p_tool = span_name.split(".", 1)
                    srv_name = srv_name or p_srv
                    tool_name = tool_name or p_tool
                args_dict = inputs_dict

            if not srv_name or not tool_name:
                raise ValueError("Could not determine 'server' and 'tool' from trace root span")

            outcome = expected_outcome or (
                "policy_refusal" if is_expected_policy_refusal(trace) else "ok"
            )
            expectations: dict[str, Any] = {"expected_outcome": outcome}
            if isinstance(must_contain, str) and must_contain.strip():
                expectations["must_contain"] = must_contain.strip()

            record = {
                "inputs": {
                    "server": srv_name,
                    "tool": tool_name,
                    "arguments": args_dict,
                },
                "expectations": expectations,
            }
            sync_res = sync_golden_dataset(
                settings,
                dataset_name=dataset_name,
                cases=[record],
            )
            mlflow.set_trace_tag(trace_id=trace_id, key="promoted_to_dataset", value=dataset_name)
            return {
                "promoted": True,
                "traceId": trace_id,
                "dataset": sync_res,
                "record": record,
            }

        try:
            return await asyncio.to_thread(_promote)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_TRACE", "message": str(exc)}},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @app.get("/api/v1/mlflow/registry")
    async def mlflow_registry_api() -> dict[str, Any]:
        def _load_registry() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            client = mlflow.MlflowClient(
                tracking_uri=settings.mlflow.tracking_uri,
                registry_uri=settings.effective_mlflow_registry_uri,
            )

            mcp_servers_out: list[dict[str, Any]] = []
            try:
                for srv in client.search_mcp_servers(max_results=50):
                    mcp_servers_out.append(
                        {
                            "name": getattr(srv, "name", None),
                            "url": getattr(srv, "url", None),
                            "version": getattr(srv, "version", None),
                            "description": getattr(srv, "description", None),
                            "aliases": dict(getattr(srv, "aliases", None) or {}),
                            "tags": dict(getattr(srv, "tags", None) or {}),
                        }
                    )
            except Exception:
                pass

            prompts_out: list[dict[str, Any]] = []
            try:
                prompts = mlflow.genai.search_prompts(max_results=30)
                for p in prompts[:20]:
                    p_name = str(getattr(p, "name", ""))
                    versions_out: list[dict[str, Any]] = []
                    try:
                        vers = client.search_prompt_versions(name=p_name, max_results=10)
                        for v in vers:
                            versions_out.append(
                                {
                                    "version": getattr(v, "version", None),
                                    "aliases": list(getattr(v, "aliases", None) or []),
                                    "commitMessage": getattr(v, "commit_message", None),
                                }
                            )
                    except Exception:
                        pass
                    prompts_out.append(
                        {
                            "name": p_name,
                            "description": getattr(p, "description", None),
                            "tags": dict(getattr(p, "tags", None) or {}),
                            "versions": versions_out,
                        }
                    )
            except Exception:
                pass

            reg_models_out: list[dict[str, Any]] = []
            try:
                for m in client.search_registered_models(max_results=30):
                    latest = [
                        {
                            "version": getattr(lv, "version", None),
                            "currentStage": getattr(lv, "current_stage", None),
                            "aliases": list(getattr(lv, "aliases", None) or []),
                        }
                        for lv in (getattr(m, "latest_versions", None) or [])
                    ]
                    reg_models_out.append(
                        {
                            "name": getattr(m, "name", None),
                            "description": getattr(m, "description", None),
                            "aliases": dict(getattr(m, "aliases", None) or {}),
                            "tags": dict(getattr(m, "tags", None) or {}),
                            "latestVersions": latest,
                        }
                    )
            except Exception:
                pass

            logged_models_out: list[dict[str, Any]] = []
            try:
                exp = client.get_experiment_by_name(settings.mlflow.experiment_name)
                if exp is not None:
                    for lm in client.search_logged_models(
                        experiment_ids=[exp.experiment_id], max_results=20
                    ):
                        logged_models_out.append(
                            {
                                "modelId": getattr(lm, "model_id", None),
                                "name": getattr(lm, "name", None),
                                "status": str(getattr(lm, "status", "")),
                                "tags": dict(getattr(lm, "tags", None) or {}),
                                "metrics": [
                                    {
                                        "key": getattr(met, "key", None),
                                        "value": getattr(met, "value", None),
                                    }
                                    for met in (getattr(lm, "metrics", None) or [])
                                ],
                            }
                        )
            except Exception:
                pass

            return {
                "available": True,
                "mutationsEnabled": settings.mlflow.allow_mutations,
                "experiment": settings.mlflow.experiment_name,
                "mcpServers": mcp_servers_out,
                "prompts": prompts_out,
                "registeredModels": reg_models_out,
                "loggedModels": logged_models_out,
            }

        try:
            return await asyncio.to_thread(_load_registry)
        except Exception as exc:
            return {
                "available": False,
                "mutationsEnabled": settings.mlflow.allow_mutations,
                "experiment": settings.mlflow.experiment_name,
                "error": str(exc),
                "mcpServers": [],
                "prompts": [],
                "registeredModels": [],
                "loggedModels": [],
            }

    @app.get("/api/v1/mlflow/prompts/{name}", response_model=None)
    async def mlflow_prompt_detail_api(
        name: str,
        version_or_alias: str = "latest",
    ) -> dict[str, Any] | JSONResponse:
        def _load() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            if version_or_alias.isdigit():
                pv = mlflow.genai.load_prompt(name, version=int(version_or_alias))
            else:
                pv = mlflow.genai.load_prompt(f"prompts:/{name}@{version_or_alias}")
            return {
                "name": getattr(pv, "name", name),
                "version": getattr(pv, "version", None),
                "template": getattr(pv, "template", None),
                "commitMessage": getattr(pv, "commit_message", None),
                "tags": dict(getattr(pv, "tags", None) or {}),
                "uri": getattr(pv, "uri", None),
            }

        try:
            return await asyncio.to_thread(_load)
        except Exception as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "PROMPT_NOT_FOUND", "message": str(exc)}},
            )

    @app.post("/api/v1/mlflow/prompts/{name}/alias", response_model=None)
    async def mlflow_prompt_alias_api(
        name: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": "Set MLFLOW_ALLOW_MUTATIONS=true to update prompt aliases",
                    }
                },
            )
        body = payload if isinstance(payload, dict) else {}
        alias = str(body.get("alias") or "").strip()
        raw_ver = body.get("version")
        if not alias or raw_ver is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'alias' and integer 'version'",
                    }
                },
            )
        version_int = int(raw_ver)

        def _set() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            mlflow.genai.set_prompt_alias(name=name, alias=alias, version=version_int)
            return {"updated": True, "name": name, "alias": alias, "version": version_int}

        try:
            return await asyncio.to_thread(_set)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @app.post("/api/v1/mlflow/models/{name}/alias", response_model=None)
    async def mlflow_model_alias_api(
        name: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": "Set MLFLOW_ALLOW_MUTATIONS=true to update model aliases",
                    }
                },
            )
        body = payload if isinstance(payload, dict) else {}
        alias = str(body.get("alias") or "").strip()
        raw_ver = body.get("version")
        if not alias or raw_ver is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'alias' and 'version'",
                    }
                },
            )
        ver_str = str(raw_ver).strip()

        def _set() -> dict[str, Any]:
            import mlflow

            client = mlflow.MlflowClient(
                tracking_uri=settings.mlflow.tracking_uri,
                registry_uri=settings.effective_mlflow_registry_uri,
            )
            client.set_registered_model_alias(name=name, alias=alias, version=ver_str)
            return {"updated": True, "name": name, "alias": alias, "version": ver_str}

        try:
            return await asyncio.to_thread(_set)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

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

    @app.post("/api/v1/actions/benchmark")
    async def action_benchmark(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        with_judge = (
            False if not isinstance(payload, dict) else bool(payload.get("with_llm_judge", False))
        )
        raw_model = None if not isinstance(payload, dict) else payload.get("judge_model")
        judge_model = str(raw_model).strip() if isinstance(raw_model, str) and raw_model else None
        return await asyncio.to_thread(
            run_golden_benchmark,
            settings,
            with_llm_judge=with_judge,
            judge_model=judge_model,
        )

    @app.post("/api/v1/actions/call-tool", response_model=None)
    async def action_call_tool(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "JSON body required"}},
            )
        raw_server = str(payload.get("server") or "").strip()
        tool_name = str(payload.get("tool") or "").strip()
        arguments = payload.get("arguments")
        if arguments is None:
            arguments = {}
        if not raw_server or not tool_name or not isinstance(arguments, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'server', 'tool', and object 'arguments'",
                    }
                },
            )

        slug = raw_server.replace("_", "-").lower()
        key = slug.replace("-", "_")
        if settings.gateway.effective_auth_enabled:
            policy = caller_client_policy_var.get()
            if not is_server_allowed(policy, slug):
                client_label = policy.client_name if policy else "caller"
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": (
                                f"Client '{client_label}' is not allowed to invoke tools "
                                f"on server '{slug}'"
                            ),
                        }
                    },
                )

        target_srv = upstream_proxy if slug == "mlflow-upstream" else servers.get(key)
        if target_srv is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "SERVER_NOT_FOUND", "message": f"Unknown '{slug}'"}},
            )

        try:
            avail_tools = await asyncio.wait_for(target_srv.list_tools(), timeout=3.0)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "SERVER_UNAVAILABLE", "message": str(exc)}},
            )

        if not any(getattr(t, "name", "") == tool_name for t in avail_tools):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "TOOL_NOT_FOUND",
                        "message": f"Tool '{tool_name}' not found on server '{slug}'",
                    }
                },
            )

        t0 = time.monotonic()
        try:
            tool_res = await asyncio.wait_for(
                target_srv.call_tool(tool_name, arguments=arguments, run_middleware=True),
                timeout=30.0,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            blocks = getattr(tool_res, "content", None) or []
            raw_text = "".join(str(getattr(b, "text", b)) for b in blocks)
            structured = getattr(tool_res, "structured_content", None)
            if not raw_text and structured is not None:
                raw_text = json.dumps(structured, default=str)

            max_chars = 50_000
            truncated = len(raw_text) > max_chars
            clipped = raw_text[:max_chars] if truncated else raw_text
            parsed_out: Any = clipped
            if not truncated:
                try:
                    parsed_out = json.loads(clipped)
                except Exception:
                    parsed_out = clipped

            return {
                "ok": True,
                "policyRefusal": False,
                "server": slug,
                "tool": tool_name,
                "durationMs": elapsed_ms,
                "truncated": truncated,
                "result": parsed_out,
            }
        except ToolError as exc:
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            msg = str(exc)
            is_refusal = any(m in msg.lower() for m in _POLICY_REFUSAL_MARKERS)
            return {
                "ok": False,
                "policyRefusal": is_refusal,
                "server": slug,
                "tool": tool_name,
                "durationMs": elapsed_ms,
                "error": msg,
            }
        except TimeoutError:
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            return JSONResponse(
                status_code=504,
                content={
                    "ok": False,
                    "server": slug,
                    "tool": tool_name,
                    "durationMs": elapsed_ms,
                    "error": "Tool execution timed out after 30s",
                },
            )

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
