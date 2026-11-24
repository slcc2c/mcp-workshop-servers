"""ASGI unit tests for the Gateway /ui dashboard and /api/v1 operational endpoints."""

from __future__ import annotations

import types

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
        for marker in ("playground-card", "bench-btn", "auto-refresh-select", "trace-detail-box"):
            assert marker in ui.text
        assert secret_tok not in ui.text

        for protected_get in (
            "/api/v1/profiles",
            "/api/v1/tools",
            "/api/v1/watchdog",
            "/api/v1/traces",
            "/api/v1/traces/tr-123",
        ):
            unauth = await cli.get(protected_get)
            assert unauth.status_code == 401

        for protected_post in (
            "/api/v1/actions/refresh-uc",
            "/api/v1/actions/watchdog",
            "/api/v1/actions/eval",
            "/api/v1/actions/benchmark",
            "/api/v1/actions/call-tool",
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
    monkeypatch.setattr(
        "mcp_stack.gateway.app.run_golden_benchmark",
        lambda _settings, with_llm_judge=False, judge_model=None: {
            "status": "completed",
            "with_llm_judge": with_llm_judge,
            "judge_model": judge_model,
            "metrics": {"tool_execution_success/mean": 1.0},
        },
    )

    app = build_gateway_app(settings)
    headers = {"Authorization": f"Bearer {tok}"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        prof_res = await cli.get("/api/v1/profiles", headers=headers)
        assert prof_res.status_code == 200
        snippets = prof_res.json()["clientSnippets"]
        assert "codex" in snippets
        assert tok not in str(snippets)

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

        act_bench = await cli.post(
            "/api/v1/actions/benchmark", json={"with_llm_judge": False}, headers=headers
        )
        assert act_bench.status_code == 200
        assert act_bench.json()["metrics"]["tool_execution_success/mean"] == 1.0


async def test_playground_call_tool_allowlist_execution_and_trace_detail(
    make_settings, monkeypatch
) -> None:
    restricted_tok = "tok_mem_only_987"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        restricted_tok: ClientPolicy(
            client_id="openai", client_name="Restricted", allowed_servers=["memory"]
        )
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    fake_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(
            trace_id="tr-demo-1",
            state="OK",
            execution_duration=18.5,
            timestamp_ms=1700000000000,
            assessments=[
                types.SimpleNamespace(
                    name="tool_execution_success",
                    feedback=types.SimpleNamespace(value=True),
                    rationale="Trace OK",
                )
            ],
        ),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    span_id="sp-1",
                    parent_id=None,
                    name="memory.memory_store",
                    span_type="TOOL",
                    status="OK",
                    start_time_ns=1_000_000,
                    end_time_ns=19_500_000,
                    inputs={"content": "hello"},
                    outputs={"stored": True},
                    events=[
                        types.SimpleNamespace(
                            name="log",
                            attributes={"exception.stacktrace": "should-be-stripped", "ok": True},
                        )
                    ],
                )
            ]
        ),
    )

    class FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def get_trace(self, trace_id: str):
            assert trace_id == "tr-demo-1"
            return fake_trace

    import mlflow

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)

    app = build_gateway_app(settings)
    headers = {"Authorization": f"Bearer {restricted_tok}"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        # Allowed server tool call succeeds
        ok_call = await cli.post(
            "/api/v1/actions/call-tool",
            json={
                "server": "memory",
                "tool": "memory_store",
                "arguments": {"content": "Playground test note", "type": "fact"},
            },
            headers=headers,
        )
        assert ok_call.status_code == 200
        ok_body = ok_call.json()
        assert ok_body["ok"] is True
        assert ok_body["result"]["stored"] is True

        # Disallowed server rejected with 403 FORBIDDEN
        blocked = await cli.post(
            "/api/v1/actions/call-tool",
            json={
                "server": "filesystem",
                "tool": "fs_read_file",
                "arguments": {"path": "/etc/passwd"},
            },
            headers=headers,
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "FORBIDDEN"

        # Trace drilldown returns sanitized spans & assessments
        detail = await cli.get("/api/v1/traces/tr-demo-1", headers=headers)
        assert detail.status_code == 200
        d_body = detail.json()
        assert d_body["traceId"] == "tr-demo-1"
        assert d_body["spans"][0]["durationMs"] == 18.5
        assert "exception.stacktrace" not in str(d_body["spans"][0]["events"])
        assert d_body["assessments"][0]["name"] == "tool_execution_success"

    # Also verify read-only sandbox refusal returns ok=False, policyRefusal=True when allowed
    open_tok = "tok_all_999"
    settings.gateway.clients[open_tok] = ClientPolicy(
        client_id="codex", client_name="Codex", allowed_servers=["*"]
    )
    app_open = build_gateway_app(settings)
    async with app_open.router.lifespan_context(app_open), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_open), base_url="http://testserver"
    ) as cli2:
        refusal = await cli2.post(
            "/api/v1/actions/call-tool",
            json={
                "server": "filesystem",
                "tool": "fs_read_file",
                "arguments": {"path": "/etc/passwd"},
            },
            headers={"Authorization": f"Bearer {open_tok}"},
        )
        assert refusal.status_code == 200
        r_body = refusal.json()
        assert r_body["ok"] is False
        assert r_body["policyRefusal"] is True