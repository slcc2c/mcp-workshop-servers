"""FastAPI + FastMCP unified gateway composing /mcp and isolated /servers/<slug>/mcp routes."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack import __version__
from mcp_stack.core.auth import GatewayAuthMiddleware, LoginNonceStore
from mcp_stack.core.config import MCPStackSettings, UpstreamServerConfig
from mcp_stack.core.logging import get_logger
from mcp_stack.evals import (  # noqa: F401
    run_golden_benchmark,
    run_trace_evaluation,
    sync_golden_dataset,
)
from mcp_stack.gateway.dashboard import get_static_dir, has_built_dashboard, render_dashboard_html
from mcp_stack.gateway.presets import PresetStore
from mcp_stack.gateway.routes_agent import build_agent_router
from mcp_stack.gateway.routes_auth import build_auth_router, maybe_mint_trusted_ui_session
from mcp_stack.gateway.routes_clients_skills import build_clients_skills_router
from mcp_stack.gateway.routes_evals import build_evals_router
from mcp_stack.gateway.routes_mlflow import build_mlflow_router
from mcp_stack.gateway.routes_ops import build_ops_router
from mcp_stack.gateway.routes_skills_registry import build_skills_registry_router
from mcp_stack.gateway.routes_tools import build_tools_router
from mcp_stack.gateway.routes_upstreams import build_upstreams_router
from mcp_stack.gateway.state import GatewayRuntimeState, slug_for
from mcp_stack.gateway.upstreams import build_upstream_proxy, probe_upstream_proxy
from mcp_stack.servers.docker_server import create_docker_server
from mcp_stack.servers.filesystem import create_filesystem_server
from mcp_stack.servers.gateway_meta import (
    MLflowPromptRegistryProvider,
    create_gateway_meta_server,
)
from mcp_stack.servers.github import create_github_server
from mcp_stack.servers.jupyter_server import create_jupyter_server
from mcp_stack.servers.kubernetes_server import create_kubernetes_server
from mcp_stack.servers.mac_mini import create_mac_mini_server
from mcp_stack.servers.memory import create_memory_server
from mcp_stack.servers.mlflow_server import (
    create_mlflow_server,
    create_mlflow_upstream_proxy,
    probe_mcp_http_endpoint,
)
from mcp_stack.servers.mongodb import create_mongodb_server
from mcp_stack.servers.neo4j_server import create_neo4j_server
from mcp_stack.servers.omnigent import create_omnigent_server
from mcp_stack.servers.photos import create_photos_server
from mcp_stack.servers.postgresql import create_postgresql_server
from mcp_stack.servers.redis_server import create_redis_server
from mcp_stack.servers.unity_catalog import (
    UCClientAdapter,
    create_unity_catalog_server,
    sync_uc_function_tools,
)
from mcp_stack.servers.xcodebuild import create_xcodebuild_server
from mcp_stack.watchdog import run_watchdog_once  # noqa: F401

_slug_for = slug_for


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


class DynamicProfilesASGI:
    """Route /profiles/<name>/mcp requests dynamically from live state.profile_http."""

    def __init__(self, state: GatewayRuntimeState) -> None:
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        raw_path = str(scope.get("path", "") or "")
        rel_path = raw_path[len("/profiles") :] if raw_path.startswith("/profiles/") else raw_path
        parts = [p for p in rel_path.split("/") if p]
        if len(parts) >= 2 and parts[1] == "mcp":
            pname = parts[0]
            target_app = self.state.profile_http.get(pname)
            if target_app is not None:
                prefix = f"/{pname}/mcp"
                rem = rel_path[len(prefix) :] if rel_path.startswith(prefix) else "/"
                if not rem:
                    rem = "/"
                sub_scope = dict(scope)
                sub_scope["path"] = rem
                sub_scope["raw_path"] = rem.encode("utf-8")
                sub_scope["root_path"] = f"/profiles/{pname}/mcp"
                await target_app(sub_scope, receive, send)
                return
        resp = JSONResponse(
            status_code=404,
            content={"error": {"code": "PROFILE_NOT_FOUND", "message": "Unknown MCP profile"}},
        )
        await resp(scope, receive, send)


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
    if normalized == "omnigent":
        return create_omnigent_server(settings), None
    if normalized == "mac_mini":
        return create_mac_mini_server(settings), None
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

    meta_prompt_provider = MLflowPromptRegistryProvider(settings)
    preset_store = PresetStore(settings.gateway.presets_path)
    upstream_proxy: FastMCP | None = None
    if settings.mlflow.proxy_upstream_mcp:
        factory = upstream_proxy_factory or create_mlflow_upstream_proxy
        upstream_proxy = factory(settings)

    federated_proxies: dict[str, FastMCP] = {}
    federated_meta: dict[str, dict[str, Any]] = {}
    federated_cfg_map: dict[str, UpstreamServerConfig] = {}
    server_inventory: list[dict[str, Any]] = []
    profile_inventory: list[dict[str, Any]] = []
    profile_apps: dict[str, FastMCP] = {}
    profile_http: dict[str, Any] = {}
    login_nonces = LoginNonceStore()

    state = GatewayRuntimeState(
        settings=settings,
        logger=logger,
        servers=servers,
        uc_adapter=uc_adapter,
        upstream_proxy=upstream_proxy,
        federated_proxies=federated_proxies,
        federated_meta=federated_meta,
        federated_cfg_map=federated_cfg_map,
        server_inventory=server_inventory,
        profile_inventory=profile_inventory,
        profile_apps=profile_apps,
        profile_http=profile_http,
        meta_prompt_provider=meta_prompt_provider,
        preset_store=preset_store,
        login_nonces=login_nonces,
    )

    gateway_meta_server = create_gateway_meta_server(
        settings,
        state.meta_state_snapshot,
        prompt_provider=meta_prompt_provider,
    )
    servers["gateway"] = gateway_meta_server

    composed = FastMCP("mcp-workshop-gateway")
    for _key, srv in servers.items():
        composed.mount(srv)

    for raw_up_name, up_cfg in settings.gateway.upstream_servers.items():
        proxy_srv, up_info = build_upstream_proxy(
            raw_up_name, up_cfg, settings, resolver=state.secret_resolver
        )
        slug = str(up_info["slug"])
        federated_meta[slug] = up_info
        federated_cfg_map[slug] = up_cfg
        if proxy_srv is not None:
            federated_proxies[slug] = proxy_srv

    composed_http = composed.http_app(path="/")
    per_server_http: dict[str, Any] = {
        slug_for(key): srv.http_app(path="/") for key, srv in servers.items()
    }
    if upstream_proxy is not None:
        per_server_http["mlflow-upstream"] = upstream_proxy.http_app(path="/")
    for fed_slug, fed_proxy in federated_proxies.items():
        per_server_http[fed_slug] = fed_proxy.http_app(path="/")

    effective_profiles: dict[str, list[str]] = {
        k: list(v) for k, v in settings.gateway.profiles.items()
    }
    for fed_slug, up_cfg in federated_cfg_map.items():
        if not up_cfg.enabled:
            continue
        for pname in up_cfg.profiles:
            clean_p = pname.strip()
            if not clean_p:
                continue
            members = effective_profiles.setdefault(clean_p, [])
            if fed_slug not in members and fed_slug.replace("-", "_") not in members:
                members.append(fed_slug)

    profile_wants_upstream: dict[str, bool] = {}
    profile_wants_federated: dict[str, list[str]] = {}
    for profile_name, raw_members in effective_profiles.items():
        clean_profile = profile_name.strip()
        if not clean_profile:
            continue
        p_mcp = FastMCP(f"mcp-profile-{clean_profile}")
        resolved_slugs: list[str] = []
        wants_upstream = False
        wants_fed: list[str] = []
        for member in raw_members:
            norm = member.strip().replace("-", "_")
            fed_slug_cand = member.strip().replace("_", "-").lower()
            if norm == "mlflow_upstream":
                if upstream_proxy is not None:
                    wants_upstream = True
                continue
            if norm in servers:
                p_mcp.mount(servers[norm])
                resolved_slugs.append(slug_for(norm))
            elif fed_slug_cand in federated_proxies:
                wants_fed.append(fed_slug_cand)
                resolved_slugs.append(fed_slug_cand)
        profile_apps[clean_profile] = p_mcp
        profile_http[clean_profile] = p_mcp.http_app(path="/")
        profile_wants_upstream[clean_profile] = wants_upstream
        profile_wants_federated[clean_profile] = wants_fed
        profile_inventory.append(
            {
                "name": clean_profile,
                "route": f"/profiles/{clean_profile}/mcp",
                "servers": resolved_slugs,
                "includesUpstreamMcp": wants_upstream,
                "builtin": clean_profile in {"discover", "core", "data", "ops", "macos"},
            }
        )

    server_inventory.extend(
        {
            "key": key,
            "slug": slug_for(key),
            "route": f"/servers/{slug_for(key)}/mcp",
            "status": "enabled",
            "connectionStatus": "connected",
            "external": False,
        }
        for key in servers
    )
    if upstream_proxy is not None:
        server_inventory.append(
            {
                "key": "mlflow_upstream",
                "slug": "mlflow-upstream",
                "route": "/servers/mlflow-upstream/mcp",
                "status": "proxy",
                "connectionStatus": "configured",
                "external": True,
                "target": settings.mlflow.mcp_url,
            }
        )
    for _fed_slug, meta in federated_meta.items():
        server_inventory.append(meta)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state.app_ref = app
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
                state.upstream_composed = bool(should_compose)
                inv_up = next(
                    (s for s in server_inventory if s["slug"] == "mlflow-upstream"), None
                )
                if inv_up is not None:
                    inv_up["connectionStatus"] = "connected" if should_compose else "unreachable"
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

            for _slug, sub_http in per_server_http.items():
                await stack.enter_async_context(sub_http.lifespan(app))

            if federated_proxies:
                async def _probe_one(f_slug: str, f_proxy: FastMCP) -> tuple[str, dict[str, Any]]:
                    cfg_obj = federated_cfg_map[f_slug]
                    return f_slug, await probe_upstream_proxy(
                        f_proxy,
                        timeout_s=cfg_obj.timeout_s,
                        allow_tools=cfg_obj.allow_tools,
                        deny_tools=cfg_obj.deny_tools,
                    )

                probe_results = await asyncio.gather(
                    *(_probe_one(s, p) for s, p in federated_proxies.items())
                )
                for f_slug, f_res in probe_results:
                    meta_ref = federated_meta[f_slug]
                    meta_ref["connectionStatus"] = f_res["connectionStatus"]
                    meta_ref["toolCount"] = f_res.get("toolCount", 0)
                    meta_ref["rawToolCount"] = f_res.get("rawToolCount", meta_ref["toolCount"])
                    meta_ref["exposedToolCount"] = f_res.get(
                        "exposedToolCount", meta_ref["toolCount"]
                    )
                    meta_ref["filteredOutCount"] = f_res.get("filteredOutCount", 0)
                    meta_ref["sampleTools"] = list(
                        f_res.get("sampleTools") or f_res.get("tools", [])[:5]
                    )
                    if f_res.get("error"):
                        meta_ref["error"] = f_res["error"]
                    if f_res.get("reachable"):
                        f_cfg = federated_cfg_map[f_slug]
                        f_proxy = federated_proxies[f_slug]
                        if f_cfg.compose_into_full:
                            composed.mount(f_proxy)
                        for pname, p_mcp in profile_apps.items():
                            if f_slug in profile_wants_federated.get(pname, []):
                                p_mcp.mount(f_proxy)
                        logger.info(
                            "Federated external MCP proxy",
                            server=f_slug,
                            tools=f_res.get("toolCount", 0),
                        )
                    else:
                        logger.warning(
                            "External MCP proxy unreachable at startup",
                            server=f_slug,
                            error=f_res.get("error"),
                        )

            await stack.enter_async_context(composed_http.lifespan(app))
            for _pname, p_http in list(profile_http.items()):
                await stack.enter_async_context(p_http.lifespan(app))
            try:
                yield
            finally:
                for p_runner in list(state.profile_runners.values()):
                    await p_runner.stop()
                state.profile_runners.clear()

    app = FastAPI(
        title="MCP Workshop Stack Gateway",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.login_nonces = login_nonces
    app.state.gateway_state = state

    app.include_router(build_auth_router(state))
    app.include_router(build_ops_router(state))
    app.include_router(build_tools_router(state))
    app.include_router(build_mlflow_router(state))
    app.include_router(build_evals_router(state))
    app.include_router(build_upstreams_router(state))
    app.include_router(build_clients_skills_router(state))
    app.include_router(build_skills_registry_router(state))
    app.include_router(build_agent_router(state))

    if has_built_dashboard():
        static_root = get_static_dir().resolve()
        assets_dir = static_root / "assets"
        if assets_dir.is_dir():
            app.mount("/ui/assets", StaticFiles(directory=str(assets_dir)), name="ui-assets")

    @app.get("/ui/{subpath:path}", response_model=None)
    async def dashboard_ui_subpath(subpath: str, request: Request) -> Response:
        static_root = get_static_dir().resolve()
        if subpath and has_built_dashboard(static_root):
            candidate = (static_root / subpath).resolve()
            if candidate.is_relative_to(static_root) and candidate.is_file():
                return FileResponse(candidate)
        resp = HTMLResponse(
            content=render_dashboard_html(__version__, static_dir=static_root),
            headers={"Cache-Control": "no-store"},
        )
        maybe_mint_trusted_ui_session(state, request, resp)
        return resp

    app.mount("/mcp", composed_http)
    for slug, sub_http in per_server_http.items():
        app.mount(f"/servers/{slug}/mcp", sub_http)
    app.mount("/profiles", DynamicProfilesASGI(state))

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
