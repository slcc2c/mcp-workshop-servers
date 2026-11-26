"""Unit tests for MCP client config generation and env-var Bearer headers."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from mcp_stack.client_configs import (
    build_omnigent_registry_payload,
    check_omnigent_cel_compatibility,
    generate_client_configs,
    validate_omnigent_registry_services,
)
from mcp_stack.core.config import ClientPolicy, UpstreamServerConfig


def test_client_configs_omit_auth_headers_when_loopback_unauthenticated(
    make_settings, tmp_path: Path
) -> None:
    settings = make_settings()
    settings.gateway.host = "127.0.0.1"
    settings.gateway.auth_enabled = False

    rendered = generate_client_configs(settings, tmp_path)
    claude_cfg = json.loads(rendered["claude-code"])
    cursor_cfg = json.loads(rendered["cursor"])

    assert "headers" not in claude_cfg["mcpServers"]["mcp-workshop-gateway"]
    assert "headers" not in cursor_cfg["mcpServers"]["mcp-workshop-gateway"]
    assert "bearer_token_env_var" not in rendered["codex"]


def test_client_configs_use_env_var_bearer_tokens_never_raw_secrets(
    make_settings, tmp_path: Path
) -> None:
    settings = make_settings()
    settings.gateway.host = "127.0.0.1"
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        "super-secret-raw-token": ClientPolicy(
            client_id="claude",
            client_name="Claude Desktop / Code",
        )
    }

    rendered = generate_client_configs(settings, tmp_path)
    claude_cfg = json.loads(rendered["claude-code"])
    cursor_cfg = json.loads(rendered["cursor"])

    assert claude_cfg["mcpServers"]["mcp-workshop-gateway"]["headers"] == {
        "Authorization": "Bearer ${MCP_CLAUDE_AUTH_TOKEN}"
    }
    assert cursor_cfg["mcpServers"]["mcp-workshop-gateway"]["headers"] == {
        "Authorization": "Bearer ${env:MCP_CURSOR_AUTH_TOKEN}"
    }
    assert 'bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"' in rendered["codex"]

    for payload in rendered.values():
        assert "super-secret-raw-token" not in payload


def test_build_omnigent_registry_payload_hybrid_and_cel_safe(make_settings) -> None:
    settings = make_settings()
    settings.gateway.host = "127.0.0.1"
    settings.gateway.port = 8090
    settings.gateway.auth_enabled = True
    settings.gateway.upstream_servers = {
        "printer": UpstreamServerConfig(
            transport="http",
            url="https://mac-studio.example.ts.net:8445/mcp",
            description="Receipt printer",
        ),
        "broken-empty": UpstreamServerConfig(
            transport="http",
            url="https://empty.example.ts.net/mcp",
        ),
    }

    catalog = {
        "mlflow-upstream": ["search_traces", "get_trace"],
        "printer": ["today", "print", "print_note", "print_picture", "reprint_ticket"],
        "profile:core": ["memory_search", "read_file"],
        "profile:discover": ["gateway_search_tools"],
    }
    rendered, managed_ids, warnings = build_omnigent_registry_payload(
        settings, tool_catalog=catalog
    )
    parsed = yaml.safe_load(rendered)
    services = parsed["services"]
    by_id = {s["id"]: s for s in services}

    assert "printer" in managed_ids
    assert "mlflow" in managed_ids
    assert "mcp-core" in managed_ids
    assert "broken-empty" not in by_id
    assert any("broken-empty" in w for w in warnings)

    assert by_id["printer"]["url"] == "http://127.0.0.1:8090/servers/printer/mcp"
    assert by_id["printer"]["auth"] == "bearer"
    assert by_id["printer"]["allow_http"] is True
    assert by_id["mcp-core"]["url"] == "http://127.0.0.1:8090/profiles/core/mcp"
    assert validate_omnigent_registry_services(services) == []
    assert check_omnigent_cel_compatibility(services) == []
