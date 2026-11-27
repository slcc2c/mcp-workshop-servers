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
    assert "mcp-workshop-gateway" in cd_doc["mcpServers"]
    assert "mcp-postgresql" not in cd_doc["mcpServers"]

    for p in (codex_path, claude_path, desk_path):
        assert "super-secret-live-token" not in p.read_text(encoding="utf-8")


def test_claude_desktop_install_prunes_legacy_stdio_entries(
    make_settings, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    desk_path = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desk_path.parent.mkdir(parents=True, exist_ok=True)
    desk_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "printer": {"command": "/Users/spencer/.local/bin/printer-mcp"},
                    "music-brain": {"command": "/Users/spencer/.local/bin/music-brain"},
                    "mcp-postgresql": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            "/Users/spencer/repos/mcp-server",
                            "run",
                            "mcp-stack",
                            "serve",
                            "postgresql",
                            "--transport",
                            "stdio",
                        ],
                    },
                    "mcp-docker": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            "/Users/spencer/repos/mcp-server",
                            "run",
                            "mcp-stack",
                            "serve",
                            "docker",
                            "--transport",
                            "stdio",
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    settings = make_settings()
    audit = audit_client_configs(settings, home_dir=home, repos_root=tmp_path / "repos")
    desktop_report = next(c for c in audit["clients"] if c["client"] == "claude-desktop")
    shadowed_names = {s["name"] for s in desktop_report["servers"] if s["shadowed"]}
    assert shadowed_names == {"mcp-docker", "mcp-postgresql"}

    res = install_client_configs(
        settings,
        tmp_path,
        ["claude-desktop"],
        profile="core",
        home_dir=home,
        prune_duplicates=True,
    )
    assert set(res["results"]["claude-desktop"]["pruned"]) == {
        "mcp-docker",
        "mcp-postgresql",
    }
    updated = json.loads(desk_path.read_text(encoding="utf-8"))
    assert set(updated["mcpServers"]) == {
        "printer",
        "music-brain",
        "mcp-workshop-gateway",
    }


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

    # Project-scoped JSONL memory override in repo is NOT flagged as shadowed
    repo_mcp = tmp_path / "repos/Music-brain/.mcp.json"
    repo_mcp.parent.mkdir(parents=True, exist_ok=True)
    repo_mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "memory": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-memory"],
                        "env": {"MEMORY_FILE_PATH": "/tmp/music-brain.jsonl"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    audit_post = audit_client_configs(settings, home_dir=home, repos_root=tmp_path / "repos")
    assert audit_post["summary"]["repoShadows"] == 0


def test_omnigent_install_skips_bearer_when_local_host_plist_lacks_cipher(
    make_settings, tmp_path: Path
) -> None:
    import plistlib

    home = tmp_path / "home"
    plist_path = home / "Library/LaunchAgents/ai.omnigent.host.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(
        plistlib.dumps({"Label": "ai.omnigent.host", "EnvironmentVariables": {"PATH": "/usr/bin"}})
    )

    omni_path = home / ".omnigent/mcp_registry.yaml"
    omni_path.parent.mkdir(parents=True, exist_ok=True)
    existing_none_yaml = yaml.safe_dump(
        {
            "services": [
                {
                    "id": "mlflow",
                    "title": "MLflow",
                    "url": "http://127.0.0.1:9012/mcp",
                    "auth": "none",
                    "allow_http": True,
                    "tools": ["search_traces"],
                }
            ]
        },
        sort_keys=False,
    )
    omni_path.write_text(existing_none_yaml, encoding="utf-8")

    settings = make_settings()
    settings.gateway.auth_enabled = True
    res = install_client_configs(
        settings,
        tmp_path,
        ["omnigent"],
        home_dir=home,
        tool_catalog={"mlflow-upstream": ["search_traces"]},
    )
    omni_res = res["results"]["omnigent"]
    assert omni_res["status"] == "skipped_missing_cipher"
    assert any("KMS_KEY_ID" in w for w in omni_res["warnings"])
    assert omni_path.read_text(encoding="utf-8") == existing_none_yaml


