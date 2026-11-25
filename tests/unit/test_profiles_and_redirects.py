"""Tests for curated toolset profiles, zero-307 routing, and profile auth allowlists."""

from __future__ import annotations

import json
import sys

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from mcp_stack.core.config import ClientPolicy, load_settings
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.registry import build_server_manifests


def _asgi_no_redirect_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        kwargs["follow_redirects"] = False
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


async def test_zero_307_redirects_and_curated_profile_tool_counts(
    make_settings, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    settings = make_settings()
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False
    app = build_gateway_app(settings)
    factory = _asgi_no_redirect_factory(app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as http_cli:
            prof_resp = await http_cli.get("/api/v1/profiles")
            assert prof_resp.status_code == 200
            body = prof_resp.json()
            assert body["defaultProfile"] == "core"
            assert {p["name"] for p in body["profiles"]} == {"core", "data", "ops", "macos"}

        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/core/mcp", httpx_client_factory=factory
            )
        ) as core_cli:
            core_tools = {t.name for t in await core_cli.list_tools()}
            assert "uc_list_catalogs" in core_tools
            assert "mlflow_search_logged_models" in core_tools
            assert "mlflow_list_experiments" not in core_tools
            assert "memory_store" in core_tools
            assert "postgres_query" not in core_tools
            assert "k8s_list_pods" not in core_tools
            assert "xcode_discover_projects" not in core_tools

        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/data/mcp", httpx_client_factory=factory
            )
        ) as data_cli:
            data_tools = {t.name for t in await data_cli.list_tools()}
            assert "postgres_query" in data_tools
            assert "redis_get" in data_tools
            assert "memory_store" not in data_tools

        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/ops/mcp", httpx_client_factory=factory
            )
        ) as ops_cli:
            ops_tools = {t.name for t in await ops_cli.list_tools()}
            assert "docker_list_containers" in ops_tools
            assert "k8s_list_pods" in ops_tools
            assert "postgres_query" not in ops_tools

        async with Client(
            StreamableHttpTransport("http://testserver/mcp", httpx_client_factory=factory)
        ) as full_cli:
            full_tools = {t.name for t in await full_cli.list_tools()}
            assert len(full_tools) > len(core_tools)
            assert "postgres_query" in full_tools
            assert "k8s_list_pods" in full_tools

        async with Client(
            StreamableHttpTransport(
                "http://testserver/servers/memory/mcp", httpx_client_factory=factory
            )
        ) as mem_cli:
            mem_res = await mem_cli.call_tool("memory_list_tags", {})
            assert mem_res.is_error is False


async def test_profile_auth_allowlist_and_env_override(make_settings, monkeypatch) -> None:
    monkeypatch.setenv("MCP_DEFAULT_CLIENT_PROFILE", "ops")
    monkeypatch.setenv("MCP_PROFILES_JSON", json.dumps({"mini": ["memory", "filesystem"]}))
    overridden = load_settings(load_dotenv=False)
    assert overridden.gateway.default_client_profile == "ops"
    assert list(overridden.gateway.profiles.keys()) == ["mini"]
    assert "profile-mini" in build_server_manifests(overridden)

    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        "restricted-token": ClientPolicy(
            client_id="limited",
            client_name="Limited Client",
            allowed_servers=["memory", "filesystem", "github", "unity_catalog", "mlflow"],
        )
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False
    app = build_gateway_app(settings)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as http_cli,
    ):
        # Restricted client allows all servers in core, but NOT docker/k8s in ops
        ops_resp = await http_cli.post(
            "/profiles/ops/mcp",
            headers={"Authorization": "Bearer restricted-token"},
            json={"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}},
        )
        assert ops_resp.status_code == 403
        assert ops_resp.json()["error"]["code"] == "FORBIDDEN"

        core_resp = await http_cli.post(
            "/profiles/core/mcp",
            headers={
                "Authorization": "Bearer restricted-token",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1.0"},
                },
            },
        )
        assert core_resp.status_code == 200
