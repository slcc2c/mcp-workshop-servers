"""ASGI unit tests for the Gateway /ui dashboard and /api/v1 operational endpoints."""

from __future__ import annotations

import httpx

from mcp_stack.core.config import ClientPolicy
from mcp_stack.gateway.app import build_gateway_app


async def test_dashboard_ui_serves_html_without_secrets(make_settings) -> None:
    secret_tok = "tok_secret_ui_should_never_appear"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        secret_tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    app = build_gateway_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        ui = await cli.get("/ui")
        assert ui.status_code == 200
        assert "text/html" in ui.headers["content-type"]
        assert "MCP Workshop Stack Gateway" in ui.text
        assert secret_tok not in ui.text

        for protected_get in ("/api/v1/tools", "/api/v1/watchdog", "/api/v1/traces"):
            unauth = await cli.get(protected_get)
            assert unauth.status_code == 401

        for protected_post in (
            "/api/v1/actions/refresh-uc",
            "/api/v1/actions/watchdog",
            "/api/v1/actions/eval",
        ):
            unauth_post = await cli.post(protected_post, json={})
            assert unauth_post.status_code == 401


async def test_api_v1_tools_watchdog_traces_and_actions_with_bearer(
    make_settings, monkeypatch
) -> None:
    tok = "tok_valid_dashboard_123"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    monkeypatch.setattr(
        "mcp_stack.gateway.app.run_watchdog_once",
        lambda _settings, dry_run=True: {"overall": "healthy", "dry_run": dry_run},
    )
    monkeypatch.setattr(
        "mcp_stack.gateway.app.run_trace_evaluation",
        lambda _settings, limit=20: {"status": "completed", "trace_count": limit, "metrics": {}},
    )

    app = build_gateway_app(settings)
    headers = {"Authorization": f"Bearer {tok}"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        tools_res = await cli.get(
            "/api/v1/tools", params={"server": "memory", "q": "store"}, headers=headers
        )
        assert tools_res.status_code == 200
        payload = tools_res.json()
        assert payload["totalTools"] >= 1
        assert any(t["name"] == "memory_store" for t in payload["tools"])
        assert "core" in payload["profileCounts"]

        wd_res = await cli.get("/api/v1/watchdog", headers=headers)
        assert wd_res.status_code == 200
        assert "components" in wd_res.json()

        tr_res = await cli.get("/api/v1/traces", headers=headers)
        assert tr_res.status_code == 200
        assert "traces" in tr_res.json()

        act_uc = await cli.post("/api/v1/actions/refresh-uc", json={}, headers=headers)
        assert act_uc.status_code == 200
        assert act_uc.json()["status"] == "skipped"

        act_wd = await cli.post(
            "/api/v1/actions/watchdog", json={"dry_run": True}, headers=headers
        )
        assert act_wd.status_code == 200
        assert act_wd.json()["overall"] == "healthy"

        act_ev = await cli.post("/api/v1/actions/eval", json={"limit": 5}, headers=headers)
        assert act_ev.status_code == 200
        assert act_ev.json()["trace_count"] == 5