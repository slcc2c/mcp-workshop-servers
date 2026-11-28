"""Comprehensive unit tests for MCP Workshop Stack v2.5.0 features."""

from __future__ import annotations

import json
import subprocess
import types
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport

from mcp_stack.agent_server import create_agent_server_app
from mcp_stack.core.config import ClientPolicy, UpstreamServerConfig
from mcp_stack.core.secrets import CommandResult, SecretResolver
from mcp_stack.evals import (
    DEFAULT_JUDGE_MODEL,
    build_agent_tool_use_grounding_judge,
    build_native_clarity_judge,
    compare_eval_runs,
    get_eval_run_detail,
    is_typesafe_judge_model,
    list_eval_datasets,
    normalize_judge_model_uri,
)
from mcp_stack.gateway.activity import ActivityBus
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.gateway.upstreams import build_upstream_proxy, filter_tool_names, is_tool_allowed
from mcp_stack.skill_registry import (
    clear_capability_cache,
    list_mlflow_skills,
    probe_skill_registry_capability,
    register_mlflow_skill,
    update_mlflow_skill_version,
)

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


def test_tool_curation_globs_and_middleware(make_settings) -> None:
    names = ["get_issue", "list_issues", "delete_issue", "create_issue", "list_teams"]
    allow = ["*_issue*", "list_teams"]
    deny = ["delete_*"]
    assert filter_tool_names(names, allow, deny) == [
        "get_issue",
        "list_issues",
        "create_issue",
        "list_teams",
    ]
    assert is_tool_allowed("delete_issue", ["*"], ["delete_*"]) is False

    settings = make_settings()
    cfg = UpstreamServerConfig(
        transport="http",
        url="https://example.test/mcp",
        allow_tools=["get_*"],
        deny_tools=["get_secret"],
    )
    proxy, info = build_upstream_proxy("linear", cfg, settings)
    assert proxy is not None
    assert info["connectionStatus"] == "configured"
    client_factory = proxy.client_factory  # type: ignore[attr-defined]
    assert client_factory().transport.forward_incoming_headers is False


async def test_discover_describe_call_and_dynamic_profile_crud(
    make_settings, monkeypatch, tmp_path: Path
) -> None:
    local_yaml = tmp_path / "gateway.local.yaml"
    monkeypatch.setenv("MCP_LOCAL_CONFIG_PATH", str(local_yaml))

    mem_srv = FastMCP("memory-mock")

    @mem_srv.tool(name="memory_ping")
    def memory_ping(echo: str = "ok") -> dict[str, str]:
        return {"pong": echo}

    fs_srv = FastMCP("fs-mock")

    @fs_srv.tool(name="fs_info")
    def fs_info() -> dict[str, str]:
        return {"root": "/tmp"}

    tok_limited = "tok_limited_acl_999"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok_limited: ClientPolicy(
            client_id="limited",
            client_name="Limited Client",
            allowed_servers=["gateway", "memory"],
        )
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False

    app = build_gateway_app(
        settings,
        server_overrides={"memory": mem_srv, "filesystem": fs_srv},
    )
    headers = {"Authorization": f"Bearer {tok_limited}"}
    factory = _asgi_factory(app)

    async with app.router.lifespan_context(app):
        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/discover/mcp",
                headers=headers,
                httpx_client_factory=factory,
            )
        ) as disc_cli:
            desc_res = await disc_cli.call_tool(
                "gateway_describe_tool",
                {"server": "memory", "tool": "memory_ping"},
            )
            desc = json.loads(str(desc_res.content[0].text))
            assert desc["tool"] == "memory_ping"
            assert "properties" in desc["parameters"]

            call_res = await disc_cli.call_tool(
                "gateway_call_tool",
                {"server": "memory", "tool": "memory_ping", "arguments": {"echo": "hello"}},
            )
            call_data = json.loads(str(call_res.content[0].text))
            assert call_data["ok"] is True
            assert call_data["result"] == {"pong": "hello"}

            denied = await disc_cli.call_tool(
                "gateway_call_tool",
                {"server": "filesystem", "tool": "fs_info"},
                raise_on_error=False,
            )
            assert denied.is_error is True
            assert "ACCESS_DENIED" in str(denied.content[0].text)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_cli:
            # Create custom profile live and use it without restart
            bad = await http_cli.put(
                "/api/v1/profiles/discover",
                headers=headers,
                json={"servers": ["memory"]},
            )
            assert bad.status_code == 400

            created = await http_cli.post(
                "/api/v1/profiles",
                headers=headers,
                json={"name": "mem-only", "servers": ["memory"]},
            )
            assert created.status_code == 200
            assert created.json()["restartRequired"] is False
            assert "mem-only" in local_yaml.read_text(encoding="utf-8")

            del_builtin = await http_cli.delete("/api/v1/profiles/discover", headers=headers)
            assert del_builtin.status_code == 400

        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/mem-only/mcp",
                headers=headers,
                httpx_client_factory=factory,
            )
        ) as custom_cli:
            tools = {t.name for t in await custom_cli.list_tools()}
            assert tools == {"memory_ping"}


