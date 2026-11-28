"""Unit tests for v2.4.0 presets store, gateway://presets resource, trace linking & prompts."""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import SecretStr

from mcp_stack.core.config import ClientPolicy
from mcp_stack.core.secrets import CommandResult, SecretResolver
from mcp_stack.core.tracing import last_trace_id_var
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.gateway.presets import PresetStore
from mcp_stack.gateway.upstreams import probe_upstream_proxy, resolve_secret_mapping

pytestmark = pytest.mark.unit


def _asgi_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        kwargs["follow_redirects"] = False
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


def test_preset_store_crud_and_pin_sort(tmp_path: Path) -> None:
    presets_file = tmp_path / "nested" / "presets.json"
    store = PresetStore(presets_file)
    assert store.list_presets() == []

    p1 = store.create_preset(
        name="Alpha",
        server="memory",
        tool="memory_search",
        arguments={"query": "notes"},
        pinned=False,
    )
    p2 = store.create_preset(
        name="Pinned Check",
        server="printer_hub",
        tool="today",
        arguments={"copy": 1},
        description="Daily printout",
        pinned=True,
    )
    listed = store.list_presets()
    assert [p.id for p in listed] == [p2.id, p1.id]
    assert listed[0].server == "printer-hub"
    assert (presets_file.stat().st_mode & 0o777) == 0o600

    updated = store.update_preset(p1.id, {"pinned": True, "name": "Alpha Pinned"})
    assert updated is not None
    assert updated.name == "Alpha Pinned"
    assert updated.pinned is True

    assert store.delete_preset(p2.id) is True
    assert store.delete_preset("does-not-exist") is False
    assert [p.id for p in store.list_presets()] == [p1.id]


