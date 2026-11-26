"""Tests for Gateway meta-tools, MCP resources, MLflow prompt bridge, and admin APIs."""

from __future__ import annotations

import json
import types
from pathlib import Path

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.tools.tool import ToolResult
from mcp.types import ImageContent, TextContent

from mcp_stack.client_configs import generate_client_configs, install_client_configs
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.servers.gateway_meta import MLflowPromptRegistryProvider, create_gateway_meta_server

pytestmark = pytest.mark.unit


def _asgi_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        kwargs["follow_redirects"] = False
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


async def test_gateway_meta_tools_resources_and_mlflow_prompt_bridge(
    make_settings, monkeypatch
) -> None:
    settings = make_settings()
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    fake_pv = types.SimpleNamespace(
        name="ai-assist",
        version=2,
        template="Summarize {{topic}} cleanly.\nKeep {{tone}} tone.",
        commit_message="v2 refinement",
    )
    fake_genai = types.SimpleNamespace(
        search_prompts=lambda max_results=50: [
            types.SimpleNamespace(name="ai-assist", latest_version=2, aliases=["production"])
        ],
        load_prompt=lambda ref: fake_pv,
    )
    fake_mlflow = types.SimpleNamespace(set_tracking_uri=lambda uri: None, genai=fake_genai)

    prompt_provider = MLflowPromptRegistryProvider(settings, ttl_s=60.0, mlflow_module=fake_mlflow)
    prompts = await prompt_provider.list_prompts()
    assert len(prompts) == 1
    assert prompts[0].name == "ai-assist"
    assert [a.name for a in (prompts[0].arguments or [])] == ["topic", "tone"]
    rendered = await prompts[0].render({"topic": "MCP gateway", "tone": "crisp"})
    text_body = getattr(rendered.messages[0].content, "text", str(rendered.messages[0].content))
    assert "Summarize MCP gateway cleanly.\nKeep crisp tone." in text_body

    # Also test full MCP tool/resource surface via FastMCP Client on /servers/gateway/mcp
    app = build_gateway_app(settings)
    factory = _asgi_factory(app)
    async with (
        app.router.lifespan_context(app),
        Client(
            StreamableHttpTransport(
                "http://testserver/servers/gateway/mcp", httpx_client_factory=factory
            )
        ) as gw_cli,
    ):
            tools = {t.name for t in await gw_cli.list_tools()}
            assert "gateway_health" in tools
            assert "gateway_list_servers" in tools
            assert "gateway_search_tools" in tools
            assert "gateway_list_profiles" in tools

            search_res = await gw_cli.call_tool("gateway_search_tools", {"query": "memory"})
            search_data = json.loads(str(search_res.content[0].text))
            assert search_data["count"] >= 1
            assert any(item["server"] == "memory" for item in search_data["tools"])

            resources = {str(r.uri) for r in await gw_cli.list_resources()}
            assert "gateway://status" in resources
            assert "gateway://servers" in resources
            assert "gateway://profiles" in resources

            cfg_read = await gw_cli.read_resource("gateway://client-configs/antigravity")
            assert "mcp-workshop-gateway" in str(cfg_read[0].text)

            # Policy-gated admin mutation should refuse when disabled
            refusal = await gw_cli.call_tool(
                "gateway_toggle_upstream",
                {"slug": "printer", "enabled": False},
                raise_on_error=False,
            )
            assert refusal.is_error is True
            assert "POLICY_REFUSAL" in str(refusal.content[0].text)


async def test_meta_server_provider_direct_mcp_prompts_listing(make_settings) -> None:
    settings = make_settings()
    fake_pv = types.SimpleNamespace(
        name="receipt-writer",
        version=1,
        template="Line: {{line}}",
        commit_message="initial",
    )
    fake_mlflow = types.SimpleNamespace(
        set_tracking_uri=lambda uri: None,
        genai=types.SimpleNamespace(
            search_prompts=lambda max_results=50: [
                types.SimpleNamespace(name="receipt-writer", latest_version=1, aliases=[])
            ],
            load_prompt=lambda ref: fake_pv,
        ),
    )
    provider = MLflowPromptRegistryProvider(settings, mlflow_module=fake_mlflow)
    meta_srv = create_gateway_meta_server(
        settings,
        lambda: {"servers": [], "profiles": [], "server_instances": {}, "settings": settings},
        prompt_provider=provider,
    )
    async with Client(meta_srv) as cli:
        mcp_prompts = await cli.list_prompts()
        assert [p.name for p in mcp_prompts] == ["receipt-writer"]
        got = await cli.get_prompt("receipt-writer", {"line": "hello thermal"})
        assert "Line: hello thermal" in str(got.messages[0].content.text)