def test_skill_registry_fallback_and_mocked_318(make_settings, tmp_path: Path) -> None:
    clear_capability_cache()
    settings = make_settings()
    settings.mlflow.allow_mutations = True

    with respx.mock(assert_all_called=False) as router:
        router.get("http://mlflow.test:5002/version").mock(
            return_value=httpx.Response(200, text="3.17.0\n")
        )
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        assert cap["supported"] is False
        assert cap["serverVersion"] == "3.17.0"
        res = list_mlflow_skills(settings)
        assert res["supported"] is False
        assert res["skills"] == []

    # Now test mocked 3.18 client paths inside allowed_paths
    skill_dir = tmp_path / "workspace" / "code-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Code Review\n", encoding="utf-8")

    fake_ver = types.SimpleNamespace(
        name="code-review",
        version=1,
        organization="atelier",
        status="draft",
        aliases=["production"],
        digest="abc",
        source=str(skill_dir),
        creation_timestamp=100,
        last_updated_timestamp=100,
        tags={},
    )
    fake_skill = types.SimpleNamespace(
        name="code-review",
        organization="atelier",
        description="Review diffs",
        aliases={"production": 1},
        tags={},
    )
    aliases_set: list[tuple[str, str, int]] = []

    class FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def search_skill_versions(self, **_kw):
            return [fake_ver]

        def update_skill_version(self, *, name, version, organization="", status=None):
            fake_ver.status = status
            return fake_ver

        def set_skill_alias(self, *, name, alias, version, organization=""):
            aliases_set.append((name, alias, version))

        def get_skill_version(self, *, name, version, organization=""):
            return fake_ver

    fake_mlflow = types.SimpleNamespace(
        set_tracking_uri=lambda _u: None,
        MlflowClient=FakeClient,
        genai=types.SimpleNamespace(
            search_skills=lambda max_results=50: [fake_skill],
            register_skill=lambda **kw: fake_ver,
        ),
    )
    listed = list_mlflow_skills(settings, mlflow_module=fake_mlflow)
    assert listed["supported"] is True
    assert listed["skills"][0]["name"] == "code-review"

    reg = register_mlflow_skill(
        settings,
        source=str(skill_dir),
        organization="atelier",
        alias="staging",
        mlflow_module=fake_mlflow,
    )
    assert reg["created"] is True
    assert aliases_set == [("code-review", "staging", 1)]

    upd = update_mlflow_skill_version(
        settings, name="code-review", version=1, status="active", mlflow_module=fake_mlflow
    )
    assert upd["updated"] is True
    assert upd["version"]["status"] == "active"


def test_typesafe_judges_and_eval_run_detail(monkeypatch) -> None:
    assert is_typesafe_judge_model("typesafe:/jev-latest") is True
    assert is_typesafe_judge_model("databricks:/system.ai.jev", "decisions") is True
    assert is_typesafe_judge_model("ollama:/qwen3.8:27b") is False

    judge = build_native_clarity_judge("typesafe:/jev-latest")
    assert "{{ trace }}" not in judge.instructions
    assert "{{ outputs }}" in judge.instructions
    assert judge.model == "typesafe:/jev-latest"

    import mlflow

    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _u: None)

    class FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def get_experiment_by_name(self, name: str):
            return types.SimpleNamespace(experiment_id="exp-1", name=name)

        def get_run(self, run_id: str):
            metrics_map = (
                {
                    "tool_execution_success/mean": 0.9,
                    "tool_response_clarity_typesafe/mean": 0.85,
                }
                if run_id == "run-b"
                else {
                    "tool_execution_success/mean": 0.8,
                    "tool_response_clarity_typesafe/mean": 0.85,
                }
            )
            return types.SimpleNamespace(
                info=types.SimpleNamespace(
                    run_id=run_id,
                    run_name=f"name-{run_id}",
                    status="FINISHED",
                    start_time=1000,
                ),
                data=types.SimpleNamespace(metrics=metrics_map, params={"model": "qwen3"}),
            )

        def search_traces(self, run_id: str, max_results: int = 200):
            return [
                types.SimpleNamespace(
                    info=types.SimpleNamespace(
                        trace_id="tr-eval-1",
                        state="OK",
                        execution_duration=42,
                        assessments=[
                            types.SimpleNamespace(
                                name="tool_response_clarity_typesafe",
                                feedback=types.SimpleNamespace(
                                    value=True,
                                    metadata={"typesafe.probability": 0.942},
                                ),
                                rationale="Decision yes",
                            )
                        ],
                    ),
                    data=types.SimpleNamespace(
                        spans=[
                            types.SimpleNamespace(
                                start_time_ns=0,
                                end_time_ns=42_000_000,
                                inputs={"tool": "memory_ping"},
                                outputs={"pong": "ok"},
                            )
                        ]
                    ),
                )
            ]

    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    from mcp_stack.core.config import MCPStackSettings

    detail = get_eval_run_detail(MCPStackSettings(_env_file=None), "run-b")
    assert detail["rows"][0]["assessments"][0]["typesafeProbability"] == 0.942
    cmp_res = compare_eval_runs(MCPStackSettings(_env_file=None), "run-a", "run-b")
    delta_row = next(d for d in cmp_res["deltas"] if d["metric"] == "tool_execution_success/mean")
    assert delta_row["delta"] == 0.1
    assert delta_row["direction"] == "improved"

    import mlflow.genai.datasets as ds_mod

    monkeypatch.setattr(
        ds_mod,
        "search_datasets",
        lambda **_kw: [
            types.SimpleNamespace(
                dataset_id="ds-1", name="golden", created_time=10, digest="d", tags={}
            )
        ],
    )
    ds_res = list_eval_datasets(MCPStackSettings(_env_file=None))
    assert ds_res["datasets"][0]["datasetId"] == "ds-1"