async def test_presets_rest_and_mcp_resource_plus_trace_id(
    make_settings, tmp_path: Path, monkeypatch
) -> None:
    tok = "tok_presets_admin_123"
    settings = make_settings()
    settings.gateway.enabled_servers = ["memory", "filesystem"]
    settings.gateway.enable_photos_on_macos = False
    settings.gateway.enable_xcode_on_macos = False
    settings.gateway.auth_enabled = True
    settings.gateway.presets_path = tmp_path / "presets.json"
    settings.gateway.mlflow_ui_url = "https://mlflow.example.test"
    settings.gateway.clients = {
        tok: ClientPolicy(client_id="codex", client_name="Codex", allowed_servers=["*"])
    }
    settings.mlflow.proxy_upstream_mcp = False
    settings.mlflow.allow_mutations = True
    settings.unity_catalog.dynamic_function_tools = False

    # Fake MLflow module to test span traceId, trace detail attrs/timestamps, & alias deletion
    deleted_aliases: list[tuple[str, str]] = []

    class FakeSpan:
        span_id = "sp-root"
        parent_id = None
        name = "memory.memory_search"
        span_type = "TOOL"
        status = "OK"
        request_id = "tr-captured-999"
        trace_id = "tr-captured-999"
        start_time_ns = 1_000_000_000
        end_time_ns = 1_045_000_000
        attributes = {"mcp.server": "memory", "mcp.tool": "memory_search", "api_key": "secret123"}
        inputs = {"query": "hello"}
        outputs = {"items": []}
        events = []

        def set_inputs(self, _v):
            return None

        def set_outputs(self, _v):
            return None

        def set_attributes(self, _v):
            return None

        def set_attribute(self, _k, _v):
            return None

    class FakeSpanCtx:
        def __enter__(self):
            return FakeSpan()

        def __exit__(self, *_args):
            return False

    class FakeClient:
        def __init__(self, tracking_uri: str = ""):
            self.tracking_uri = tracking_uri

        def get_trace(self, trace_id: str):
            sp = FakeSpan()
            info = types.SimpleNamespace(
                trace_id=trace_id,
                state="OK",
                execution_duration=45,
                timestamp_ms=1000,
                tags={"mcp.server": "memory", "mcp.tool": "memory_search"},
                trace_metadata={"mlflow.trace.user": "codex"},
                assessments=[],
            )
            return types.SimpleNamespace(info=info, data=types.SimpleNamespace(spans=[sp]))

        def search_logged_models(self, **_kw):
            return []

    fake_mlflow = types.ModuleType("mlflow")
    fake_mlflow.set_tracking_uri = lambda uri: None
    fake_mlflow.set_experiment = lambda name: types.SimpleNamespace(experiment_id="1")
    fake_mlflow.start_span = lambda **kw: FakeSpanCtx()
    fake_mlflow.update_current_trace = lambda **kw: None
    fake_mlflow.MlflowClient = FakeClient
    fake_mlflow.create_external_model = lambda **kw: types.SimpleNamespace(model_id="m-1")
    fake_mlflow.genai = types.SimpleNamespace(
        delete_prompt_alias=lambda name, alias: deleted_aliases.append((name, alias))
    )
    fake_entities = types.ModuleType("mlflow.entities")
    fake_entities.SpanType = types.SimpleNamespace(TOOL="TOOL")
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(sys.modules, "mlflow.genai", fake_mlflow.genai)
    monkeypatch.setitem(sys.modules, "mlflow.entities", fake_entities)

    # Ensure tracing is enabled inside gateway call_tool test
    settings.mlflow.tracing_enabled = True
    app = build_gateway_app(settings)
    headers = {"Authorization": f"Bearer {tok}"}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as cli:
            # Unauthenticated presets access rejected, while /favicon.ico is public
            unauth = await cli.get("/api/v1/presets")
            assert unauth.status_code == 401
            fav = await cli.get("/favicon.ico")
            assert fav.status_code == 200
            assert "image/svg+xml" in fav.headers["content-type"]

            health = await cli.get("/health")
            assert health.status_code == 200
            assert health.json()["mlflowUiUrl"] == "https://mlflow.example.test"

            # Create, list, update, delete preset
            created = await cli.post(
                "/api/v1/presets",
                headers=headers,
                json={
                    "name": "Memory lookup",
                    "server": "memory",
                    "tool": "memory_search",
                    "arguments": {"query": "test"},
                    "pinned": True,
                },
            )
            assert created.status_code == 200
            preset_id = created.json()["preset"]["id"]

            listed = await cli.get("/api/v1/presets", headers=headers)
            assert len(listed.json()["presets"]) == 1

            # Verify /api/v1/actions/call-tool captures last_trace_id_var
            res = await cli.post(
                "/api/v1/actions/call-tool",
                headers=headers,
                json={"server": "memory", "tool": "memory_search", "arguments": {"query": "hi"}},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["ok"] is True
            assert body["traceId"] == "tr-captured-999"

            # Verify trace detail returns startTimeMs, endTimeMs, redacted attributes, server & tool
            td = await cli.get("/api/v1/traces/tr-captured-999", headers=headers)
            assert td.status_code == 200
            detail = td.json()
            assert detail["server"] == "memory"
            assert detail["tool"] == "memory_search"
            assert detail["spans"][0]["startTimeMs"] == 1000.0
            assert detail["spans"][0]["endTimeMs"] == 1045.0
            assert detail["spans"][0]["attributes"]["api_key"] == "<redacted>"

            # Verify DELETE alias calls mlflow.genai.delete_prompt_alias
            del_alias = await cli.delete(
                "/api/v1/mlflow/prompts/ai-assist/alias/@staging", headers=headers
            )
            assert del_alias.status_code == 200
            assert deleted_aliases == [("ai-assist", "staging")]

        # Verify gateway://presets MCP Resource exposes the persisted preset
        factory = _asgi_factory(app)
        async with Client(
            StreamableHttpTransport(
                "http://testserver/servers/gateway/mcp",
                headers=headers,
                httpx_client_factory=factory,
            )
        ) as gw_cli:
            resources = {str(r.uri) for r in await gw_cli.list_resources()}
            assert "gateway://presets" in resources
            res_blocks = await gw_cli.read_resource("gateway://presets")
            payload = json.loads(getattr(res_blocks[0], "text", "{}"))
            assert payload["presets"][0]["id"] == preset_id

    # Verify MLflowTracingMiddleware ContextVar does not leak outside call
    assert last_trace_id_var.get() is None


def test_resolve_secret_mapping_prefixed_onepassword_with_spaces(
    make_settings, monkeypatch
) -> None:
    from mcp_stack.gateway.upstreams import resolve_secret_mapping_with_reasons

    settings = make_settings()
    settings.secrets.onepassword_enabled = True
    settings.secrets.onepassword_allowed_vaults = ["Server-Configurations"]

    ref = "Bearer op://Server-Configurations/Linear API Key/credential"

    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    blocked_calls: list[list[str]] = []

    def _blocked_runner(args: list[str]) -> CommandResult:
        blocked_calls.append(args)
        return CommandResult(returncode=0, stdout="should-not-run\n", stderr="")

    blocked_resolver = SecretResolver(settings.secrets, runner=_blocked_runner)
    resolved_blocked, missing_blocked, reasons_blocked = resolve_secret_mapping_with_reasons(
        {"Authorization": SecretStr(ref)},
        blocked_resolver,
    )
    assert resolved_blocked == {}
    assert missing_blocked == ["op://Server-Configurations/Linear API Key/credential"]
    assert reasons_blocked and reasons_blocked[0][0] == "service_account_missing"
    assert blocked_calls == []

    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "ops_test_token")

    def _ok_runner(args: list[str]) -> CommandResult:
        assert args == [
            "op",
            "read",
            "op://Server-Configurations/Linear API Key/credential",
        ]
        return CommandResult(returncode=0, stdout="lin_demo_token_abc\n", stderr="")

    ok_resolver = SecretResolver(settings.secrets, runner=_ok_runner)
    resolved, missing = resolve_secret_mapping(
        {"Authorization": SecretStr(ref)},
        ok_resolver,
    )
    assert resolved == {"Authorization": "Bearer lin_demo_token_abc"}
    assert missing == []

    def _missing_runner(_args: list[str]) -> CommandResult:
        return CommandResult(returncode=1, stdout="", stderr="ERROR: item not found")

    miss_resolver = SecretResolver(settings.secrets, runner=_missing_runner)
    resolved2, missing2 = resolve_secret_mapping(
        {"Authorization": SecretStr(ref)},
        miss_resolver,
    )
    assert resolved2 == {}
    assert len(missing2) == 1
    assert "op://Server-Configurations/Linear API Key/credential" in missing2[0]

    def _timeout_runner(_args: list[str]) -> CommandResult:
        raise subprocess.TimeoutExpired(cmd=["op", "read"], timeout=10)

    to_resolver = SecretResolver(settings.secrets, runner=_timeout_runner)
    resolved3, missing3 = resolve_secret_mapping(
        {"Authorization": SecretStr(ref)},
        to_resolver,
    )
    assert resolved3 == {}
    assert len(missing3) == 1
    assert "op://Server-Configurations/Linear API Key/credential" in missing3[0]


async def test_probe_upstream_proxy_includes_sample_tools() -> None:
    class _FakeProxy:
        async def list_tools(self):
            return [types.SimpleNamespace(name=f"tool_{i}") for i in range(7)]

    res = await probe_upstream_proxy(_FakeProxy(), timeout_s=1.0)
    assert res["reachable"] is True
    assert res["toolCount"] == 7
    assert res["sampleTools"] == ["tool_0", "tool_1", "tool_2", "tool_3", "tool_4"]
