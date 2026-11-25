"""Unit tests for LaunchAgent log rotation and MLflow 3.x GenAI trace @scorers."""

from __future__ import annotations

import importlib.util
import os
import types
from pathlib import Path

import httpx

from mcp_stack.evals import (
    build_native_clarity_judge,
    build_trace_scorers,
    invoke_benchmark_tool,
    is_expected_policy_refusal,
    normalize_judge_model_uri,
)
from mcp_stack.service import rotate_log_file, rotate_service_logs


def test_log_rotation_caps_size_and_keeps_three_archives(tmp_path: Path) -> None:
    log_file = tmp_path / "gateway.log"
    log_file.write_bytes(b"x" * 2048)

    assert rotate_log_file(log_file, max_bytes=1024, keep=3) is True
    assert (tmp_path / "gateway.log.1").exists()
    assert log_file.stat().st_size == 0

    summary = rotate_service_logs(tmp_path, max_mb=0.001, keep=3)
    assert summary["scanned"] >= 1


def test_mlflow_http_pool_defaults_prevent_urllib3_overflow() -> None:
    assert int(os.environ["MLFLOW_HTTP_POOL_MAXSIZE"]) >= 64
    assert int(os.environ["MLFLOW_HTTP_POOL_CONNECTIONS"]) >= 32


def test_trace_scorers_catch_secret_leaks_and_errors() -> None:
    scorers = {
        s.name: s
        for s in build_trace_scorers(
            latency_sla_ms=100.0, forbidden_tokens=["secret_tok_999"]
        )
    }

    good_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK", execution_duration=25.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="uc_execute_function",
                    status="OK",
                    inputs={"a": 1},
                    outputs={"value": 42},
                    events=[],
                )
            ]
        ),
    )
    assert scorers["tool_execution_success"](trace=good_trace).value is True
    assert (
        scorers["policy_governance_compliance"](
            trace=good_trace,
            expectations={"expected_outcome": "ok", "must_contain": "42"},
        ).value
        is True
    )
    assert scorers["tool_latency_sla"](trace=good_trace).value is True
    assert scorers["secret_redaction_hygiene"](trace=good_trace).value is True
    assert scorers["structured_error_hygiene"](trace=good_trace).value is True

    leaky_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="ERROR", execution_duration=500.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="bad_call",
                    status="ERROR",
                    inputs={"auth": "Bearer secret_tok_999"},
                    outputs={"err": "Traceback (most recent call last):\nBOOM"},
                    events=[],
                )
            ]
        ),
    )
    assert scorers["tool_execution_success"](trace=leaky_trace).value is False
    assert scorers["policy_governance_compliance"](trace=leaky_trace).value is False
    assert scorers["tool_latency_sla"](trace=leaky_trace).value is False
    assert scorers["secret_redaction_hygiene"](trace=leaky_trace).value is False
    assert scorers["structured_error_hygiene"](trace=leaky_trace).value is False


def test_policy_refusal_traces_score_cleanly_including_span_events() -> None:
    scorers = {s.name: s for s in build_trace_scorers()}
    refusal_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="ERROR", execution_duration=12.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="postgres_insert",
                    status="ERROR",
                    inputs={"table_name": "users"},
                    outputs=None,
                    events=[
                        types.SimpleNamespace(
                            name="exception",
                            attributes={
                                "exception.type": "ToolError",
                                "exception.message": (
                                    "PostgreSQL mutations are disabled by policy. "
                                    "Set POSTGRES_ALLOW_MUTATIONS=true."
                                ),
                            },
                        )
                    ],
                )
            ]
        ),
    )
    assert is_expected_policy_refusal(refusal_trace) is True
    assert scorers["tool_execution_success"](trace=refusal_trace).value is True
    assert (
        scorers["policy_governance_compliance"](
            trace=refusal_trace,
            expectations={"expected_outcome": "policy_refusal"},
        ).value
        is True
    )
    assert (
        scorers["policy_governance_compliance"](
            trace=refusal_trace,
            expectations={"expected_outcome": "ok"},
        ).value
        is False
    )


def test_ollama_judge_scorer_uses_local_chat_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: dict, timeout: float):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"value": "yes", "rationale": "Clean structured JSON result."}'
                }
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    scorers = {
        s.name: s
        for s in build_trace_scorers(
            with_llm_judge=True,
            judge_model="ollama:/qwen3.8:27b",
        )
    }
    sample_trace = types.SimpleNamespace(
        info=types.SimpleNamespace(state="OK", execution_duration=10.0),
        data=types.SimpleNamespace(
            spans=[
                types.SimpleNamespace(
                    name="memory_store",
                    status="OK",
                    inputs={"content": "hi"},
                    outputs={"stored": True},
                    events=[],
                )
            ]
        ),
    )
    fb = scorers["tool_response_clarity"](trace=sample_trace)
    assert fb.value == "yes"
    assert "qwen3.8:27b" in fb.rationale
    assert str(captured["url"]).endswith("/api/chat")


def test_invoke_benchmark_tool_runs_ok_and_policy_refusal(make_settings, tmp_path: Path) -> None:
    settings = make_settings()
    (tmp_path / "golden.txt").write_text("golden-benchmark-ok\n", encoding="utf-8")

    ok_res = invoke_benchmark_tool(
        settings,
        workspace_dir=tmp_path,
        server="filesystem",
        tool="fs_read_file",
        arguments={"path": "golden.txt"},
    )
    assert ok_res["ok"] is True
    assert "golden-benchmark" in ok_res["result"]

    refusal = invoke_benchmark_tool(
        settings,
        workspace_dir=tmp_path,
        server="filesystem",
        tool="fs_read_file",
        arguments={"path": "/etc/passwd"},
    )
    assert refusal["ok"] is False
    assert refusal["policy_refusal"] is True


def test_native_judge_model_normalization_and_make_judge() -> None:
    assert normalize_judge_model_uri("ollama:/qwen3.8:27b") == "ollama_chat:/qwen3.8:27b"
    assert normalize_judge_model_uri("openai:/gpt-4o-mini") == "openai:/gpt-4o-mini"

    judge = build_native_clarity_judge("ollama:/qwen3.8:27b")
    assert judge.name == "tool_response_clarity_judge"
    assert getattr(judge, "model", "") == "ollama_chat:/qwen3.8:27b"
