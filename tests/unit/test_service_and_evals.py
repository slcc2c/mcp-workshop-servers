"""Unit tests for LaunchAgent log rotation and MLflow 3.x GenAI trace @scorers."""

from __future__ import annotations

import types
from pathlib import Path

from mcp_stack.evals import build_trace_scorers
from mcp_stack.service import rotate_log_file, rotate_service_logs


def test_log_rotation_caps_size_and_keeps_three_archives(tmp_path: Path) -> None:
    log_file = tmp_path / "gateway.log"
    log_file.write_bytes(b"x" * 2048)

    assert rotate_log_file(log_file, max_bytes=1024, keep=3) is True
    assert (tmp_path / "gateway.log.1").exists()
    assert log_file.stat().st_size == 0

    summary = rotate_service_logs(tmp_path, max_mb=0.001, keep=3)
    assert summary["scanned"] >= 1


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
                )
            ]
        ),
    )
    assert scorers["tool_execution_success"](trace=good_trace).value is True
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
                )
            ]
        ),
    )
    assert scorers["tool_execution_success"](trace=leaky_trace).value is False
    assert scorers["tool_latency_sla"](trace=leaky_trace).value is False
    assert scorers["secret_redaction_hygiene"](trace=leaky_trace).value is False
    assert scorers["structured_error_hygiene"](trace=leaky_trace).value is False
