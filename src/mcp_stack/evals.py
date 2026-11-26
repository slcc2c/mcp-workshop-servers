"""MLflow 3.x GenAI trace evaluation runner, golden benchmark, and scorer registry."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

import httpx

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import get_or_create_gateway_logged_model

# Configure MLflow client env vars BEFORE importing mlflow so session pools match worker counts.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_HTTP_POOL_MAXSIZE", "64")
os.environ.setdefault("MLFLOW_HTTP_POOL_CONNECTIONS", "32")

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9\-_]{12,}"),
)

_POLICY_REFUSAL_MARKERS = (
    "disabled by policy",
    "read-only",
    "escapes allowed",
    "not allowed to access",
    "allow_mutations",
    "allow_execution",
    "resolves outside allowed directories",
    "targets blocked path",
    "permission denied",
)

GOLDEN_DATASET_NAME = "mcp-workshop-golden-v1"

GOLDEN_BENCHMARK_CASES: list[dict[str, Any]] = [
    {
        "inputs": {
            "server": "memory",
            "tool": "memory_store",
            "arguments": {
                "content": "Golden benchmark persistent knowledge entry",
                "type": "fact",
                "tags": ["golden", "benchmark"],
            },
        },
        "expectations": {"expected_outcome": "ok", "must_contain": "stored"},
    },
    {
        "inputs": {
            "server": "filesystem",
            "tool": "fs_read_file",
            "arguments": {"path": "golden.txt"},
        },
        "expectations": {"expected_outcome": "ok", "must_contain": "golden-benchmark"},
    },
    {
        "inputs": {
            "server": "filesystem",
            "tool": "fs_read_file",
            "arguments": {"path": "/etc/passwd"},
        },
        "expectations": {"expected_outcome": "policy_refusal"},
    },
    {
        "inputs": {
            "server": "unity_catalog",
            "tool": "uc_create_catalog",
            "arguments": {"name": "golden_blocked_catalog"},
        },
        "expectations": {"expected_outcome": "policy_refusal"},
    },
    {
        "inputs": {
            "server": "postgresql",
            "tool": "postgres_insert",
            "arguments": {"table_name": "users", "data": {"id": 1}},
        },
        "expectations": {"expected_outcome": "policy_refusal"},
    },
    {
        "inputs": {
            "server": "jupyter",
            "tool": "jupyter_execute_cell",
            "arguments": {"code": "print(1 + 1)"},
        },
        "expectations": {"expected_outcome": "policy_refusal"},
    },
]


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


def _serialized_spans(trace: Any, *, include_stacktrace: bool = True) -> str:
    data = getattr(trace, "data", None)
    spans = getattr(data, "spans", None) or []
    parts: list[str] = []
    for span in spans:
        parts.append(json.dumps(getattr(span, "inputs", None), default=str))
        parts.append(json.dumps(getattr(span, "outputs", None), default=str))
        status = getattr(span, "status", None)
        if status is not None:
            parts.append(json.dumps(status, default=str))
        events = getattr(span, "events", None) or []
        for event in events:
            attrs = getattr(event, "attributes", None)
            if isinstance(attrs, dict) and not include_stacktrace:
                attrs = {k: v for k, v in attrs.items() if k != "exception.stacktrace"}
            ev_payload = {
                "name": getattr(event, "name", None),
                "attributes": attrs,
            }
            parts.append(json.dumps(ev_payload, default=str))
    return "\n".join(parts)


def is_expected_policy_refusal(trace: Any) -> bool:
    """Return True when a trace reflects an intentional read-only or sandbox policy refusal."""
    if trace is None:
        return False
    payload_blob = _serialized_spans(trace, include_stacktrace=False)
    if "Traceback (most recent call last):" in payload_blob:
        return False
    data = getattr(trace, "data", None)
    spans = getattr(data, "spans", None) or []
    for span in spans:
        outputs = getattr(span, "outputs", None)
        if isinstance(outputs, dict) and outputs.get("policy_refusal") is True:
            return True
    lowered = payload_blob.lower()
    return any(marker in lowered for marker in _POLICY_REFUSAL_MARKERS)


def _trace_has_error(trace: Any) -> tuple[bool, list[str]]:
    state_str = str(getattr(getattr(trace, "info", None), "state", ""))
    spans = getattr(getattr(trace, "data", None), "spans", None) or []
    bad_spans = [
        str(getattr(s, "name", "span"))
        for s in spans
        if "ERROR" in str(getattr(s, "status", ""))
    ]
    if bad_spans or "ERROR" in state_str:
        return True, bad_spans
    for span in spans:
        outputs = getattr(span, "outputs", None)
        if isinstance(outputs, dict) and outputs.get("ok") is False:
            return True, [str(getattr(span, "name", "span"))]
    return "OK" not in state_str, bad_spans


def _parse_ollama_judge_json(raw_text: str) -> tuple[str, str]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            raw_val = str(parsed.get("value", "")).strip().lower()
            rationale = str(parsed.get("rationale") or cleaned)[:500]
            if raw_val in {"yes", "true", "pass", "passed", "ok"}:
                return "yes", rationale
            if raw_val in {"no", "false", "fail", "failed"}:
                return "no", rationale
    except Exception:
        pass
    lowered = cleaned.lower()
    if '"value": "yes"' in lowered or lowered.startswith("yes"):
        return "yes", cleaned[:500]
    return "no", cleaned[:500]


def _build_ollama_clarity_scorer(judge_model: str) -> Any:
    import httpx
    from mlflow.entities import Feedback
    from mlflow.genai import scorer

    model_name = judge_model.removeprefix("ollama:/").strip()
    base_url = os.getenv("MCP_EVAL_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

    @scorer(name="tool_response_clarity")
    def tool_response_clarity(trace: Any) -> Feedback:
        snippet = _serialized_spans(trace)[:3500]
        prompt = (
            "Evaluate this MCP tool execution trace. "
            "Criteria: outputs/errors are structured, concise, actionable, and free of raw secrets "
            "or Python tracebacks. Expected read-only policy refusals are valid outputs.\n"
            'Respond ONLY as JSON: {"value": "yes" or "no", "rationale": "<one sentence>"}.\n\n'
            f"TRACE:\n{snippet}"
        )
        try:
            resp = httpx.post(
                f"{base_url}/api/chat",
                json={
                    "model": model_name,
                    "stream": False,
                    "format": "json",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            content = str((data.get("message") or {}).get("content") or "")
            value, rationale = _parse_ollama_judge_json(content)
            return Feedback(value=value, rationale=f"[{model_name}] {rationale}")
        except Exception as exc:
            return Feedback(
                value="no",
                rationale=f"Ollama judge call failed for '{model_name}': {exc}",
            )

    return tool_response_clarity


def normalize_judge_model_uri(judge_model: str | None = None) -> str:
    """Normalize local Ollama / cloud judge URIs for LiteLLM + MLflow make_judge()."""
    raw = (
        judge_model
        or os.getenv("MCP_EVAL_OLLAMA_MODEL")
        or "ollama:/qwen3.8:27b"
    ).strip()
    if raw.startswith("ollama:/"):
        return "ollama_chat:/" + raw.removeprefix("ollama:/").lstrip("/")
    if raw.startswith("ollama:"):
        return "ollama_chat:/" + raw.removeprefix("ollama:").lstrip("/")
    return raw


def is_typesafe_judge_model(
    judge_model: str | None,
    model_api: str | None = None,
) -> bool:
    """Return True when the requested judge uses TypeSafe System One (`typesafe:/` or decisions)."""
    if (model_api or "").strip().lower() == "decisions":
        return True
    return bool(judge_model and judge_model.strip().lower().startswith("typesafe:/"))


def _ensure_typesafe_api_key(settings: MCPStackSettings | None = None) -> None:
    raw = os.getenv("TYPESAFE_API_KEY", "").strip()
    if raw.startswith(("env:", "op://")) and settings is not None:
        from mcp_stack.core.secrets import SecretResolver

        resolved = SecretResolver(settings.secrets).resolve(raw)
        if resolved:
            os.environ["TYPESAFE_API_KEY"] = resolved


def build_native_clarity_judge(
    judge_model: str | None = None,
    *,
    model_api: str = "default",
    settings: MCPStackSettings | None = None,
) -> Any:
    """Build a native MLflow 3.x LLM judge using mlflow.genai.judges.make_judge()."""
    from mlflow.genai.judges import make_judge

    ollama_url = os.getenv("MCP_EVAL_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    os.environ.setdefault("OLLAMA_API_BASE", ollama_url)
    normalized = normalize_judge_model_uri(judge_model)
    if is_typesafe_judge_model(normalized, model_api):
        _ensure_typesafe_api_key(settings)
        # TypeSafe System One decision models evaluate inputs/outputs/expectations (no {{ trace }})
        return make_judge(
            name="tool_response_clarity_typesafe",
            instructions=(
                "Answer yes or no: Is the response in {{ outputs }} structured, concise, "
                "actionable, free of exposed secrets or Python tracebacks, and consistent with "
                "{{ inputs }} and {{ expectations }}?"
            ),
            model=normalized,
            model_api="decisions",
            feedback_value_type=bool,
        )
    return make_judge(
        name="tool_response_clarity_judge",
        instructions=(
            "Evaluate the MCP tool execution trace in {{ trace }}. "
            "Return 'yes' if outputs or intentional read-only/sandbox policy refusals are "
            "structured, concise, actionable, and free of exposed secrets or Python tracebacks; "
            "otherwise return 'no'."
        ),
        model=normalized,
        feedback_value_type=Literal["yes", "no"],
    )


def build_trace_scorers(
    *,
    latency_sla_ms: float = 5000.0,
    forbidden_tokens: list[str] | None = None,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
    model_api: str = "default",
    settings: MCPStackSettings | None = None,
) -> list[Any]:
    """Build deterministic MLflow 3.x GenAI @scorers plus optional local Ollama / LLM judge."""
    from mlflow.entities import Feedback
    from mlflow.genai import scorer

    secret_literals = [t for t in (forbidden_tokens or []) if t and len(t) >= 8]

    @scorer(name="tool_execution_success")
    def tool_execution_success(trace: Any) -> Feedback:
        has_err, bad_spans = _trace_has_error(trace)
        if not has_err:
            return Feedback(value=True, rationale="Trace OK")
        if is_expected_policy_refusal(trace):
            return Feedback(
                value=True,
                rationale="Expected read-only or sandbox policy refusal",
            )
        state_str = str(getattr(getattr(trace, "info", None), "state", ""))
        return Feedback(
            value=False,
            rationale=f"state={state_str}, bad_spans={bad_spans}",
        )

    @scorer(name="policy_governance_compliance")
    def policy_governance_compliance(
        trace: Any = None,
        outputs: Any = None,
        expectations: dict[str, Any] | None = None,
    ) -> Feedback:
        blob = (
            _serialized_spans(trace, include_stacktrace=False)
            if trace is not None
            else json.dumps(outputs, default=str)
        )
        if "Traceback (most recent call last):" in blob:
            return Feedback(
                value=False,
                rationale="Policy/tool failure exposed a raw Python traceback",
            )

        is_refusal = (
            is_expected_policy_refusal(trace)
            if trace is not None
            else any(m in blob.lower() for m in _POLICY_REFUSAL_MARKERS)
        )
        expected_outcome = (expectations or {}).get("expected_outcome")
        if expected_outcome == "policy_refusal":
            return Feedback(
                value=is_refusal,
                rationale=(
                    "Matched expected governance policy refusal"
                    if is_refusal
                    else "Expected policy refusal but operation succeeded or failed unexpectedly"
                ),
            )
        if expected_outcome == "ok":
            has_err, bad_spans = _trace_has_error(trace) if trace is not None else (False, [])
            if has_err or is_refusal:
                return Feedback(
                    value=False,
                    rationale=f"Expected success but got refusal/error (bad_spans={bad_spans})",
                )
            must_contain = (expectations or {}).get("must_contain")
            if must_contain and str(must_contain) not in blob:
                return Feedback(
                    value=False,
                    rationale=f"Expected substring '{must_contain}' missing from tool output",
                )
            return Feedback(value=True, rationale="Matched expected tool execution outcome")

        if is_refusal:
            return Feedback(value=True, rationale="Structured governance policy refusal")
        return Feedback(value=True, rationale="No governance policy violation detected")

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
        blob = _serialized_spans(trace, include_stacktrace=False)
        has_tb = "Traceback (most recent call last):" in blob
        return Feedback(
            value=not has_tb,
            rationale="Raw Python traceback exposed" if has_tb else "Clean span payloads",
        )

    scorers: list[Any] = [
        tool_execution_success,
        policy_governance_compliance,
        tool_latency_sla,
        secret_redaction_hygiene,
        structured_error_hygiene,
    ]
    if with_llm_judge:
        effective_model = (
            judge_model
            or os.getenv("MCP_EVAL_OLLAMA_MODEL")
            or "ollama:/qwen3.8:27b"
        )
        has_litellm = importlib.util.find_spec("litellm") is not None
        is_ollama = effective_model.startswith(("ollama:/", "ollama:", "ollama_chat:/"))
        is_typesafe = is_typesafe_judge_model(effective_model, model_api)
        if has_litellm or is_typesafe or not is_ollama:
            scorers.append(
                build_native_clarity_judge(
                    effective_model, model_api=model_api, settings=settings
                )
            )
        else:
            scorers.append(_build_ollama_clarity_scorer(effective_model))

    return scorers


def sync_golden_dataset(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    dataset_name: str = GOLDEN_DATASET_NAME,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Idempotently create/update a versioned MLflow GenAI dataset for golden MCP evals."""
    import mlflow
    from mlflow.genai.datasets import create_dataset, search_datasets

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    exp = mlflow.set_experiment(exp_target)

    existing = search_datasets(
        experiment_ids=[exp.experiment_id],
        filter_string=f"name = '{dataset_name}'",
        max_results=5,
    )
    if existing:
        dataset = existing[0]
        action = "updated"
    else:
        dataset = create_dataset(
            name=dataset_name,
            experiment_id=exp.experiment_id,
            tags={"suite": "mcp-workshop-golden", "schema": "v1"},
        )
        action = "created"

    records = cases if cases is not None else GOLDEN_BENCHMARK_CASES
    dataset.merge_records(records)
    return {
        "status": action,
        "dataset_name": dataset_name,
        "dataset_id": getattr(dataset, "dataset_id", None),
        "experiment": exp_target,
        "experiment_id": exp.experiment_id,
        "record_count": len(records),
    }


