"""Unit tests for MCP client config generation and env-var Bearer headers."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_stack.client_configs import generate_client_configs
from mcp_stack.core.config import ClientPolicy


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