async def test_rich_content_blocks_upstreams_admin_and_client_configs(
    make_settings, monkeypatch, tmp_path: Path
) -> None:
    local_yaml = tmp_path / "gateway.local.yaml"
    monkeypatch.setenv("MCP_LOCAL_CONFIG_PATH", str(local_yaml))

    rich_srv = FastMCP("printer-mock")

    @rich_srv.tool(name="today_mock")
    def today_mock() -> ToolResult:
        return ToolResult(
            content=[
                TextContent(type="text", text="Wednesday 25 November\nToday printed at 8:30 am."),
                ImageContent(type="image", data="iVBORw0KGgo=", mimeType="image/png"),
            ],
            structured_content={"date": "2026-11-25"},
        )

    settings = make_settings()
    settings.gateway.enabled_servers = ["memory"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False
    app = build_gateway_app(settings, server_overrides={"memory": rich_srv})

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http_cli,
    ):
            # Rich content blocks preserve newlines + inline image separately from text
            call_res = await http_cli.post(
                "/api/v1/actions/call-tool",
                json={"server": "memory", "tool": "today_mock", "arguments": {}},
            )
            assert call_res.status_code == 200
            payload = call_res.json()
            assert payload["ok"] is True
            assert payload["result"] == "Wednesday 25 November\nToday printed at 8:30 am."
            assert payload["structuredContent"] == {"date": "2026-11-25"}
            assert payload["contentBlocks"][0]["type"] == "text"
            assert payload["contentBlocks"][1] == {
                "type": "image",
                "mimeType": "image/png",
                "data": "iVBORw0KGgo=",
            }

            # Raw secret rejected on upstream create
            bad_up = await http_cli.post(
                "/api/v1/upstreams",
                json={
                    "slug": "linear-test",
                    "transport": "http",
                    "url": "https://mcp.linear.app/mcp",
                    "headers": {"Authorization": "Bearer lin_api_rawsecret123456"},
                },
            )
            assert bad_up.status_code == 400
            assert bad_up.json()["error"]["code"] == "RAW_SECRET_REJECTED"

            # env: secret ref succeeds and writes atomically
            good_up = await http_cli.post(
                "/api/v1/upstreams",
                json={
                    "slug": "linear-test",
                    "transport": "http",
                    "url": "https://mcp.linear.app/mcp",
                    "headers": {"Authorization": "Bearer env:LINEAR_API_KEY"},
                    "profiles": ["studio"],
                },
            )
            assert good_up.status_code == 200
            assert local_yaml.exists()
            saved_text = local_yaml.read_text(encoding="utf-8")
            assert "env:LINEAR_API_KEY" in saved_text

            # Prompt authoring gated when MLFLOW_ALLOW_MUTATIONS=false
            prompt_res = await http_cli.post(
                "/api/v1/mlflow/prompts",
                json={"name": "test", "template": "Hi {{name}}"},
            )
            assert prompt_res.status_code == 403

            # Client onboarding API returns all 6 clients
            cli_res = await http_cli.get("/api/v1/clients/configs?profile=discover")
            assert cli_res.status_code == 200
            configs = cli_res.json()["configs"]
            expected_clients = {
                "antigravity",
                "codex",
                "claude-code",
                "claude-desktop",
                "cursor",
                "gemini-cli",
            }
            assert expected_clients <= set(configs)
            assert "/profiles/discover/mcp" in configs["antigravity"]

    # Test dry-run client install for new targets
    install_res = install_client_configs(
        settings,
        tmp_path,
        clients=["antigravity", "gemini-cli", "cursor"],
        profile="studio",
        dry_run=True,
        home_dir=tmp_path,
    )
    assert set(install_res["results"]) == {"antigravity", "gemini-cli", "cursor"}
    assert "mcp-workshop-gateway" in generate_client_configs(settings, tmp_path)["gemini-cli"]
