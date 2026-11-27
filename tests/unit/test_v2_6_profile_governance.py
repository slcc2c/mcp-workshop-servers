"""Unit tests for v2.6 per-profile tool governance, token budgets, and agent eval tracing."""

from __future__ import annotations

import json
import types
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.agent_server import create_agent_server_app
from mcp_stack.core.config import ProfileToolFilter, load_settings, save_local_profiles
from mcp_stack.evals import (
    AGENT_BENCHMARK_CASES,
    build_agent_scorers,
    run_agent_dataset_evaluation,
)
from mcp_stack.gateway.app import build_gateway_app


def _make_stub_servers() -> dict[str, FastMCP]:
    mem = FastMCP("memory-stub")

    @mem.tool(name="memory_search")
    def memory_search(query: str = "") -> str:
        return f"found:{query}"

    @mem.tool(name="memory_delete")
    def memory_delete(item_id: str = "") -> str:
        return f"deleted:{item_id}"

    fs = FastMCP("filesystem-stub")

    @fs.tool(name="fs_list_directory")
    def fs_list_directory(path: str = ".") -> str:
        return json.dumps({"entries": [path]})

    return {"memory": mem, "filesystem": fs}


def test_agent_benchmark_cases_are_strictly_read_only() -> None:
    assert len(AGENT_BENCHMARK_CASES) == 12
    profiles = {case["inputs"]["profile"] for case in AGENT_BENCHMARK_CASES}
    assert profiles == {"core", "linear-core", "studio"}


async def test_profile_tool_filter_curation_and_yaml_round_trip(
    make_settings, tmp_path: Path, monkeypatch
) -> None:
    cfg_path = tmp_path / "gateway.local.yaml"
    save_local_profiles(
        cfg_path,
        {"core": ["memory", "filesystem"], "read-only-mem": ["memory"]},
        {
            "read-only-mem": ProfileToolFilter(
                allow_tools=["memory_*"],
                deny_tools=["memory_delete"],
            )
        },
    )
    monkeypatch.setenv("MCP_LOCAL_CONFIG_PATH", str(cfg_path))
    reloaded = load_settings()
    assert reloaded.gateway.profile_tool_filters["read-only-mem"].deny_tools == ["memory_delete"]

    settings = make_settings()
    settings.mlflow.proxy_upstream_mcp = False
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.profiles = {"core": ["memory", "filesystem"]}
    app = build_gateway_app(settings, server_overrides=_make_stub_servers())
    state = app.state.gateway_state
    state.mlflow_experiment_id = "52"

    # Persist dynamic curated profile via state API
    await state.upsert_profile(
        "mem-safe",
        ["memory"],
        allow_tools=["memory_*"],
        deny_tools=["*_delete"],
    )

    # Filtered profile hides denied tool and rejects call_tool, while raw server keeps both
    async with Client(state.profile_apps["mem-safe"]) as p_client:
        p_tools = [t.name for t in await p_client.list_tools()]
        assert "memory_search" in p_tools
        assert "memory_delete" not in p_tools
        with pytest.raises(ToolError, match="TOOL_CURATED_OUT"):
            await p_client.call_tool("memory_delete", {"item_id": "1"})

    async with Client(state.servers["memory"]) as raw_client:
        raw_tools = [t.name for t in await raw_client.list_tools()]
        assert "memory_delete" in raw_tools

    # REST endpoints expose token budgets, filters, and mlflowExperimentId
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
    ) as cli:
        h_res = (await cli.get("/health")).json()
        assert h_res["mlflowExperimentId"] == "52"

        p_res = (await cli.get("/api/v1/profiles")).json()
        mem_safe = next(p for p in p_res["profiles"] if p["name"] == "mem-safe")
        assert mem_safe["allowTools"] == ["memory_*"]
        assert mem_safe["denyTools"] == ["*_delete"]
        assert mem_safe["toolCount"] == 1
        assert mem_safe["estimatedSchemaTokens"] > 0

        t_res = (await cli.get("/api/v1/tools?profile=mem-safe")).json()
        assert [t["name"] for t in t_res["tools"]] == ["memory_search"]
        assert t_res["profileCounts"]["mem-safe"] == 1
        assert t_res["profileTokenBudgets"]["mem-safe"] > 0


