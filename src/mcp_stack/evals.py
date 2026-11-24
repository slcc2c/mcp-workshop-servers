"""MLflow 3.x GenAI trace evaluation runner using mlflow.genai.evaluate() and @scorer."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from mcp_stack.core.config import MCPStackSettings

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9\-_]{12,}"),
)


def _trace_duration_ms(trace: Any) -> float:
    info = getattr(trace, "info", None)
    dur = getattr(info, "execution_duration", None)
    if dur is not None:
        return float(dur)
    data = getattr(trace, "data", None)
    spans = getattr(data, "spans", None) or []
    if not spans:
        return 0.0
    starts = [getattr(s, "start_time_ns", 0) or 0 for s in spans]
    ends = [getattr(s, "end_time_ns", 0) or 0 for s in spans]
    if max(ends) <= min(starts):
        return 0.0
    return (max(ends) - min(starts)) / 1_000_000.0


def _serialized_spans(trace: Any) -> str:
    data = getattr(trace, "data", None)
    spans = getattr(data, "spans", None) or []
    parts: list[str] = []
    for span in spans:
        parts.append(json.dumps(getattr(span, "inputs", None), default=str))
        parts.append(json.dumps(getattr(span, "outputs", None), default=str))
    return "\n".join(parts)


def build_trace_scorers(
    *,
    latency_sla_ms: float = 5000.0,
    forbidden_tokens: list[str] | None = None,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
) -> list[Any]:
    """Build deterministic MLflow 3.x GenAI @scorers plus optional LLM Guidelines judge."""
    from mlflow.entities import Feedback
    from mlflow.genai import scorer

    secret_literals = [t for t in (forbidden_tokens or []) if t and len(t) >= 8]

    @scorer(name="tool_execution_success")
    def tool_execution_success(trace: Any) -> Feedback:
        state_str = str(getattr(getattr(trace, "info", None), "state", ""))
        spans = getattr(getattr(trace, "data", None), "spans", None) or []
        bad_spans = [
            getattr(s, "name", "span")
            for s in spans
            if "ERROR" in str(getattr(s, "status", ""))
        ]
        ok = ("OK" in state_str) and not bad_spans
        rationale = "Trace OK" if ok else f"state={state_str}, bad_spans={bad_spans}"
        return Feedback(value=ok, rationale=rationale)

    @scorer(name="tool_latency_sla")
    def tool_latency_sla(trace: Any) -> Feedback:
        dur_ms = _trace_duration_ms(trace)
        ok = dur_ms <= latency_sla_ms
        return Feedback(
            value=ok,
            rationale=f"duration={dur_ms:.1f}ms (sla={latency_sla_ms:.1f}ms)",
        )

    @scorer(name="secret_redaction_hygiene")
    def secret_redaction_hygiene(trace: Any) -> Feedback:
        blob = _serialized_spans(trace)
        for pat in _SECRET_PATTERNS:
            if pat.search(blob):
                return Feedback(value=False, rationale=f"Matched unredacted pattern {pat.pattern}")
        for lit in secret_literals:
            if lit in blob:
                return Feedback(value=False, rationale="Matched configured raw secret token")
        return Feedback(value=True, rationale="No secret patterns detected in spans")

    @scorer(name="structured_error_hygiene")
    def structured_error_hygiene(trace: Any) -> Feedback:
        blob = _serialized_spans(trace)
        has_tb = "Traceback (most recent call last):" in blob
        return Feedback(
            value=not has_tb,
            rationale="Raw Python traceback exposed" if has_tb else "Clean span payloads",
        )

    scorers: list[Any] = [
        tool_execution_success,
        tool_latency_sla,
        secret_redaction_hygiene,
        structured_error_hygiene,
    ]
    if with_llm_judge:
        from mlflow.genai.scorers import Guidelines

        kwargs: dict[str, Any] = {
            "name": "tool_response_clarity",
            "guidelines": (
                "Tool calls should produce structured, concise JSON/text results "
                "and actionable error messages without exposing secrets."
            ),
        }
        if judge_model:
            kwargs["model"] = judge_model
        scorers.append(Guidelines(**kwargs))

    return scorers


def run_trace_evaluation(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    limit: int = 20,
    latency_sla_ms: float = 5000.0,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Run mlflow.genai.evaluate() over recent MCP gateway traces."""
    import mlflow
    import mlflow.genai
    from mlflow.genai.evaluation.utils import traces_to_df

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    exp = client.get_experiment_by_name(exp_target)
    if exp is None:
        return {
            "status": "no_experiment",
            "experiment": exp_target,
            "trace_count": 0,
            "metrics": {},
        }

    traces = client.search_traces(
        locations=[exp.experiment_id],
        max_results=limit,
        order_by=["timestamp_ms DESC"],
    )
    if not traces:
        return {
            "status": "no_traces",
            "experiment": exp_target,
            "experiment_id": exp.experiment_id,
            "trace_count": 0,
            "metrics": {},
        }

    mlflow.set_experiment(exp_target)
    scorers = build_trace_scorers(
        latency_sla_ms=latency_sla_ms,
        forbidden_tokens=list(settings.gateway.clients.keys()),
        with_llm_judge=with_llm_judge,
        judge_model=judge_model,
    )
    eval_df = traces_to_df(list(traces))
    result = mlflow.genai.evaluate(data=eval_df, scorers=scorers)
    return {
        "status": "completed",
        "experiment": exp_target,
        "experiment_id": exp.experiment_id,
        "run_id": getattr(result, "run_id", None),
        "trace_count": len(traces),
        "metrics": dict(getattr(result, "metrics", {}) or {}),
    }
