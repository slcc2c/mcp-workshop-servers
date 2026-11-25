"""ASGI unit tests for the Gateway /ui dashboard and /api/v1 operational endpoints."""

from __future__ import annotations

import json
import types

import httpx
from typer.testing import CliRunner

from mcp_stack.cli import app as cli_app
from mcp_stack.core.auth import UI_SESSION_COOKIE
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


async def test_trace_feedback_expectation_tag_and_dataset_promotion(
    make_settings, monkeypatch
) -> None:
    tok = "tok_curator_456"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    logged: dict[str, list] = {"feedback": [], "expectation": [], "tag": [], "dataset": []}

    import mlflow

    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _u: None)
    monkeypatch.setattr(
        mlflow,
        "log_feedback",
        lambda **kw: logged["feedback"].append(kw) or types.SimpleNamespace(assessment_id="a-1"),
    )
    monkeypatch.setattr(
        mlflow,
        "log_expectation",
        lambda **kw: logged["expectation"].append(kw)
        or types.SimpleNamespace(assessment_id="a-2"),
    )
    monkeypatch.setattr(mlflow, "set_trace_tag", lambda **kw: logged["tag"].append(kw))

    class FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def get_trace(self, trace_id: str):
            return types.SimpleNamespace(
                info=types.SimpleNamespace(state="OK", trace_id=trace_id),
                data=types.SimpleNamespace(
                    spans=[
                        types.SimpleNamespace(
                            name="memory.memory_store",
                            attributes={"mcp.server": "memory", "mcp.tool": "memory_store"},
                            inputs={"content": "promoted entry"},
                            outputs={"stored": True},
                            events=[],
                        )
                    ]
                ),
            )

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    monkeypatch.setattr(
        "mcp_stack.gateway.app.sync_golden_dataset",
        lambda _s, dataset_name, cases: logged["dataset"].append((dataset_name, cases))
        or {"status": "updated", "dataset_name": dataset_name, "record_count": len(cases)},
    )

    app = build_gateway_app(settings)
    headers = {"Authorization": f"Bearer {tok}"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        # Requires Bearer auth
        assert (
            await cli.post("/api/v1/traces/tr-1/feedback", json={"value": "yes"})
        ).status_code == 401

        fb = await cli.post(
            "/api/v1/traces/tr-1/feedback",
            json={"name": "human_quality", "value": "yes", "rationale": "Clean output"},
            headers=headers,
        )
        assert fb.status_code == 200
        assert logged["feedback"][0]["source"].source_id == "codex"

        ex = await cli.post(
            "/api/v1/traces/tr-1/expectation",
            json={"name": "expected_outcome", "value": "ok"},
            headers=headers,
        )
        assert ex.status_code == 200
        assert logged["expectation"][0]["value"] == "ok"

        tg = await cli.post(
            "/api/v1/traces/tr-1/tag",
            json={"key": "reviewed", "value": "true"},
            headers=headers,
        )
        assert tg.status_code == 200
        assert logged["tag"][0]["key"] == "reviewed"

        pr = await cli.post(
            "/api/v1/traces/tr-1/promote-to-dataset",
            json={"expected_outcome": "ok"},
            headers=headers,
        )
        assert pr.status_code == 200
        promoted_body = pr.json()
        assert promoted_body["promoted"] is True
        assert promoted_body["record"]["inputs"]["server"] == "memory"
        assert promoted_body["record"]["inputs"]["tool"] == "memory_store"
        assert logged["dataset"][0][0] == "mcp-workshop-golden-v1"


async def test_ui_cookie_auth_flow_login_link_session_logout_and_csrf(make_settings) -> None:
    secret_tok = "tok_ui_flow_999"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory"]
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
        # /ui must not embed sessionStorage token storage or secrets
        ui = await cli.get("/ui")
        assert ui.status_code == 200
        assert "sessionStorage" not in ui.text
        markers = (
            "tab-overview",
            "tab-playground",
            "tab-traces",
            "tab-registry",
            "regression-banner",
        )
        for marker in markers:
            assert marker in ui.text

        # Unauthenticated /api/v1/auth/me returns authenticated=False cleanly
        me_unauth = await cli.get("/api/v1/auth/me")
        assert me_unauth.status_code == 200
        assert me_unauth.json()["authenticated"] is False

        # Mint 60s login link with Bearer
        link = await cli.post(
            "/api/v1/auth/login-link", headers={"Authorization": f"Bearer {secret_tok}"}
        )
        assert link.status_code == 200
        login_url = link.json()["url"]
        nonce = login_url.split("nonce=", 1)[1]

        # Consume nonce -> 303 redirect setting HttpOnly session cookie
        consumed = await cli.get(f"/ui/login?nonce={nonce}", follow_redirects=False)
        assert consumed.status_code == 303
        assert UI_SESSION_COOKIE in consumed.cookies

        # Replay of single-use nonce fails cleanly with redirect auth_error
        replay = await cli.get(f"/ui/login?nonce={nonce}", follow_redirects=False)
        assert replay.status_code == 303
        assert "auth_error=invalid_link" in replay.headers["location"]

        # Cookie authenticates /api/v1/auth/me and /api/v1/profiles
        me_cookie = await cli.get("/api/v1/auth/me")
        assert me_cookie.json()["authenticated"] is True
        assert me_cookie.json()["authMethod"] == "cookie"
        assert (await cli.get("/api/v1/profiles")).status_code == 200

        # Cookie cannot mint another login link (Bearer-only)
        link_from_cookie = await cli.post(
            "/api/v1/auth/login-link", headers={"X-Requested-With": "mcp-ui"}
        )
        assert link_from_cookie.status_code == 403

        # Logout clears cookie
        out = await cli.post("/api/v1/auth/logout", headers={"X-Requested-With": "mcp-ui"})
        assert out.status_code == 200
        assert (await cli.get("/api/v1/auth/me")).json()["authenticated"] is False


async def test_traces_filtering_facets_eval_history_and_registry_api(
    make_settings, monkeypatch
) -> None:
    tok = "tok_registry_and_filter"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.mlflow.allow_mutations = False
    settings.unity_catalog.dynamic_function_tools = False

    fake_traces = [
        types.SimpleNamespace(
            info=types.SimpleNamespace(
                trace_id="tr-mem",
                state="OK",
                execution_duration=12.0,
                timestamp_ms=2000,
                tags={"mcp.server": "memory", "mcp.tool": "memory_store", "mcp.profile": "core"},
                trace_metadata={"mlflow.trace.user": "codex", "mlflow.modelId": "m-1"},
                assessments=[],
            ),
            data=types.SimpleNamespace(
                spans=[types.SimpleNamespace(name="memory.memory_store", events=[])]
            ),
        ),
        types.SimpleNamespace(
            info=types.SimpleNamespace(
                trace_id="tr-uc",
                state="ERROR",
                execution_duration=5.0,
                timestamp_ms=1000,
                tags={
                    "mcp.server": "unity_catalog",
                    "mcp.tool": "uc_create_catalog",
                    "mcp.policy_refusal": "true",
                },
                trace_metadata={"mlflow.trace.user": "claude", "mlflow.modelId": "m-2"},
                assessments=[],
            ),
            data=types.SimpleNamespace(
                spans=[
                    types.SimpleNamespace(
                        name="unity_catalog.uc_create_catalog", events=[]
                    )
                ]
            ),
        ),
    ]
    fake_runs = [
        types.SimpleNamespace(
            info=types.SimpleNamespace(run_id="r-new", run_name="eval-new", start_time=2000),
            data=types.SimpleNamespace(
                metrics={"tool_execution_success/mean": 0.5, "tool_latency_sla/mean": 1.0}
            ),
        ),
        types.SimpleNamespace(
            info=types.SimpleNamespace(run_id="r-old", run_name="eval-old", start_time=1000),
            data=types.SimpleNamespace(
                metrics={"tool_execution_success/mean": 1.0, "tool_latency_sla/mean": 1.0}
            ),
        ),
    ]
    alias_calls: list[tuple[str, str, str, object]] = []

    class FakeClient:
        def __init__(self, tracking_uri: str, registry_uri: str | None = None) -> None:
            self.tracking_uri = tracking_uri

        def get_experiment_by_name(self, _name: str):
            return types.SimpleNamespace(experiment_id="52")

        def search_traces(self, **_kwargs):
            return fake_traces

        def search_runs(self, *_args, **_kwargs):
            return fake_runs

        def search_mcp_servers(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    name="io.github.slcc2c/mcp-memory",
                    url="http://127.0.0.1:8090/servers/memory/mcp",
                    version="2.0.0",
                    description="Memory server",
                    aliases={"production": "2.0.0"},
                    tags={"scope": "server"},
                )
            ]

        def search_prompt_versions(self, name: str, **_kwargs):
            return [types.SimpleNamespace(version=2, aliases=["production"], commit_message="init")]

        def search_registered_models(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    name="demo-model",
                    description="Demo",
                    aliases={"champion": "1"},
                    tags={},
                    latest_versions=[
                        types.SimpleNamespace(version="2", current_stage="None", aliases=[])
                    ],
                )
            ]

        def search_logged_models(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    model_id="m-1",
                    name="mcp-workshop-gateway-2-0-0-c1f6301",
                    status="READY",
                    tags={"git_sha": "c1f6301"},
                    metrics=[],
                )
            ]

        def set_registered_model_alias(self, name: str, alias: str, version: str):
            alias_calls.append(("model", name, alias, version))

    import mlflow
    import mlflow.genai

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _u: None)
    monkeypatch.setattr(
        mlflow.genai,
        "search_prompts",
        lambda **_kw: [types.SimpleNamespace(name="ai-assist", description="Assist", tags={})],
    )
    monkeypatch.setattr(
        mlflow.genai,
        "load_prompt",
        lambda _uri, **_kw: types.SimpleNamespace(
            name="ai-assist",
            version=2,
            template="Be concise.",
            commit_message="v2",
            tags={},
            uri="prompts:/ai-assist/2",
        ),
    )
    monkeypatch.setattr(
        mlflow.genai,
        "set_prompt_alias",
        lambda name, alias, version: alias_calls.append(("prompt", name, alias, version)),
    )

    headers = {"Authorization": f"Bearer {tok}"}
    app = build_gateway_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as cli:
        filtered = await cli.get(
            "/api/v1/traces?user=codex&policy_refusal=exclude", headers=headers
        )
        assert filtered.status_code == 200
        body = filtered.json()
        assert [t["traceId"] for t in body["traces"]] == ["tr-mem"]
        assert body["facets"]["servers"] == ["memory", "unity_catalog"]
        assert len(body["evalHistory"]) == 2
        assert body["evalRegression"]["status"] == "regression"

        reg = await cli.get("/api/v1/mlflow/registry", headers=headers)
        assert reg.status_code == 200
        reg_json = reg.json()
        assert reg_json["mutationsEnabled"] is False
        assert reg_json["mcpServers"][0]["aliases"]["production"] == "2.0.0"
        assert reg_json["prompts"][0]["name"] == "ai-assist"
        assert reg_json["loggedModels"][0]["modelId"] == "m-1"

        p_det = await cli.get(
            "/api/v1/mlflow/prompts/ai-assist?version_or_alias=2", headers=headers
        )
        assert p_det.status_code == 200
        assert p_det.json()["template"] == "Be concise."

        # Read-only blocks alias promotion
        denied = await cli.post(
            "/api/v1/mlflow/prompts/ai-assist/alias",
            json={"alias": "production", "version": 2},
            headers=headers,
        )
        assert denied.status_code == 403

    # Mutations enabled allows prompt + model alias updates
    settings.mlflow.allow_mutations = True
    app_mut = build_gateway_app(settings)
    async with app_mut.router.lifespan_context(app_mut), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_mut), base_url="http://testserver"
    ) as cli_mut:
        ok_p = await cli_mut.post(
            "/api/v1/mlflow/prompts/ai-assist/alias",
            json={"alias": "production", "version": 2},
            headers=headers,
        )
        assert ok_p.status_code == 200
        ok_m = await cli_mut.post(
            "/api/v1/mlflow/models/demo-model/alias",
            json={"alias": "production", "version": "2"},
            headers=headers,
        )
        assert ok_m.status_code == 200
    assert alias_calls == [
        ("prompt", "ai-assist", "production", 2),
        ("model", "demo-model", "production", "2"),
    ]


def test_cli_ui_open_mints_login_link_without_printing_token(make_settings, monkeypatch) -> None:
    tok = "tok_secret_never_echo"
    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    monkeypatch.setattr("mcp_stack.cli.load_settings", lambda: settings)

    def fake_post(url: str, *, headers: dict, timeout: float):
        assert url.endswith("/api/v1/auth/login-link")
        assert headers["Authorization"] == f"Bearer {tok}"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "url": "http://127.0.0.1:8090/ui/login?nonce=abc123",
                "expiresInSeconds": 60,
                "clientId": "codex",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = CliRunner().invoke(cli_app, ["ui", "open", "--no-browser"])
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["url"] == "http://127.0.0.1:8090/ui/login?nonce=abc123"
    assert tok not in result.stdout