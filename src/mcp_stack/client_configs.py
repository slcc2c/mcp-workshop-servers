"""Client configuration generators for Claude Code, Claude Desktop, Codex, and Cursor."""

from __future__ import annotations

import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp_stack.core.config import MCPStackSettings


def generate_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
) -> dict[str, str]:
    """Render configuration payloads for supported MCP clients."""
    root_str = str(repo_root.resolve())
    gw_url = f"http://{settings.gateway.host}:{settings.gateway.port}/mcp"
    auth_enabled = settings.gateway.effective_auth_enabled

    claude_gateway_entry: dict[str, Any] = {
        "type": "http",
        "url": gw_url,
    }
    if auth_enabled:
        claude_gateway_entry["headers"] = {
            "Authorization": "Bearer ${MCP_CLAUDE_AUTH_TOKEN}",
        }

    claude_code_payload: dict[str, Any] = {
        "mcpServers": {
            "mcp-workshop-gateway": claude_gateway_entry,
            "mlflow": {
                "type": "http",
                "url": settings.mlflow.mcp_url,
            },
            "mcp-photos": {
                "command": "uv",
                "args": [
                    "--directory",
                    root_str,
                    "run",
                    "mcp-stack",
                    "serve",
                    "photos",
                    "--transport",
                    "stdio",
                ],
                "env": {
                    "PHOTOS_EXPORT_ROOT": str(
                        settings.photos.export_root or "/Users/spencer/Exports/photos-mcp"
                    ),
                },
            },
        }
    }

    stdio_servers = [
        "unity-catalog",
        "mlflow",
        "memory",
        "filesystem",
        "github",
        "docker",
        "postgresql",
        "redis",
        "mongodb",
        "neo4j",
        "kubernetes",
        "jupyter",
        "photos",
        "xcodebuild",
    ]
    claude_desktop_servers: dict[str, Any] = {}
    for slug in stdio_servers:
        entry: dict[str, Any] = {
            "command": "uv",
            "args": [
                "--directory",
                root_str,
                "run",
                "mcp-stack",
                "serve",
                slug,
                "--transport",
                "stdio",
            ],
        }
        if slug == "photos":
            entry["env"] = {
                "PHOTOS_EXPORT_ROOT": str(
                    settings.photos.export_root or "/Users/spencer/Exports/photos-mcp"
                )
            }
        claude_desktop_servers[f"mcp-{slug}"] = entry

    claude_desktop_payload = {"mcpServers": claude_desktop_servers}

    cursor_gateway_entry: dict[str, Any] = {
        "url": gw_url,
    }
    if auth_enabled:
        cursor_gateway_entry["headers"] = {
            "Authorization": "Bearer ${env:MCP_CURSOR_AUTH_TOKEN}",
        }

    cursor_payload = {
        "mcpServers": {
            "mcp-workshop-gateway": cursor_gateway_entry,
            "mlflow": {
                "url": settings.mlflow.mcp_url,
            },
        }
    }

    photos_export = str(
        settings.photos.export_root or "/Users/spencer/Exports/photos-mcp"
    )
    codex_gateway_lines = [
        "[mcp_servers.mcp_workshop_gateway]",
        f'url = "{gw_url}"',
    ]
    if auth_enabled:
        codex_gateway_lines.append('bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"')

    codex_toml = "\n".join(
        [
            *codex_gateway_lines,
            "",
            "[mcp_servers.mlflow]",
            f'url = "{settings.mlflow.mcp_url}"',
            "",
            "[mcp_servers.mcp_photos]",
            'command = "uv"',
            (
                f'args = ["--directory", "{root_str}", "run", "mcp-stack", '
                '"serve", "photos", "--transport", "stdio"]'
            ),
            f'env = {{ PHOTOS_EXPORT_ROOT = "{photos_export}" }}',
            "",
        ]
    )

    return {
        "claude-code": json.dumps(claude_code_payload, indent=2) + "\n",
        "claude-desktop": json.dumps(claude_desktop_payload, indent=2) + "\n",
        "cursor": json.dumps(cursor_payload, indent=2) + "\n",
        "codex": codex_toml,
    }


def write_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
    target: str = "all",
) -> list[Path]:
    """Write selected client configs into repo root."""
    rendered = generate_client_configs(settings, repo_root)
    targets_map = {
        "claude-code": repo_root / ".mcp.json",
        "claude-desktop": repo_root / "claude-desktop-config.json",
        "cursor": repo_root / "cursor-mcp-config.json",
        "codex": repo_root / "config" / "codex-mcp-snippet.toml",
    }

    keys = list(targets_map.keys()) if target == "all" else [target]
    written: list[Path] = []
    for key in keys:
        if key not in targets_map:
            raise ValueError(f"Unknown client config target: {key}")
        dest = targets_map[key]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered[key], encoding="utf-8")
        written.append(dest)
    return written


def _backup_file(path: Path, stamp: str) -> str | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return str(backup)


def _upsert_codex_gateway_section(
    raw_toml: str,
    *,
    gw_url: str,
    auth_enabled: bool,
) -> str:
    new_lines = [
        "[mcp_servers.mcp_workshop_gateway]",
        f'url = "{gw_url}"',
    ]
    if auth_enabled:
        new_lines.append('bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"')

    lines = raw_toml.splitlines()
    start_idx: int | None = None
    end_idx = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[mcp_servers.mcp_workshop_gateway]":
            start_idx = idx
            continue
        if start_idx is not None and stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    if start_idx is None:
        prefix = raw_toml.rstrip("\n")
        sep = "\n\n" if prefix else ""
        updated = prefix + sep + "\n".join(new_lines) + "\n"
    else:
        replaced = [*lines[:start_idx], *new_lines, "", *lines[end_idx:]]
        updated = "\n".join(replaced).rstrip("\n") + "\n"

    tomllib.loads(updated)
    return updated


def install_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
    clients: list[str],
    *,
    dry_run: bool = False,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Non-destructively merge gateway/stdio MCP entries into live host client configs."""
    home = (home_dir or Path.home()).resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rendered = generate_client_configs(settings, repo_root)
    gw_url = f"http://{settings.gateway.host}:{settings.gateway.port}/mcp"
    auth_enabled = settings.gateway.effective_auth_enabled

    results: dict[str, Any] = {}
    for client_name in clients:
        key = client_name.strip().lower()
        if key == "codex":
            target = home / ".codex/config.toml"
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            updated = _upsert_codex_gateway_section(
                existing, gw_url=gw_url, auth_enabled=auth_enabled
            )
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(updated, encoding="utf-8")
            results["codex"] = {
                "path": str(target),
                "backup": backup,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "claude-code":
            target = home / ".claude.json"
            doc: dict[str, Any] = (
                json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            )
            servers = dict(doc.get("mcpServers") or {})
            src_cc = json.loads(rendered["claude-code"])["mcpServers"]
            servers["mcp-workshop-gateway"] = src_cc["mcp-workshop-gateway"]
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["claude-code"] = {
                "path": str(target),
                "backup": backup,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "claude-desktop":
            target = home / "Library/Application Support/Claude/claude_desktop_config.json"
            doc = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            servers = dict(doc.get("mcpServers") or {})
            src_cd = json.loads(rendered["claude-desktop"])["mcpServers"]
            for name_k, val in src_cd.items():
                servers[name_k] = val
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["claude-desktop"] = {
                "path": str(target),
                "backup": backup,
                "status": "dry_run" if dry_run else "updated",
                "entries": sorted(src_cd.keys()),
            }
        else:
            raise ValueError(f"Unsupported live install target: {client_name}")

    return {"dry_run": dry_run, "results": results}
