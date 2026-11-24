"""FastAPI + FastMCP unified gateway composing /mcp and isolated /servers/<slug>/mcp routes."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from mcp_stack import __version__
from mcp_stack.core.auth import GatewayAuthMiddleware
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.metrics import render_metrics
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


def _slug_for(server_key: str) -> str:
    return server_key.replace("_", "-")


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
                    logger.info(
                        "Composed upstream mlflow[mcp] into /mcp",
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
            "servers": server_inventory,
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

    @app.get("/metrics")
    async def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    app.mount("/mcp", composed_http)
    for slug, sub_http in per_server_http.items():
        app.mount(f"/servers/{slug}/mcp", sub_http)

    # Pure ASGI middlewares (outermost executes first)
    app.add_middleware(GatewayAuthMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.gateway.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
