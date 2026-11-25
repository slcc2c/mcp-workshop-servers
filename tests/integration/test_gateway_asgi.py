"""ASGI integration tests for the unified FastAPI + FastMCP Streamable HTTP gateway."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from mcp_stack.gateway.app import build_gateway_app

pytestmark = pytest.mark.integration


def _asgi_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


async def test_gateway_health_ready_metrics_and_streamable_http_mcp(make_settings) -> None:
    settings = make_settings()
    settings.gateway.enabled_servers = [
        "unity_catalog",
        "mlflow",
        "memory",
        "filesystem",
        "github",
        "docker",
    ]
    settings.gateway.enable_photos_on_macos = False
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    app = build_gateway_app(settings)
    factory = _asgi_factory(app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http_cli:
            health = await http_cli.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "healthy"

            servers_resp = await http_cli.get("/api/v1/servers")
            assert servers_resp.status_code == 200
            slugs = [s["slug"] for s in servers_resp.json()["servers"]]
            assert {"unity-catalog", "mlflow", "memory", "filesystem", "github", "docker"} <= set(
                slugs
            )

            ready_resp = await http_cli.get("/ready")
            assert ready_resp.status_code == 200
            assert ready_resp.json()["status"] in {"ready", "degraded"}

        # Composed /mcp endpoint via Streamable HTTP
        composed_transport = StreamableHttpTransport(
            "http://testserver/mcp/", httpx_client_factory=factory
        )
        async with Client(composed_transport) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert "uc_list_catalogs" in names
            assert "mlflow_search_logged_models" in names
            assert "mlflow_list_experiments" not in names
            assert "memory_store" in names
            assert "fs_read_file" in names
            assert "github_get_repo" in names
            assert "docker_list_containers" in names

            stored = await client.call_tool(
                "memory_store",
                {"content": "Gateway ASGI smoke entry", "type": "fact", "tags": ["asgi"]},
            )
            entry_id = json.loads(stored.content[0].text)["id"]
            fetched = await client.call_tool("memory_get", {"id": entry_id})
            assert "Gateway ASGI smoke entry" in str(fetched)

        # Isolated /servers/memory/mcp endpoint sees the same persisted SQLite store
        mem_transport = StreamableHttpTransport(
            "http://testserver/servers/memory/mcp/", httpx_client_factory=factory
        )
        async with Client(mem_transport) as mem_client:
            mem_tools = {t.name for t in await mem_client.list_tools()}
            assert "memory_search" in mem_tools
            assert "uc_list_catalogs" not in mem_tools

            searched = await mem_client.call_tool("memory_search", {"query": "Gateway ASGI"})
            assert json.loads(searched.content[0].text)["totalResults"] == 1

        # Isolated /servers/unity-catalog/mcp endpoint
        with respx.mock(assert_all_called=False) as router:
            router.get("http://uc.test:8080/api/2.1/unity-catalog/catalogs").mock(
                return_value=httpx.Response(200, json={"catalogs": [{"name": "unity"}]})
            )
            uc_transport = StreamableHttpTransport(
                "http://testserver/servers/unity-catalog/mcp/",
                httpx_client_factory=factory,
            )
            async with Client(uc_transport) as uc_client:
                res = await uc_client.call_tool("uc_list_catalogs", {})
                assert "unity" in str(res)

        # Metrics endpoint recorded tool calls
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http_cli:
            metrics = await http_cli.get("/metrics")
            assert metrics.status_code == 200
            assert "mcp_tool_calls_total" in metrics.text
