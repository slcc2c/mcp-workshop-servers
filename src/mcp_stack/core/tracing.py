"""Fail-open MLflow 3.x tracing + LoggedModel versioning + Prometheus metrics for FastMCP."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from mcp_stack import __version__
from mcp_stack.core.auth import (
    caller_client_id_var,
    caller_profile_var,
    caller_session_id_var,
)
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.metrics import (
    mcp_active_requests,
    mcp_mlflow_trace_failures_total,
    mcp_tool_calls_total,
    mcp_tool_duration_seconds,
)

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|authorization|api_key|apikey|credential|private_key)",
    re.IGNORECASE,
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
_MAX_STR_LEN = 4000
_GIT_SHA_CACHE: str | None = None
_LOGGED_MODEL_CACHE: dict[tuple[str, str, str], str] = {}


def _short_git_sha() -> str:
    global _GIT_SHA_CACHE
    if _GIT_SHA_CACHE is not None:
        return _GIT_SHA_CACHE
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        ).strip()
        _GIT_SHA_CACHE = sha or "nogit"
    except Exception:
        _GIT_SHA_CACHE = "nogit"
    return _GIT_SHA_CACHE


def get_or_create_gateway_logged_model(
    settings: MCPStackSettings,
    *,
    experiment_name: str | None = None,
) -> str | None:
    """Resolve or lazily create an MLflow 3.x LoggedModel for the gateway version + git SHA."""
    exp_target = experiment_name or settings.mlflow.experiment_name
    git_sha = _short_git_sha()
    # MLflow rejects '/', ':', '.', '%', quotes in LoggedModel names.
    safe_version = re.sub(r"[/.:%'\"]+", "-", __version__).strip("-") or "0"
    safe_sha = re.sub(r"[/.:%'\"]+", "-", git_sha).strip("-") or "nogit"
    model_name = f"mcp-workshop-gateway-{safe_version}-{safe_sha}"
    cache_key = (settings.mlflow.tracking_uri, exp_target, model_name)
    if cache_key in _LOGGED_MODEL_CACHE:
        return _LOGGED_MODEL_CACHE[cache_key]

    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        exp = mlflow.set_experiment(exp_target)
        client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
        existing = client.search_logged_models(
            experiment_ids=[exp.experiment_id],
            filter_string=f"name = '{model_name}'",
            max_results=1,
        )
        if existing:
            model_id = str(existing[0].model_id)
        else:
            created = mlflow.create_external_model(
                name=model_name,
                experiment_id=exp.experiment_id,
                tags={
                    "component": "mcp-workshop-gateway",
                    "version": __version__,
                    "git_sha": git_sha,
                },
            )
            model_id = str(created.model_id)
        _LOGGED_MODEL_CACHE[cache_key] = model_id
        return model_id
    except Exception:
        return None


def redact_payload(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and truncate large payloads for tracing."""
    if depth > 6:
        return "<truncated-depth>"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if _SENSITIVE_KEY_RE.search(key_str):
                sanitized[key_str] = "<redacted>"
            else:
                sanitized[key_str] = redact_payload(v, depth=depth + 1)
        return sanitized
    if isinstance(value, (list, tuple)):
        items = [redact_payload(v, depth=depth + 1) for v in value[:50]]
        if len(value) > 50:
            items.append(f"...(+{len(value) - 50} more)")
        return items
    if isinstance(value, str):
        if len(value) > _MAX_STR_LEN:
            return value[:_MAX_STR_LEN] + f"...<truncated {len(value) - _MAX_STR_LEN} chars>"
        return value
    return value