async def test_agent_server_invoke_with_mocked_llm_and_mcp(make_settings, monkeypatch) -> None:
    settings = make_settings()
    settings.mlflow.tracing_enabled = False
    settings.agent.llm_base_url = "http://llm.test/v1"
    settings.agent.llm_model = "test-model"

    mcp_srv = FastMCP("mock-tools")

    @mcp_srv.tool(name="ping_tool")
    def ping_tool(val: str = "x") -> str:
        return f"pong:{val}"

    call_idx = 0
    with respx.mock(assert_all_called=False) as router:
        def _llm_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "ping_tool",
                                                "arguments": '{"val": "abc"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "Done: pong:abc"}}]},
            )

        router.post("http://llm.test/v1/chat/completions").mock(side_effect=_llm_handler)

        agent_app = create_agent_server_app(
            settings,
            mcp_client_factory=lambda _url: Client(mcp_srv),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app),
            base_url="http://agent.test",
        ) as cli:
            resp = await cli.post(
                "/invocations",
                json={"input": [{"role": "user", "content": "Run ping_tool"}]},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert any(
                "Done: pong:abc" in json.dumps(item) for item in body.get("output", [])
            )


def test_secret_resolver_dual_mode_diagnostics_and_activity_bus(
    make_settings, monkeypatch
) -> None:
    settings = make_settings()
    settings.secrets.onepassword_enabled = True
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "ops_dummy_never_logged")

    def _timeout(_args: list[str]) -> CommandResult:
        raise subprocess.TimeoutExpired(cmd=["op", "read"], timeout=10)

    resolver = SecretResolver(settings.secrets, runner=_timeout)
    assert resolver.onepassword_mode() == "service-account"
    with pytest.raises(Exception) as exc_info:
        resolver.resolve("op://AI/Test/cred")
    assert "unlock 1Password" in str(exc_info.value)

    diag = resolver.diagnostics()
    assert diag["configuredMode"] == "service-account"
    assert diag["mode"] == "service-account"
    assert diag["serviceAccountConfigured"] is True
    assert diag["lastErrorCode"] == "timeout"
    assert "ops_dummy_never_logged" not in json.dumps(diag)

    bus = ActivityBus(maxlen=10)
    ev = bus.record(
        "tool_call",
        status="ok",
        server="linear",
        tool="list_teams",
        duration_ms=42.5,
        detail={"authorization": "Bearer secret_abc"},
    )
    assert ev["detail"]["authorization"] == "<redacted>"
    assert len(bus.recent(limit=5)) == 1
    assert len(bus.metrics_series(buckets=4)) == 4


def test_default_cross_family_judge_and_agent_grounding_scorer(monkeypatch) -> None:
    monkeypatch.delenv("MCP_EVAL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("MCP_EVAL_OLLAMA_MODEL", raising=False)
    assert DEFAULT_JUDGE_MODEL == "gateway:/mcp-workshop-judge-v1"
    assert normalize_judge_model_uri(None) == "gateway:/mcp-workshop-judge-v1"
    assert (
        normalize_judge_model_uri("ollama:/gemma4-64k:latest")
        == "ollama_chat:/gemma4-64k:latest"
    )

    grounding_judge = build_agent_tool_use_grounding_judge()
    assert grounding_judge.name == "agent_tool_use_grounding_judge"
    assert "{{ trace }}" in grounding_judge.instructions
    assert grounding_judge.model == "gateway:/mcp-workshop-judge-v1"
