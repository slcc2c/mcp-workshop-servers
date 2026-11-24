"""Dedicated Prometheus metrics registry for MCP gateway and servers."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total",
    "Total number of MCP tool calls",
    labelnames=["server", "tool", "status"],
    registry=REGISTRY,
)

mcp_tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "Duration of MCP tool executions in seconds",
    labelnames=["server", "tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

mcp_active_requests = Gauge(
    "mcp_active_requests",
    "Currently active MCP tool calls",
    labelnames=["server"],
    registry=REGISTRY,
)

mcp_mlflow_trace_failures_total = Counter(
    "mcp_mlflow_trace_failures_total",
    "Number of fail-open MLflow tracing errors",
    labelnames=["reason"],
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    """Return Prometheus exposition payload and MIME content type."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