def test_antigravity_and_claude_desktop_pruning_retargeting_and_extras(
    make_settings, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    ag_path = home / ".gemini/config/mcp_config.json"
    ag_path.parent.mkdir(parents=True, exist_ok=True)
    ag_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "mcp-workshop-gateway": {
                        "url": "http://127.0.0.1:8090/profiles/core/mcp",
                        "headers": {"Authorization": "Bearer ${MCP_ANTIGRAVITY_AUTH_TOKEN}"},
                    },
                    "unifi": {"command": "/Users/spencer/repos/unifi/scripts/mcp-launch.sh"},
                }
            }
        ),
        encoding="utf-8",
    )

    music_brain_cmd = (
        "/Users/spencer/.local/share/music-brain-mcp/bin/music-brain-relay"
    )
    migrated_path = home / ".gemini/config/plugins/migrated-settings/mcp_config.json"
    migrated_path.parent.mkdir(parents=True, exist_ok=True)
    migrated_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "music-brain": {
                        "command": music_brain_cmd,
                        "args": [],
                    },
                    "mlflow": {"url": "http://localhost:9012/mcp"},
                    "printer": {"url": "https://mac-studio.example.ts.net:8445/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )

    desk_path = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desk_path.parent.mkdir(parents=True, exist_ok=True)
    desk_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "printer": {
                        "command": "/Users/spencer/repos/printer/.venv/bin/python",
                        "args": ["/Users/spencer/repos/printer/scripts/printer_mcp.py"],
                    },
                    "music-brain": {
                        "command": music_brain_cmd,
                        "args": [],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    settings = make_settings()
    settings.gateway.auth_enabled = True
    settings.gateway.clients = {
        "tok-ag": ClientPolicy(client_id="antigravity", client_name="Antigravity IDE"),
        "tok-cl": ClientPolicy(client_id="claude", client_name="Claude Desktop / Code"),
    }
    settings.gateway.upstream_servers = {
        "printer": UpstreamServerConfig(
            transport="http",
            url="https://mac-studio.example.ts.net:8445/mcp",
        ),
        "music-brain": UpstreamServerConfig(
            transport="stdio",
            command=music_brain_cmd,
        ),
    }

    res = install_client_configs(
        settings,
        tmp_path,
        ["antigravity", "claude-desktop"],
        profile="core",
        home_dir=home,
        prune_duplicates=True,
        extra_servers=["omnigent"],
    )

    ag_res = res["results"]["antigravity"]
    assert set(ag_res["migratedPruned"]) == {"mlflow", "music-brain", "printer"}
    assert ag_res["migratedBackup"] and Path(ag_res["migratedBackup"]).exists()
    assert set(ag_res["retargeted"]) == {"music-brain", "printer"}
    assert ag_res["added"] == ["omnigent"]

    ag_doc = json.loads(ag_path.read_text(encoding="utf-8"))
    assert set(ag_doc["mcpServers"]) == {
        "mcp-workshop-gateway",
        "music-brain",
        "omnigent",
        "printer",
        "unifi",
    }
    assert ag_doc["mcpServers"]["unifi"] == {
        "command": "/Users/spencer/repos/unifi/scripts/mcp-launch.sh"
    }
    assert ag_doc["mcpServers"]["printer"] == {
        "command": str(tmp_path.resolve() / ".venv/bin/mcp-stack"),
        "args": [
            "bridge",
            "--server",
            "printer",
            "--token-env-var",
            "MCP_ANTIGRAVITY_AUTH_TOKEN",
        ],
    }
    migrated_doc = json.loads(migrated_path.read_text(encoding="utf-8"))
    assert migrated_doc["mcpServers"] == {}

    cd_res = res["results"]["claude-desktop"]
    assert set(cd_res["retargeted"]) == {"music-brain", "printer"}
    assert cd_res["added"] == ["omnigent"]
    cd_doc = json.loads(desk_path.read_text(encoding="utf-8"))
    assert cd_doc["mcpServers"]["omnigent"] == {
        "command": str(tmp_path.resolve() / ".venv/bin/mcp-stack"),
        "args": [
            "bridge",
            "--server",
            "omnigent",
            "--token-env-var",
            "MCP_CLAUDE_AUTH_TOKEN",
        ],
    }

    post_audit = audit_client_configs(settings, home_dir=home, repos_root=tmp_path / "repos")
    assert post_audit["summary"]["shadowedClientEntries"] == 0