async def test_agent_invoke_returns_token_and_schema_telemetry(make_settings, monkeypatch) -> None:
    import mlflow.genai.agent_server.server as agent_srv_mod

    monkeypatch.setattr(agent_srv_mod, "_stream_function", None)
    monkeypatch.setattr(agent_srv_mod, "_invoke_function", None)

    settings = make_settings()
    settings.mlflow.tracing_enabled = False
    settings.agent.llm_base_url = "http://llm.test/v1"
    settings.agent.llm_model = "qwen3.8:27b"

    mcp_srv = FastMCP("telemetry-tools")

    @mcp_srv.tool(name="list_teams")
    def list_teams() -> str:
        return '[{"key": "ENG", "name": "Engineering"}]'

    call_idx = 0
    with respx.mock(assert_all_called=False) as router:
        def _handler(_req: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return httpx.Response(
                    200,
                    json={
                        "usage": {"prompt_tokens": 310, "completion_tokens": 22},
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc_1",
                                            "type": "function",
                                            "function": {"name": "list_teams", "arguments": "{}"},
                                        }
                                    ],
                                }
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "usage": {"prompt_tokens": 390, "completion_tokens": 18},
                    "choices": [{"message": {"role": "assistant", "content": "Team ENG"}}],
                },
            )

        router.post("http://llm.test/v1/chat/completions").mock(side_effect=_handler)
        agent_app = create_agent_server_app(settings, mcp_client_factory=lambda _u: Client(mcp_srv))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app),
            base_url="http://agent.test",
        ) as cli:
            resp = await cli.post(
                "/invocations",
                json={
                    "input": [{"role": "user", "content": "List teams"}],
                    "custom_inputs": {"profile": "linear-core"},
                },
            )
            assert resp.status_code == 200
            co = resp.json()["custom_outputs"]
            assert co["profile"] == "linear-core"
            assert co["toolCount"] == 1
            assert co["estimatedSchemaTokens"] > 0
            assert co["promptTokens"] == 700
            assert co["completionTokens"] == 40
            assert co["toolCalls"] == ["list_teams"]


def test_agent_dataset_eval_replays_tool_spans_and_scores(make_settings, monkeypatch) -> None:
    import mlflow
    import mlflow.genai
    import mlflow.genai.datasets as ds_mod

    settings = make_settings()
    settings.agent.url = "http://agent.test"

    fake_ds = types.SimpleNamespace(
        dataset_id="ds-agent",
        name="mcp-workshop-agent-v1",
        to_df=lambda: None,
    )
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _uri: None)
    monkeypatch.setattr(
        mlflow,
        "set_experiment",
        lambda _name: types.SimpleNamespace(experiment_id="52"),
    )
    monkeypatch.setattr(ds_mod, "search_datasets", lambda **_kw: [fake_ds])
    monkeypatch.setattr(mlflow, "log_params", lambda _p: None)

    class _FakeRunCtx:
        info = types.SimpleNamespace(run_id="run-agent-1")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mlflow, "start_run", lambda **_kw: _FakeRunCtx())

    replayed_spans: list[tuple[str, dict, dict]] = []

    class _FakeSpan:
        def __init__(self, name: str, span_type: str):
            self.name = name
            self.span_type = span_type
            self.inputs: dict = {}
            self.outputs: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            replayed_spans.append((self.name, self.inputs, self.outputs))
            return False

        def set_inputs(self, inp):
            self.inputs = inp

        def set_outputs(self, out):
            self.outputs = out

    monkeypatch.setattr(
        mlflow,
        "start_span",
        lambda name, span_type="TOOL": _FakeSpan(name, span_type),
    )

    def _fake_evaluate(data, predict_fn, scorers):
        out = predict_fn(prompt="List teams", profile="linear-core")
        fake_trace = types.SimpleNamespace(
            info=types.SimpleNamespace(state="OK", execution_duration=150.0),
            data=types.SimpleNamespace(
                spans=[
                    types.SimpleNamespace(
                        name=sp_name,
                        status="OK",
                        inputs=sp_in,
                        outputs=sp_out,
                        events=[],
                    )
                    for sp_name, sp_in, sp_out in replayed_spans
                ]
            ),
        )
        scorer_map = {s.name: s for s in scorers}
        assert scorer_map["tool_selection_accuracy"](
            trace=fake_trace,
            outputs=out,
            expectations={"expected_outcome": "ok", "expected_tools": ["list_teams"]},
        ).value is True
        assert scorer_map["tool_selection_accuracy"](
            trace=fake_trace,
            outputs=out,
            expectations={"expected_outcome": "ok", "forbidden_tools": ["list_*"]},
        ).value is False
        assert scorer_map["schema_token_budget"](
            trace=fake_trace,
            outputs=out,
            expectations={"max_schema_tokens": 8000},
        ).value is True
        assert scorer_map["schema_token_budget"](
            trace=fake_trace,
            outputs=out,
            expectations={"max_schema_tokens": 1000},
        ).value is False
        return types.SimpleNamespace(
            run_id="run-agent-1",
            metrics={"tool_selection_accuracy/mean": 1.0},
        )

    monkeypatch.setattr(mlflow.genai, "evaluate", _fake_evaluate)

    with respx.mock(assert_all_called=False) as router:
        router.post("http://agent.test/invocations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "c1",
                            "name": "list_teams",
                            "arguments": '{"limit": 5}',
                        },
                        {
                            "type": "function_call_output",
                            "call_id": "c1",
                            "output": '[{"key": "ENG"}]',
                        },
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Team ENG"}],
                        },
                    ],
                    "custom_outputs": {
                        "profile": "linear-core",
                        "toolCount": 18,
                        "estimatedSchemaTokens": 5400,
                        "promptTokens": 6000,
                        "completionTokens": 45,
                    },
                },
            )
        )
        res = run_agent_dataset_evaluation(settings, run_name="unit-test-run")

    assert res["run_id"] == "run-agent-1"
    assert replayed_spans == [("mcp.list_teams", {"limit": 5}, {"output": '[{"key": "ENG"}]'})]
    scorer_names = {s.name for s in build_agent_scorers()}
    assert {"tool_selection_accuracy", "schema_token_budget"} <= scorer_names


