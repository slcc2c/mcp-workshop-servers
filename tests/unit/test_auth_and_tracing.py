"""Unit tests for gateway auth, OBO UC token propagation, and fail-open MLflow tracing."""

from __future__ import annotations

import sys
import types

import httpx
import pytest
from fastmcp import Client, FastMCP

from mcp_stack.core.auth import (
    UI_SESSION_COOKIE,
    GatewayAuthMiddleware,
    LoginNonceStore,
    caller_auth_method_var,
    caller_profile_var,
    caller_session_id_var,
    caller_uc_token_var,
    sign_ui_session,
    verify_ui_session,
)
from mcp_stack.core.config import ClientPolicy
from mcp_stack.core.metrics import mcp_mlflow_trace_failures_total, mcp_tool_calls_total
from mcp_stack.core.tracing import (
    _LOGGED_MODEL_CACHE,
    MLflowTracingMiddleware,
    get_or_create_gateway_logged_model,
    redact_payload,
)

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
        sess = caller_session_id_var.get() or ""
        prof = caller_profile_var.get() or ""
        body = f'{{"ok":true,"uc":"{token or ""}","sess":"{sess}","prof":"{prof}"}}'.encode()
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
        # Allowed server + OBO X-UC-Token + Mcp-Session-Id -> 200
        r1 = await client.post(
            "/servers/memory/mcp",
            headers={
                "Authorization": "Bearer tok-limited",
                "X-UC-Token": "uc-obo-123",
                "Mcp-Session-Id": "sess-xyz",
            },
        )
        assert r1.status_code == 200
        assert r1.json()["uc"] == "uc-obo-123"
        assert r1.json()["sess"] == "sess-xyz"
        assert r1.json()["prof"] == "server:memory"
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


def test_logged_model_resolution_is_idempotent_and_fail_open(
    make_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _LOGGED_MODEL_CACHE.clear()
    settings = make_settings()
    settings.mlflow.experiment_name = "logged-model-unit"

    created_calls: list[dict] = []
    fake_mlflow = types.ModuleType("mlflow")
    fake_mlflow.set_tracking_uri = lambda _u: None  # type: ignore[attr-defined]
    fake_mlflow.set_experiment = lambda _n: types.SimpleNamespace(experiment_id="52")  # type: ignore[attr-defined]

    class FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def search_logged_models(self, **_kwargs):
            return []

    fake_mlflow.MlflowClient = FakeClient  # type: ignore[attr-defined]

    def fake_create_external_model(**kwargs):
        created_calls.append(kwargs)
        return types.SimpleNamespace(model_id="m-unit-001")

    fake_mlflow.create_external_model = fake_create_external_model  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    first = get_or_create_gateway_logged_model(settings)
    second = get_or_create_gateway_logged_model(settings)
    assert first == "m-unit-001"
    assert second == "m-unit-001"
    assert len(created_calls) == 1
    assert not any(ch in created_calls[0]["name"] for ch in "/:.%'\"")
    _LOGGED_MODEL_CACHE.clear()


async def test_ui_session_cookie_signing_nonce_csrf_and_route_isolation(make_settings) -> None:
    tok = "tok_ui_cookie_owner"
    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }

    signed = sign_ui_session("codex", settings, ttl_s=120, now=1000.0)
    assert verify_ui_session(signed, settings, now=1050.0) == "codex"
    assert verify_ui_session(signed, settings, now=1200.0) is None
    assert verify_ui_session(signed + "tamper", settings, now=1050.0) is None

    now = 10.0
    nonces = LoginNonceStore(ttl_s=60.0, clock=lambda: now)
    nonce = nonces.issue("codex")
    assert nonces.consume(nonce) == "codex"
    assert nonces.consume(nonce) is None

    nonce_exp = nonces.issue("codex")
    now += 61.0
    assert nonces.consume(nonce_exp) is None

    from fastapi import FastAPI

    api = FastAPI()

    @api.get("/api/v1/ping")
    async def ping():
        return {"ok": True, "method": caller_auth_method_var.get()}

    @api.post("/api/v1/mutate")
    async def mutate():
        return {"mutated": True, "method": caller_auth_method_var.get()}

    @api.post("/mcp")
    async def mcp_ep():
        return {"mcp": True}

    api.add_middleware(GatewayAuthMiddleware, settings=settings)

    cookie_val = sign_ui_session("codex", settings)
    cookie_hdr = {"Cookie": f"{UI_SESSION_COOKIE}={cookie_val}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://testserver"
    ) as client:
        # Cookie grants GET on /api/v1/*
        r_get = await client.get("/api/v1/ping", headers=cookie_hdr)
        assert r_get.status_code == 200
        assert r_get.json()["method"] == "cookie"

        # Cookie-authenticated POST without X-Requested-With -> 403 CSRF_REQUIRED
        r_csrf = await client.post("/api/v1/mutate", headers=cookie_hdr)
        assert r_csrf.status_code == 403
        assert r_csrf.json()["error"]["code"] == "CSRF_REQUIRED"

        # Cookie + X-Requested-With -> 200
        r_post = await client.post(
            "/api/v1/mutate",
            headers={**cookie_hdr, "X-Requested-With": "mcp-ui"},
        )
        assert r_post.status_code == 200

        # Bearer works on POST without X-Requested-With
        r_bearer = await client.post(
            "/api/v1/mutate", headers={"Authorization": f"Bearer {tok}"}
        )
        assert r_bearer.status_code == 200
        assert r_bearer.json()["method"] == "bearer"

        # Cookies MUST be rejected on /mcp endpoints
        r_mcp = await client.post(
            "/mcp",
            headers={**cookie_hdr, "X-Requested-With": "mcp-ui"},
        )
        assert r_mcp.status_code == 401
