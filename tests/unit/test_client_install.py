"""Unit tests for live client config installer backups and non-destructive merges."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from mcp_stack.client_configs import audit_client_configs, install_client_configs
from mcp_stack.core.config import ClientPolicy, UpstreamServerConfig


def test_install_client_configs_preserves_existing_entries_and_creates_backups(
    make_settings, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    codex_path = home / ".codex/config.toml"
    codex_path.parent.mkdir(parents=True, exist_ok=True)
    codex_path.write_text(
        'model = "gpt-5"\n\n[mcp_servers.music-brain]\nurl = "http://localhost:7777/mcp"\n',
        encoding="utf-8",
    )

    claude_path = home / ".claude.json"
    claude_path.write_text(
        json.dumps({"mcpServers": {"music-brain": {"url": "http://localhost:7777"}}}),
        encoding="utf-8",
    )

    desk_path = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desk_path.parent.mkdir(parents=True, exist_ok=True)
    desk_path.write_text(
        json.dumps({"mcpServers": {"printer": {"command": "uv"}}}),
        encoding="utf-8",
    )

    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        "super-secret-live-token": ClientPolicy(client_id="codex", client_name="Codex CLI")
    }

    res = install_client_configs(
        settings,
        tmp_path,
        ["codex", "claude-code", "claude-desktop"],
        home_dir=home,
    )

    assert res["results"]["codex"]["backup"]
    assert Path(res["results"]["codex"]["backup"]).exists()
    parsed_toml = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert "music-brain" in parsed_toml["mcp_servers"]
    assert parsed_toml["mcp_servers"]["mcp_workshop_gateway"]["bearer_token_env_var"] == (
        "MCP_CODEX_AUTH_TOKEN"
    )

    cc_doc = json.loads(claude_path.read_text(encoding="utf-8"))
    assert "music-brain" in cc_doc["mcpServers"]
    assert cc_doc["mcpServers"]["mcp-workshop-gateway"]["headers"] == {
        "Authorization": "Bearer ${MCP_CLAUDE_AUTH_TOKEN}"
    }

    cd_doc = json.loads(desk_path.read_text(encoding="utf-8"))
    assert "printer" in cd_doc["mcpServers"]
    assert "mcp-postgresql" in cd_doc["mcpServers"]

    for p in (codex_path, claude_path, desk_path):
        assert "super-secret-live-token" not in p.read_text(encoding="utf-8")


def test_audit_and_prune_duplicates_plus_omnigent_install(
    make_settings, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    codex_path = home / ".codex/config.toml"
    codex_path.parent.mkdir(parents=True, exist_ok=True)
    codex_path.write_text(
        "\n".join(
            [
                "[mcp_servers.computer-use]",
                'command = "/Applications/SkyComputerUseClient"',
                "",
                "[mcp_servers.mlflow]",
                'url = "http://localhost:9012/mcp"',
                "",
                "[mcp_servers.printer]",
                'url = "https://mac-studio.example.ts.net:8445/mcp"',
                'default_tools_approval_mode = "approve"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    # Empty 0-byte antigravity config must not crash audit/install
    ag_path = home / ".gemini/config/mcp_config.json"
    ag_path.parent.mkdir(parents=True, exist_ok=True)
    ag_path.write_text("", encoding="utf-8")

    # Custom service in existing omnigent registry
    omni_path = home / ".omnigent/mcp_registry.yaml"
    omni_path.parent.mkdir(parents=True, exist_ok=True)
    omni_path.write_text(
        yaml.safe_dump(
            {
                "services": [
                    {
                        "id": "custom-external",
                        "title": "Custom",
                        "url": "https://custom.example.com/mcp",
                        "auth": "none",
                        "tools": ["ping"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    settings = make_settings()
    settings.gateway.upstream_servers = {
        "printer": UpstreamServerConfig(
            transport="http",
            url="https://mac-studio.example.ts.net:8445/mcp",
        )
    }

    audit = audit_client_configs(settings, home_dir=home, repos_root=tmp_path / "repos")
    assert audit["summary"]["shadowedClientEntries"] == 2
    ag_entry = next(c for c in audit["clients"] if c["client"] == "antigravity")
    assert ag_entry["error"] is None

    res = install_client_configs(
        settings,
        tmp_path,
        ["codex", "omnigent", "antigravity"],
        profile="core",
        home_dir=home,
        prune_duplicates=True,
        tool_catalog={
            "mlflow-upstream": ["search_traces"],
            "printer": ["today", "print", "print_note", "print_picture", "reprint_ticket"],
            "profile:core": ["memory_search"],
        },
    )

    parsed_toml = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert "computer-use" in parsed_toml["mcp_servers"]
    assert "mlflow" not in parsed_toml["mcp_servers"]
    assert parsed_toml["mcp_servers"]["printer"]["url"] == "http://127.0.0.1:8090/servers/printer/mcp"
    assert parsed_toml["mcp_servers"]["printer"]["default_tools_approval_mode"] == "approve"
    assert "mlflow" in res["results"]["codex"]["pruned"]
    assert "printer" in res["results"]["codex"]["retargeted"]

    omni_loaded = yaml.safe_load(omni_path.read_text(encoding="utf-8"))
    omni_ids = [s["id"] for s in omni_loaded["services"]]
    assert "printer" in omni_ids
    assert "custom-external" in omni_ids