def register_experiment_scorers(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    judge_model: str | None = None,
    online_sample_rate: float = 1.0,
) -> dict[str, Any]:
    """Register built-in online guards, native make_judge(), and deterministic scorers."""
    import mlflow
    from mlflow.exceptions import MlflowException
    from mlflow.genai import list_scorers
    from mlflow.genai.scorers import RegexMatch, ScorerSamplingConfig

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    exp = mlflow.set_experiment(exp_target)

    existing_map = {s.name: s for s in list_scorers(experiment_id=exp.experiment_id)}
    no_traceback_guard = RegexMatch(
        name="no_traceback_guard",
        pattern=r"^(?![\s\S]*Traceback \(most recent call last\):)[\s\S]*$",
    )
    no_secret_leak_guard = RegexMatch(
        name="no_secret_leak_guard",
        pattern=(
            r"^(?![\s\S]*(?:ghp_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9\-_]{20,}|"
            r"Bearer\s+[A-Za-z0-9._\-]{16,}))[\s\S]*$"
        ),
    )
    builtin_guards = [no_traceback_guard, no_secret_leak_guard]
    clarity_judge = build_native_clarity_judge(judge_model)
    custom_scorers = build_trace_scorers()

    results: dict[str, dict[str, Any]] = {}

    for guard in builtin_guards:
        reg_status = "already_registered"
        target_scorer = existing_map.get(guard.name)
        if target_scorer is None:
            try:
                target_scorer = guard.register(name=guard.name, experiment_id=exp.experiment_id)
                reg_status = "registered"
            except Exception as exc:
                results[guard.name] = {"status": "error", "detail": str(exc)[:250]}
                continue
        entry: dict[str, Any] = {"status": reg_status}
        if online_sample_rate > 0:
            try:
                started = target_scorer.start(
                    name=guard.name,
                    experiment_id=exp.experiment_id,
                    sampling_config=ScorerSamplingConfig(sample_rate=online_sample_rate),
                )
                entry["online_sampling_rate"] = getattr(started, "sample_rate", online_sample_rate)
            except Exception as exc:
                msg = str(exc)
                if "gateway model" in msg.lower():
                    entry["online_mode"] = "unsupported_without_gateway_model"
                    entry["online_detail"] = msg[:200]
                else:
                    entry["online_error"] = msg[:200]
        results[guard.name] = entry

    # Register native LLM judge on-demand (sample_rate=None; no automatic background LLM calls)
    if clarity_judge.name in existing_map:
        results[clarity_judge.name] = {"status": "already_registered", "mode": "on_demand"}
    else:
        try:
            clarity_judge.register(name=clarity_judge.name, experiment_id=exp.experiment_id)
            results[clarity_judge.name] = {"status": "registered", "mode": "on_demand"}
        except Exception as exc:
            results[clarity_judge.name] = {"status": "error", "detail": str(exc)[:250]}

    for item in custom_scorers:
        if item.name in existing_map:
            results[item.name] = {"status": "already_registered"}
            continue
        try:
            item.register(name=item.name, experiment_id=exp.experiment_id)
            results[item.name] = {"status": "registered"}
        except MlflowException as exc:
            msg = str(exc)
            if "MLFLOW_SERVER_ENABLE_CUSTOM_SCORERS" in msg or "Custom scorer" in msg:
                results[item.name] = {
                    "status": "skipped_server_policy",
                    "detail": (
                        "Server disabled custom @scorer registration; runs inline during evaluate()"
                    ),
                }
            elif "already exists" in msg.lower():
                results[item.name] = {"status": "already_registered"}
            else:
                results[item.name] = {"status": "error", "detail": msg[:250]}
        except Exception as exc:
            results[item.name] = {"status": "error", "detail": str(exc)[:250]}

    return {
        "experiment": exp_target,
        "experiment_id": exp.experiment_id,
        "scorers": results,
    }


