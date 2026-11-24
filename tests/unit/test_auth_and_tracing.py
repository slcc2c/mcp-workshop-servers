"""Unit tests for gateway auth, OBO UC token propagation, and fail-open MLflow tracing."""

from __future__ import annotations

import sys
import types

import httpx
import pytest
from fastmcp import Client, FastMCP

from mcp_stack.core.auth import GatewayAuthMiddleware, caller_uc_token_var
from mcp_stack.core.config import ClientPolicy
from mcp_stack.core.metrics import mcp_mlflow_trace_failures_total, mcp_tool_calls_total
from mcp_stack.core.tracing import MLflowTracingMiddleware, redact_payload

pytestmark = pytest.mark.unit


def test_redact_payload_masks_sensitive_keys() -> None:
    payload = {
        "query": "hello",
        "github_token": "ghp_super_secret",
        "nested": {"Authorization": "Bearer abc", "password": "pw", "safe": 42},
    }
    redacted = redact_payload(payload)
    assert redacted["query"] == "hello"
    assert redacted["github_token"] == "<redacted>"
    assert redacted["nested"]["Authorization"] == "<redacted>"
    assert redacted["nested"]["password"] == "<redacted>"
    assert redacted["nested"]["safe"] == 42


async def test_gateway_auth_middleware_enforces_tokens_allowlist_and_rate_limit(
    make_settings,
) -> None:
    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        "tok-limited": ClientPolicy(
            client_id="limited",
            client_name="Limited",
            allowed_servers=["memory"],
            rate_limit_max=2,
            rate_limit_window_s=60,
        )
    }

    async def inner_app(scope, receive, send) -> None:
        token = caller_uc_token_var.get()
        body = f'{{"ok":true,"uc":"{token or ""}"}}'.encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    now = 10.0
    wrapped = GatewayAuthMiddleware(inner_app, settings, clock=lambda: now)
    transport = httpx.ASGITransport(app=wrapped)  # type: ignore[arg-type]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Health is exempt
        assert (await client.get("/health")).status_code == 200
        # Missing auth -> 401
        assert (await client.get("/api/v1/servers")).status_code == 401
        # Invalid auth -> 401
        assert (
            await client.get("/api/v1/servers", headers={"Authorization": "Bearer bad"})
        ).status_code == 401
        # Disallowed server -> 403
        assert (
            await client.post(
                "/servers/github/mcp",
                headers={"Authorization": "Bearer tok-limited"},
            )
        ).status_code == 403
        # Allowed server + OBO X-UC-Token -> 200
        r1 = await client.post(
            "/servers/memory/mcp",
            headers={"Authorization": "Bearer tok-limited", "X-UC-Token": "uc-obo-123"},
        )
        assert r1.status_code == 200
        assert r1.json()["uc"] == "uc-obo-123"
        # Second allowed call -> 200
        assert (
            await client.post(
                "/servers/memory/mcp",
                headers={"Authorization": "Bearer tok-limited"},
            )
        ).status_code == 200
        # Third call trips rate limit -> 429
        assert (
            await client.post(
                "/servers/memory/mcp",
                headers={"Authorization": "Bearer tok-limited"},
            )
        ).status_code == 429


async def test_mlflow_tracing_middleware_fail_open_circuit_breaker(
    make_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings()
    settings.mlflow.tracing_enabled = True
    settings.mlflow.circuit_breaker_cooldown_s = 60.0

    calls = 0
    fake_mlflow = types.ModuleType("mlflow")

    def boom_set_uri(_uri: str) -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("MLflow down")

    fake_mlflow.set_tracking_uri = boom_set_uri  # type: ignore[attr-defined]
    fake_mlflow.set_experiment = lambda _name: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    now = 100.0
    mw = MLflowTracingMiddleware(settings, "test_srv", clock=lambda: now)
    mcp = FastMCP("test_srv")
    mcp.add_middleware(mw)

    @mcp.tool()
    def echo(text: str) -> str:
        return f"echo:{text}"

    before_fail = mcp_mlflow_trace_failures_total.labels(reason="span_start")._value.get()
    before_calls = mcp_tool_calls_total.labels(
        server="test_srv", tool="echo", status="success"
    )._value.get()

    async with Client(mcp) as client:
        res1 = await client.call_tool("echo", {"text": "one"})
        res2 = await client.call_tool("echo", {"text": "two"})

    assert "echo:one" in str(res1)
    assert "echo:two" in str(res2)
    # Circuit breaker prevented second MLflow attempt within 60s cooldown
    assert calls == 1
    assert (
        mcp_mlflow_trace_failures_total.labels(reason="span_start")._value.get()
        == before_fail + 1
    )
    assert (
        mcp_tool_calls_total.labels(server="test_srv", tool="echo", status="success")._value.get()
        == before_calls + 2
    )
