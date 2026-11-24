"""Fail-open MLflow 3.x tracing + Prometheus instrumentation middleware for FastMCP."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

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
_MAX_STR_LEN = 4000


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
            try:
                mlflow = self._configure_mlflow()
                from mlflow.entities import SpanType

                span_ctx = mlflow.start_span(
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
                        span.set_attribute("error.type", type(tool_exc).__name__)
                        span.set_attribute("error.message", str(tool_exc)[:500])
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