def invoke_benchmark_tool(
    settings: MCPStackSettings,
    *,
    workspace_dir: Path,
    server: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute one MCP tool call in-process against read-only FastMCP servers."""
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    from mcp_stack.core.config import (
        FilesystemSettings,
        JupyterSettings,
        MemorySettings,
        PostgreSQLSettings,
        UnityCatalogSettings,
    )
    from mcp_stack.servers.filesystem import create_filesystem_server
    from mcp_stack.servers.jupyter_server import create_jupyter_server
    from mcp_stack.servers.memory import create_memory_server
    from mcp_stack.servers.postgresql import create_postgresql_server
    from mcp_stack.servers.unity_catalog import create_unity_catalog_server

    bench_settings = settings.model_copy(
        update={
            "mlflow": settings.mlflow.model_copy(update={"tracing_enabled": False}),
            "memory": MemorySettings(
                db_path=workspace_dir / "memory.db",
                legacy_json_path=workspace_dir / "missing-legacy.json",
            ),
            "filesystem": FilesystemSettings(allowed_paths=[workspace_dir]),
            "unity_catalog": UnityCatalogSettings(
                mode="oss",
                base_url="http://127.0.0.1:0",
                allow_mutations=False,
            ),
            "postgresql": PostgreSQLSettings(allow_mutations=False),
            "jupyter": JupyterSettings(
                notebook_dir=workspace_dir,
                allow_execution=False,
            ),
        }
    )

    factories = {
        "memory": lambda: create_memory_server(bench_settings),
        "filesystem": lambda: create_filesystem_server(bench_settings),
        "unity_catalog": lambda: create_unity_catalog_server(bench_settings),
        "postgresql": lambda: create_postgresql_server(bench_settings),
        "jupyter": lambda: create_jupyter_server(bench_settings),
    }
    if server not in factories:
        return {"ok": False, "policy_refusal": False, "error": f"Unknown server '{server}'"}

    async def _run() -> dict[str, Any]:
        srv = factories[server]()
        async with Client(srv) as client:
            try:
                res = await client.call_tool(tool, arguments)
                text = "".join(
                    str(getattr(block, "text", block)) for block in (res.content or [])
                )
                return {"ok": True, "policy_refusal": False, "result": text[:1000]}
            except ToolError as exc:
                msg = str(exc)
                lowered = msg.lower()
                is_refusal = any(m in lowered for m in _POLICY_REFUSAL_MARKERS)
                return {"ok": False, "policy_refusal": is_refusal, "error": msg}

    return asyncio.run(_run())


def run_golden_benchmark(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    dataset_name: str = GOLDEN_DATASET_NAME,
    latency_sla_ms: float = 5000.0,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
    model_api: str = "default",
) -> dict[str, Any]:
    """Run executable golden benchmark against mlflow.genai.datasets via mlflow.genai.evaluate()."""
    import mlflow
    import mlflow.genai
    from mlflow.genai.datasets import search_datasets

    sync_info = sync_golden_dataset(
        settings,
        experiment_name=experiment_name,
        dataset_name=dataset_name,
    )
    exp_target = str(sync_info["experiment"])
    exp_id = str(sync_info["experiment_id"])
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    mlflow.set_experiment(exp_target)

    datasets = search_datasets(
        experiment_ids=[exp_id],
        filter_string=f"name = '{dataset_name}'",
        max_results=1,
    )
    dataset = datasets[0]

    with tempfile.TemporaryDirectory(prefix="mcp-golden-") as tmp_dir:
        workspace = Path(tmp_dir)
        (workspace / "golden.txt").write_text("golden-benchmark-ok\n", encoding="utf-8")

        @mlflow.trace(name="mcp_golden_tool_call", span_type="TOOL")
        def predict_fn(server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
            with contextlib.suppress(Exception):
                mlflow.update_current_trace(
                    user="golden-benchmark",
                    tags={
                        "mcp.server": str(server),
                        "mcp.tool": str(tool),
                        "mcp.profile": "benchmark",
                    },
                )
            return invoke_benchmark_tool(
                settings,
                workspace_dir=workspace,
                server=server,
                tool=tool,
                arguments=arguments,
            )

        scorers = build_trace_scorers(
            latency_sla_ms=latency_sla_ms,
            forbidden_tokens=list(settings.gateway.clients.keys()),
            with_llm_judge=with_llm_judge,
            judge_model=judge_model,
            model_api=model_api,
            settings=settings,
        )
        model_id = get_or_create_gateway_logged_model(settings, experiment_name=exp_target)
        eval_kwargs: dict[str, Any] = {
            "data": dataset,
            "predict_fn": predict_fn,
            "scorers": scorers,
        }
        if model_id:
            eval_kwargs["model_id"] = model_id
        result = mlflow.genai.evaluate(**eval_kwargs)

    return {
        "status": "completed",
        "dataset_name": dataset_name,
        "dataset_id": sync_info.get("dataset_id"),
        "experiment": exp_target,
        "experiment_id": exp_id,
        "model_id": model_id,
        "run_id": getattr(result, "run_id", None),
        "record_count": sync_info.get("record_count"),
        "metrics": dict(getattr(result, "metrics", {}) or {}),
    }


def run_trace_evaluation(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    limit: int = 20,
    latency_sla_ms: float = 5000.0,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
    model_api: str = "default",
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
        model_api=model_api,
        settings=settings,
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


def list_eval_datasets(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    max_results: int = 25,
) -> dict[str, Any]:
    """List MLflow GenAI evaluation datasets for the active experiment."""
    import mlflow
    from mlflow.genai.datasets import search_datasets

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    exp = client.get_experiment_by_name(exp_target)
    if exp is None:
        return {"available": True, "experiment": exp_target, "datasets": []}

    datasets = search_datasets(
        experiment_ids=[exp.experiment_id],
        max_results=max(1, min(max_results, 100)),
    )
    out: list[dict[str, Any]] = []
    for ds in datasets:
        records = _extract_dataset_records(ds)
        out.append(
            {
                "datasetId": getattr(ds, "dataset_id", None),
                "name": getattr(ds, "name", None),
                "createdTime": getattr(ds, "created_time", None),
                "digest": getattr(ds, "digest", None),
                "tags": dict(getattr(ds, "tags", None) or {}),
                "recordCount": len(records),
            }
        )
    return {"available": True, "experiment": exp_target, "datasets": out}


def _extract_dataset_records(dataset: Any) -> list[dict[str, Any]]:
    try:
        to_df = getattr(dataset, "to_df", None)
        if callable(to_df):
            df = to_df()
            rows = df.to_dict(orient="records")
            return json.loads(json.dumps(rows, default=str))
    except Exception:
        pass
    try:
        to_dict = getattr(dataset, "to_dict", None)
        if callable(to_dict):
            d = to_dict()
            recs = d.get("records") if isinstance(d, dict) else None
            if isinstance(recs, list):
                return json.loads(json.dumps(recs, default=str))
    except Exception:
        pass
    return []


def get_eval_dataset(
    settings: MCPStackSettings,
    dataset_id: str,
) -> dict[str, Any]:
    """Fetch a dataset and its records by dataset_id."""
    import mlflow
    from mlflow.genai.datasets import get_dataset

    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    ds = get_dataset(dataset_id=dataset_id)
    records = _extract_dataset_records(ds)
    return {
        "datasetId": getattr(ds, "dataset_id", dataset_id),
        "name": getattr(ds, "name", None),
        "createdTime": getattr(ds, "created_time", None),
        "digest": getattr(ds, "digest", None),
        "tags": dict(getattr(ds, "tags", None) or {}),
        "recordCount": len(records),
        "records": records,
    }


def merge_dataset_records(
    settings: MCPStackSettings,
    dataset_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append or merge new test records into an existing MLflow GenAI dataset."""
    import mlflow
    from mlflow.genai.datasets import get_dataset

    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    ds = get_dataset(dataset_id=dataset_id)
    ds.merge_records(records)
    updated = _extract_dataset_records(ds)
    return {
        "merged": True,
        "datasetId": getattr(ds, "dataset_id", dataset_id),
        "name": getattr(ds, "name", None),
        "addedCount": len(records),
        "recordCount": len(updated),
    }


def _extract_typesafe_prob(item: Any) -> float | None:
    feedback = getattr(item, "feedback", None)
    meta = dict(getattr(item, "metadata", None) or {})
    if feedback is not None:
        meta.update(dict(getattr(feedback, "metadata", None) or {}))
    for key in ("typesafe.probability", "probability"):
        if key in meta and meta[key] is not None:
            try:
                return round(float(meta[key]), 4)
            except Exception:
                pass
    return None


def list_eval_runs(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """List recent MLflow GenAI evaluation runs with metrics and params."""
    import mlflow

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    exp = client.get_experiment_by_name(exp_target)
    if exp is None:
        return {"available": True, "experiment": exp_target, "runs": []}

    runs = client.search_runs(
        [exp.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=max(1, min(limit * 2, 100)),
    )
    out: list[dict[str, Any]] = []
    for run in runs:
        metrics = {
            k: round(float(v), 4)
            for k, v in (run.data.metrics or {}).items()
            if "/" in k or "tool_" in k or "policy_" in k or "clarity" in k
        }
        if not metrics:
            continue
        out.append(
            {
                "runId": run.info.run_id,
                "runName": getattr(run.info, "run_name", None),
                "status": getattr(run.info, "status", None),
                "startTimeMs": getattr(run.info, "start_time", None),
                "endTimeMs": getattr(run.info, "end_time", None),
                "params": dict(run.data.params or {}),
                "tags": {
                    k: v
                    for k, v in dict(run.data.tags or {}).items()
                    if not k.startswith("mlflow.log-model")
                },
                "metrics": metrics,
            }
        )
        if len(out) >= limit:
            break
    return {"available": True, "experiment": exp_target, "runs": out}


def get_eval_run_detail(
    settings: MCPStackSettings,
    run_id: str,
) -> dict[str, Any]:
    """Return aggregate metrics and per-row scorer feedback (with typesafe.probability)."""
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    run = client.get_run(run_id)
    metrics = {k: round(float(v), 4) for k, v in (run.data.metrics or {}).items()}
    traces = client.search_traces(run_id=run_id, max_results=200)

    rows: list[dict[str, Any]] = []
    for tr in traces:
        info = getattr(tr, "info", tr)
        spans = getattr(getattr(tr, "data", None), "spans", None) or []
        root = spans[0] if spans else None
        assessments_out: list[dict[str, Any]] = []
        for item in getattr(info, "assessments", None) or []:
            fb = getattr(item, "feedback", None)
            val = getattr(fb, "value", None) if fb is not None else getattr(item, "value", None)
            assessments_out.append(
                {
                    "name": getattr(item, "name", None),
                    "value": val,
                    "rationale": getattr(item, "rationale", None),
                    "typesafeProbability": _extract_typesafe_prob(item),
                }
            )
        rows.append(
            {
                "traceId": getattr(info, "trace_id", None) or getattr(info, "request_id", None),
                "state": str(getattr(info, "state", "")),
                "durationMs": round(_trace_duration_ms(tr), 1),
                "inputs": json.loads(json.dumps(getattr(root, "inputs", None), default=str))
                if root
                else None,
                "outputs": json.loads(json.dumps(getattr(root, "outputs", None), default=str))
                if root
                else None,
                "assessments": assessments_out,
            }
        )

    return {
        "runId": run.info.run_id,
        "runName": getattr(run.info, "run_name", None),
        "status": getattr(run.info, "status", None),
        "startTimeMs": getattr(run.info, "start_time", None),
        "metrics": metrics,
        "params": dict(run.data.params or {}),
        "rows": rows,
    }


def compare_eval_runs(
    settings: MCPStackSettings,
    run_a: str,
    run_b: str,
) -> dict[str, Any]:
    """Compare two MLflow GenAI eval runs and compute per-metric deltas."""
    detail_a = get_eval_run_detail(settings, run_a)
    detail_b = get_eval_run_detail(settings, run_b)
    keys = sorted(set(detail_a["metrics"].keys()) | set(detail_b["metrics"].keys()))
    deltas: list[dict[str, Any]] = []
    for k in keys:
        va = detail_a["metrics"].get(k)
        vb = detail_b["metrics"].get(k)
        delta = (
            round(float(vb) - float(va), 4)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float))
            else None
        )
        deltas.append(
            {
                "metric": k,
                "runA": va,
                "runB": vb,
                "delta": delta,
                "direction": (
                    "improved"
                    if isinstance(delta, float) and delta > 0
                    else ("regressed" if isinstance(delta, float) and delta < 0 else "unchanged")
                ),
            }
        )
    return {
        "runA": {
            "runId": detail_a["runId"],
            "runName": detail_a["runName"],
            "metrics": detail_a["metrics"],
            "rowCount": len(detail_a["rows"]),
        },
        "runB": {
            "runId": detail_b["runId"],
            "runName": detail_b["runName"],
            "metrics": detail_b["metrics"],
            "rowCount": len(detail_b["rows"]),
        },
        "deltas": deltas,
    }


def run_agent_dataset_evaluation(
    settings: MCPStackSettings,
    *,
    dataset_name: str = GOLDEN_DATASET_NAME,
    experiment_name: str | None = None,
    profile: str | None = None,
    model: str | None = None,
    with_llm_judge: bool = False,
    judge_model: str | None = None,
    model_api: str = "default",
) -> dict[str, Any]:
    """Run mlflow.genai.evaluate() against the co-hosted ResponsesAgent /invocations."""
    import mlflow
    import mlflow.genai
    from mlflow.genai.datasets import search_datasets

    exp_target = experiment_name or settings.mlflow.experiment_name
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    exp = mlflow.set_experiment(exp_target)
    datasets = search_datasets(
        experiment_ids=[exp.experiment_id],
        filter_string=f"name = '{dataset_name}'",
        max_results=1,
    )
    if not datasets:
        raise ValueError(f"Dataset '{dataset_name}' not found in experiment '{exp_target}'")
    dataset = datasets[0]
    agent_url = f"{settings.agent.url.rstrip('/')}/invocations"

    @mlflow.trace(name="agent_eval_invocation", span_type="CHAIN")
    def predict_fn(**row_inputs: Any) -> str:
        prompt = json.dumps(row_inputs, default=str)
        custom_inputs: dict[str, Any] = {}
        if profile:
            custom_inputs["profile"] = profile
        if model:
            custom_inputs["model"] = model
        resp = httpx.post(
            agent_url,
            json={
                "input": [{"role": "user", "content": prompt}],
                "custom_inputs": custom_inputs,
            },
            timeout=settings.agent.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        texts: list[str] = []
        for out in data.get("output") or []:
            content = out.get("content")
            if isinstance(content, list):
                texts.extend(str(c.get("text") or "") for c in content if isinstance(c, dict))
            elif isinstance(content, str):
                texts.append(content)
        return "\n".join(t for t in texts if t) or json.dumps(data, default=str)

    scorers = build_trace_scorers(
        forbidden_tokens=list(settings.gateway.clients.keys()),
        with_llm_judge=with_llm_judge,
        judge_model=judge_model,
        model_api=model_api,
        settings=settings,
    )
    result = mlflow.genai.evaluate(data=dataset, predict_fn=predict_fn, scorers=scorers)
    return {
        "status": "completed",
        "mode": "agent",
        "dataset_name": dataset_name,
        "experiment": exp_target,
        "run_id": getattr(result, "run_id", None),
        "metrics": dict(getattr(result, "metrics", {}) or {}),
    }