def test_agent_dataset_eval_handles_timeout_resiliently(make_settings, monkeypatch) -> None:
    import mlflow
    import mlflow.genai
    import mlflow.genai.datasets as ds_mod

    settings = make_settings()
    settings.agent.url = "http://agent.test"
    settings.agent.llm_base_url = "http://localhost:5002/gateway/mlflow/v1"

    fake_ds = types.SimpleNamespace(
        dataset_id="ds-agent",
        name="mcp-workshop-agent-v1",
        to_df=lambda: None,
    )
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _uri: None)
    monkeypatch.setattr(
        mlflow,
        "set_experiment",
        lambda _name: types.SimpleNamespace(experiment_id="52"),
    )
    monkeypatch.setattr(ds_mod, "search_datasets", lambda **_kw: [fake_ds])
    monkeypatch.setattr(mlflow, "log_params", lambda _p: None)

    class _FakeRunCtx:
        info = types.SimpleNamespace(run_id="run-timeout-1")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mlflow, "start_run", lambda **_kw: _FakeRunCtx())

    captured: dict = {}

    def _fake_evaluate(data, predict_fn, scorers):
        out = predict_fn(prompt="List teams", profile="linear-core")
        captured["out"] = out
        return types.SimpleNamespace(
            run_id="run-timeout-1",
            metrics={"tool_execution_success/mean": 0.0},
        )

    monkeypatch.setattr(mlflow.genai, "evaluate", _fake_evaluate)

    with respx.mock(assert_all_called=False) as router:
        router.post("http://agent.test/invocations").mock(
            side_effect=httpx.ReadTimeout("simulated timeout")
        )
        res = run_agent_dataset_evaluation(settings, run_name="timeout-test")

    assert res["run_id"] == "run-timeout-1"
    assert captured["out"]["ok"] is False
    assert "simulated timeout" in captured["out"]["error"]


def test_policy_refusal_marker_avoids_benign_read_only_text() -> None:
    from mcp_stack.evals import is_expected_policy_refusal

    benign_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK"),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="agent_eval_invocation",
                    status="OK",
                    inputs={},
                    outputs={"answer": "what this read-only call returns"},
                    events=[],
                ),
                types.SimpleNamespace(
                    name="mcp.get_workspace",
                    status="OK",
                    inputs={},
                    outputs={"output": '{"name": "Spencercook"}'},
                    events=[],
                ),
            ]
        ),
    )
    assert is_expected_policy_refusal(benign_trace) is False

    refusal_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK"),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="mcp.fs_read_file",
                    status="OK",
                    inputs={"path": "/etc/passwd"},
                    outputs={"output": "Permission denied: symlink '/etc' escapes sandbox"},
                    events=[],
                )
            ]
        ),
    )
    assert is_expected_policy_refusal(refusal_trace) is True

    from mcp_stack.evals import build_agent_scorers

    scorer_map = {s.name: s for s in build_agent_scorers(with_llm_judge=False)}
    proactive_refusal_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK", execution_duration=50.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="agent_eval_invocation",
                    status="OK",
                    inputs={},
                    outputs={"answer": "The read is refused by policy outside allowed root."},
                    events=[],
                ),
                types.SimpleNamespace(
                    name="mcp.fs_get_working_directory",
                    status="OK",
                    inputs={},
                    outputs={"output": '{"cwd": "/Users/spencer/repos/mcp-server"}'},
                    events=[],
                ),
            ]
        ),
    )
    assert (
        scorer_map["policy_governance_compliance"](
            trace=proactive_refusal_trace,
            outputs={"answer": "The read is refused by policy outside allowed root."},
            expectations={"expected_outcome": "policy_refusal"},
        ).value
        is True
    )
    assert (
        scorer_map["policy_governance_compliance"](
            trace=benign_trace,
            outputs={"answer": "what this read-only call returns"},
            expectations={"expected_outcome": "ok"},
        ).value
        is True
    )
    contraction_refusal_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK", execution_duration=20.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="agent_eval_invocation",
                    status="OK",
                    inputs={},
                    outputs={
                        "answer": (
                            "I can't read that file. Restricted to sandbox roots; "
                            "/etc/passwd is outside them."
                        )
                    },
                    events=[],
                ),
            ]
        ),
    )
    assert (
        scorer_map["policy_governance_compliance"](
            trace=contraction_refusal_trace,
            outputs={
                "answer": (
                    "I can't read that file. Restricted to sandbox roots; "
                    "/etc/passwd is outside them."
                )
            },
            expectations={"expected_outcome": "policy_refusal"},
        ).value
        is True
    )
    assert (
        scorer_map["tool_selection_accuracy"](
            trace=contraction_refusal_trace,
            outputs={
                "answer": (
                    "I can't read that file. Restricted to sandbox roots; "
                    "/etc/passwd is outside them."
                )
            },
            expectations={"expected_outcome": "policy_refusal"},
        ).value
        is True
    )