class MLflowTracingMiddleware(Middleware):
    """Instrument FastMCP tool calls with Prometheus metrics and fail-open MLflow 3.x spans."""

    def __init__(
        self,
        settings: MCPStackSettings,
        server_name: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self.server_name = server_name
        self._clock = clock
        self._logger = get_logger(f"tracing.{server_name}")
        self._circuit_open_until: float = 0.0
        self._experiment_configured: bool = False

    def _is_circuit_open(self) -> bool:
        return self._clock() < self._circuit_open_until

    def _trip_circuit(self, reason: str, exc: Exception) -> None:
        cooldown = max(1.0, self._settings.mlflow.circuit_breaker_cooldown_s)
        if not self._is_circuit_open():
            self._logger.warning(
                "MLflow tracing unavailable; opening fail-open circuit breaker",
                server=self.server_name,
                cooldown_s=cooldown,
                error=str(exc),
            )
        self._circuit_open_until = self._clock() + cooldown
        mcp_mlflow_trace_failures_total.labels(reason=reason).inc()

    def _configure_mlflow(self) -> Any:
        import mlflow

        if not self._experiment_configured:
            mlflow.set_tracking_uri(self._settings.mlflow.tracking_uri)
            mlflow.set_experiment(self._settings.mlflow.experiment_name)
            self._experiment_configured = True
        return mlflow

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name = context.message.name
        raw_args = context.message.arguments or {}
        start = self._clock()
        status = "success"

        mcp_active_requests.labels(server=self.server_name).inc()
        try:
            use_mlflow = (
                self._settings.mlflow.tracing_enabled and not self._is_circuit_open()
            )
            if not use_mlflow:
                return await call_next(context)

            span_ctx = None
            span = None
            mlflow_mod: Any = None
            try:
                mlflow_mod = self._configure_mlflow()
                from mlflow.entities import SpanType

                span_ctx = mlflow_mod.start_span(
                    name=f"{self.server_name}.{tool_name}",
                    span_type=SpanType.TOOL,
                )
                span = span_ctx.__enter__()
                span.set_inputs(redact_payload(raw_args))
                span.set_attributes(
                    {
                        "mcp.server": self.server_name,
                        "mcp.tool": tool_name,
                    }
                )
                model_id = get_or_create_gateway_logged_model(self._settings)
                update_fn = getattr(mlflow_mod, "update_current_trace", None)
                if callable(update_fn):
                    update_kwargs: dict[str, Any] = {
                        "user": caller_client_id_var.get() or "anonymous",
                        "tags": {
                            "mcp.server": self.server_name,
                            "mcp.tool": tool_name,
                            "mcp.profile": caller_profile_var.get() or "direct",
                        },
                    }
                    if session_id := caller_session_id_var.get():
                        update_kwargs["session_id"] = session_id
                    if model_id:
                        update_kwargs["model_id"] = model_id
                    update_fn(**update_kwargs)
            except Exception as exc:
                self._trip_circuit("span_start", exc)
                span_ctx = None
                span = None

            try:
                result = await call_next(context)
            except Exception as tool_exc:
                status = "error"
                if span is not None and span_ctx is not None:
                    try:
                        err_msg = str(tool_exc)
                        is_refusal = any(
                            marker in err_msg.lower() for marker in _POLICY_REFUSAL_MARKERS
                        )
                        span.set_attribute("error.type", type(tool_exc).__name__)
                        span.set_attribute("error.message", err_msg[:500])
                        update_fn = getattr(mlflow_mod, "update_current_trace", None)
                        if callable(update_fn):
                            refusal_flag = "true" if is_refusal else "false"
                            update_fn(tags={"mcp.policy_refusal": refusal_flag})
                        span_ctx.__exit__(type(tool_exc), tool_exc, tool_exc.__traceback__)
                    except Exception as ml_exc:
                        self._trip_circuit("span_end_error", ml_exc)
                raise

            if span is not None and span_ctx is not None:
                try:
                    preview = [
                        getattr(block, "text", str(block))
                        for block in (getattr(result, "content", None) or [])
                    ]
                    span.set_outputs(redact_payload({"content": preview}))
                    update_fn = getattr(mlflow_mod, "update_current_trace", None)
                    if callable(update_fn):
                        update_fn(tags={"mcp.policy_refusal": "false"})
                    span_ctx.__exit__(None, None, None)
                except Exception as ml_exc:
                    self._trip_circuit("span_end", ml_exc)

            return result
        except Exception:
            status = "error"
            raise
        finally:
            duration = max(0.0, self._clock() - start)
            mcp_active_requests.labels(server=self.server_name).dec()
            mcp_tool_calls_total.labels(
                server=self.server_name, tool=tool_name, status=status
            ).inc()
            mcp_tool_duration_seconds.labels(
                server=self.server_name, tool=tool_name
            ).observe(duration)
