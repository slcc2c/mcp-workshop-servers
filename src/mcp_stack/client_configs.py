"""Client configuration generators for Antigravity, Codex, Claude, Cursor, and Gemini CLI."""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import shutil
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml

from mcp_stack.core.config import MCPStackSettings

_OMNIGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_NATIVE_CLIENT_SERVERS = frozenset({"computer-use", "node_repl"})
_PRINTER_CEL_REQUIRED_TOOLS = ("print", "print_note", "print_picture", "reprint_ticket")
_LEGACY_CLAUDE_DESKTOP_STDIO_SLUGS = frozenset(
    {
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
    }
)
_LEGACY_CLAUDE_DESKTOP_STDIO_KEYS = frozenset(
    f"mcp-{slug}" for slug in _LEGACY_CLAUDE_DESKTOP_STDIO_SLUGS
)


def _stdio_bridge_entry(
    settings: MCPStackSettings,
    repo_root: Path,
    *,
    token_env_var: str,
    profile: str | None = None,
    server: str | None = None,
) -> dict[str, Any]:
    """Build a self-contained `mcp-stack bridge` stdio entry for local GUI clients."""
    mcp_stack_bin = str(repo_root.resolve() / ".venv/bin/mcp-stack")
    is_default_base = (
        settings.gateway.host == "127.0.0.1" and settings.gateway.port == 8090
    )
    if server is not None:
        slug = server.strip().replace("_", "-").lower()
        if is_default_base:
            args = ["bridge", "--server", slug, "--token-env-var", token_env_var]
        else:
            args = [
                "bridge",
                "--url",
                f"{_gateway_base_url(settings)}/servers/{slug}/mcp",
                "--token-env-var",
                token_env_var,
            ]
    else:
        selected = (
            profile if profile is not None else settings.gateway.default_client_profile
        ).strip()
        if selected and selected != "full" and is_default_base:
            args = ["bridge", "--profile", selected, "--token-env-var", token_env_var]
        else:
            gw_url = _gateway_mcp_url(settings, profile=profile)
            args = ["bridge", "--url", gw_url, "--token-env-var", token_env_var]

    if not settings.gateway.effective_auth_enabled:
        args.append("--allow-unauthenticated")

    return {
        "command": mcp_stack_bin,
        "args": args,
    }


def _is_legacy_claude_desktop_stdio_entry(name: str, entry: dict[str, Any]) -> bool:
    """Return True for deprecated standalone mcp-<slug> stdio entries."""
    norm = name.strip().replace("_", "-").lower()
    if norm not in _LEGACY_CLAUDE_DESKTOP_STDIO_KEYS:
        return False
    target = _extract_mcp_target(entry)
    return "mcp-stack" in target and "serve" in target and "stdio" in target


def _gateway_base_url(settings: MCPStackSettings) -> str:
    return f"http://{settings.gateway.host}:{settings.gateway.port}"


def _gateway_mcp_url(settings: MCPStackSettings, profile: str | None = None) -> str:
    selected = (
        profile if profile is not None else settings.gateway.default_client_profile
    ).strip()
    base = _gateway_base_url(settings)
    if not selected or selected == "full":
        return f"{base}/mcp"
    return f"{base}/profiles/{selected}/mcp"


def _safe_load_json_dict(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        if not path.exists():
            return {}, None
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, f"Unreadable {path}: {exc}"
    if not raw.strip():
        return {}, None
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"Malformed JSON in {path}: {exc}"
    if not isinstance(loaded, dict):
        return {}, f"Expected JSON object in {path}"
    return loaded, None


def _resolve_auth_token(settings: MCPStackSettings, client_name: str) -> str:
    clean_client = client_name.strip().lower()
    env_var = _CLIENT_TOKEN_ENV.get(clean_client, "MCP_DEFAULT_AUTH_TOKEN")
    tok = os.getenv(env_var, "").strip()
    if not tok:
        for k, pol in settings.gateway.clients.items():
            if pol.client_id == clean_client or clean_client.startswith(pol.client_id):
                tok = k
                break
    if not tok:
        for k, pol in settings.gateway.clients.items():
            if "*" in pol.allowed_servers:
                tok = k
                break
    if not tok and settings.gateway.clients:
        tok = next(iter(settings.gateway.clients.keys()))
    return tok


def introspect_local_tool_catalog(settings: MCPStackSettings) -> dict[str, list[str]]:
    """Collect deterministic tool names for mounted built-in servers and profiles offline."""
    from mcp_stack.gateway.app import build_server_instance

    catalog: dict[str, list[str]] = {}

    async def _collect() -> None:
        server_tools: dict[str, list[str]] = {}
        for key in settings.gateway.enabled_servers:
            slug = key.strip().replace("_", "-").lower()
            try:
                srv, _ = build_server_instance(key, settings)
                tools = await srv.list_tools()
                names = sorted({getattr(t, "name", "") for t in tools if getattr(t, "name", "")})
                if names:
                    server_tools[slug] = names
                    catalog[slug] = names
            except Exception:
                continue

        for profile_name, members in settings.gateway.profiles.items():
            combined: set[str] = set()
            for member in members:
                m_slug = member.strip().replace("_", "-").lower()
                if m_slug in server_tools:
                    combined.update(server_tools[m_slug])
            if combined:
                catalog[f"profile:{profile_name.strip()}"] = sorted(combined)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_collect())
        return catalog
    return catalog


def discover_live_tool_catalog(
    settings: MCPStackSettings,
    *,
    timeout_s: float = 3.0,
) -> dict[str, list[str]]:
    """Query the running gateway /api/v1/tools and /health for exact tool names."""
    base = _gateway_base_url(settings)
    headers: dict[str, str] = {}
    if settings.gateway.effective_auth_enabled:
        tok = _resolve_auth_token(settings, "codex")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

    catalog: dict[str, list[str]] = {}
    with httpx.Client(timeout=timeout_s, headers=headers or None) as client:
        tools_resp = client.get(f"{base}/api/v1/tools")
        tools_resp.raise_for_status()
        tools_data = tools_resp.json()

        health_resp = client.get(f"{base}/health")
        health_resp.raise_for_status()
        health_data = health_resp.json()

    by_server: dict[str, set[str]] = {}
    for item in tools_data.get("tools", []):
        srv = str(item.get("server") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if srv and name:
            by_server.setdefault(srv, set()).add(name)

    for srv, names in by_server.items():
        catalog[srv] = sorted(names)

    for prof in health_data.get("profiles", []):
        pname = str(prof.get("name") or "").strip()
        if not pname:
            continue
        combined: set[str] = set()
        for srv in prof.get("servers", []):
            combined.update(by_server.get(str(srv).strip().lower(), set()))
        if prof.get("includesUpstreamMcp"):
            combined.update(by_server.get("mlflow-upstream", set()))
        if combined:
            catalog[f"profile:{pname}"] = sorted(combined)

    return catalog


def check_omnigent_cel_compatibility(services: list[dict[str, Any]]) -> list[str]:
    """Ensure Omnigent printer CEL approval rules match unprefixed printer tool names."""
    warnings: list[str] = []
    for svc in services:
        if svc.get("id") != "printer":
            continue
        tools = set(svc.get("tools") or [])
        missing = [t for t in _PRINTER_CEL_REQUIRED_TOOLS if t not in tools]
        if missing:
            warnings.append(
                "Omnigent CEL policy server_printer_approval expects unprefixed tools "
                f"{missing} on service 'printer'."
            )
    return warnings


def validate_omnigent_registry_services(services: list[dict[str, Any]]) -> list[str]:
    """Validate Omnigent McpRegistryConfig invariants without importing omnigent."""
    errors: list[str] = []
    seen: set[str] = set()
    for svc in services:
        sid = str(svc.get("id") or "")
        if not _OMNIGENT_ID_RE.match(sid) or "__" in sid:
            errors.append(f"Invalid Omnigent service id: {sid!r}")
        if sid in seen:
            errors.append(f"Duplicate Omnigent service id: {sid!r}")
        seen.add(sid)
        tools = svc.get("tools")
        if not isinstance(tools, list) or len(tools) < 1:
            errors.append(f"Service {sid!r} must have at least 1 tool in tools[]")
        url = str(svc.get("url") or "")
        parsed = urlsplit(url)
        allow_http = bool(svc.get("allow_http", False))
        allowed_schemes = {"http", "https"} if allow_http else {"https"}
        if parsed.scheme not in allowed_schemes or not parsed.hostname:
            errors.append(f"Service {sid!r} has invalid URL/allow_http pair: {url!r}")
    return errors


def build_omnigent_registry_payload(
    settings: MCPStackSettings,
    *,
    tool_catalog: dict[str, list[str]] | None = None,
    existing_services: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Build hybrid Omnigent mcp_registry.yaml routing domain servers & profiles via :8090."""
    base = _gateway_base_url(settings)
    catalog = tool_catalog if tool_catalog is not None else introspect_local_tool_catalog(settings)
    existing_by_id: dict[str, dict[str, Any]] = {
        str(s.get("id")): s
        for s in (existing_services or [])
        if isinstance(s, dict) and s.get("id")
    }
    auth_mode = "bearer" if settings.gateway.effective_auth_enabled else "none"
    warnings: list[str] = []
    managed_ids: list[str] = []
    services: list[dict[str, Any]] = []

    def _resolve_tools(lookup_keys: list[str], service_id: str) -> list[str]:
        for key in lookup_keys:
            items = catalog.get(key)
            if items:
                return sorted(set(items))
        prev = existing_by_id.get(service_id)
        if prev and isinstance(prev.get("tools"), list) and prev["tools"]:
            warnings.append(
                f"Service '{service_id}' had no live tools; "
                f"preserved {len(prev['tools'])} cached tools."
            )
            return [str(t) for t in prev["tools"]]
        warnings.append(
            f"Omitted Omnigent service '{service_id}': "
            "no tools discovered (Omnigent requires min_length=1)."
        )
        return []

    def _append_service(
        *,
        service_id: str,
        title: str,
        description: str,
        url: str,
        lookup_keys: list[str],
    ) -> None:
        tools = _resolve_tools(lookup_keys, service_id)
        if not tools:
            return
        entry: dict[str, Any] = {
            "id": service_id,
            "title": title,
            "description": description,
            "url": url,
            "auth": auth_mode,
        }
        if url.startswith("http://"):
            entry["allow_http"] = True
        entry["tools"] = tools
        services.append(entry)
        managed_ids.append(service_id)

    # 1. MLflow upstream MCP via gateway proxy
    mlflow_url = (
        f"{base}/servers/mlflow-upstream/mcp"
        if settings.mlflow.proxy_upstream_mcp
        else settings.mlflow.mcp_url
    )
    _append_service(
        service_id="mlflow",
        title="MLflow",
        description=(
            "MLflow 3.x tracking, trace search, assessments, scorers, "
            "and eval datasets via mcp-server."
        ),
        url=mlflow_url,
        lookup_keys=["mlflow-upstream", "mlflow"],
    )

    # 2. Federated external domain servers via /servers/<slug>/mcp
    for raw_name, up_cfg in sorted(settings.gateway.upstream_servers.items()):
        if not up_cfg.enabled:
            continue
        slug = raw_name.strip().replace("_", "-").lower()
        if not _OMNIGENT_ID_RE.match(slug) or "__" in slug:
            warnings.append(f"Skipped upstream '{raw_name}': invalid Omnigent service id '{slug}'.")
            continue
        title = slug.replace("-", " ").title()
        _append_service(
            service_id=slug,
            title=title,
            description=(
                up_cfg.description or f"Federated {slug} MCP server via mcp-server gateway."
            ),
            url=f"{base}/servers/{slug}/mcp",
            lookup_keys=[slug],
        )

    # 3. Curated mcp-server toolset profiles via /profiles/<name>/mcp
    for profile_name in sorted(settings.gateway.profiles.keys()):
        clean_p = profile_name.strip().replace("_", "-").lower()
        sid = f"mcp-{clean_p}"
        if not _OMNIGENT_ID_RE.match(sid):
            continue
        _append_service(
            service_id=sid,
            title=f"MCP Workshop ({clean_p})",
            description=f"Curated '{clean_p}' profile from mcp-server gateway.",
            url=f"{base}/profiles/{profile_name.strip()}/mcp",
            lookup_keys=[f"profile:{profile_name.strip()}", clean_p],
        )

    warnings.extend(check_omnigent_cel_compatibility(services))
    rendered = yaml.safe_dump({"services": services}, sort_keys=False)
    return rendered, managed_ids, warnings


def _profile_includes_mlflow(settings: MCPStackSettings, profile: str | None) -> bool:
    selected = (
        profile if profile is not None else settings.gateway.default_client_profile
    ).strip()
    if not selected or selected == "full":
        return True
    members = {
        m.strip().replace("_", "-").lower()
        for m in settings.gateway.profiles.get(selected, [])
    }
    return bool(members & {"mlflow", "mlflow-upstream"})


def generate_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
    *,
    profile: str | None = None,
    tool_catalog: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Render configuration payloads for supported MCP clients."""
    gw_url = _gateway_mcp_url(settings, profile=profile)
    auth_enabled = settings.gateway.effective_auth_enabled
    include_direct_mlflow = not _profile_includes_mlflow(settings, profile)

    claude_gateway_entry: dict[str, Any] = {
        "type": "http",
        "url": gw_url,
    }
    if auth_enabled:
        claude_gateway_entry["headers"] = {
            "Authorization": "Bearer ${MCP_CLAUDE_AUTH_TOKEN}",
        }

    claude_servers: dict[str, Any] = {
        "mcp-workshop-gateway": claude_gateway_entry,
    }
    if include_direct_mlflow:
        claude_servers["mlflow"] = {
            "type": "http",
            "url": settings.mlflow.mcp_url,
        }
    claude_code_payload: dict[str, Any] = {"mcpServers": claude_servers}

    claude_desktop_payload = {
        "mcpServers": {
            "mcp-workshop-gateway": _stdio_bridge_entry(
                settings,
                repo_root,
                token_env_var="MCP_CLAUDE_AUTH_TOKEN",
                profile=profile,
            ),
        }
    }

    cursor_gateway_entry: dict[str, Any] = {
        "url": gw_url,
    }
    if auth_enabled:
        cursor_gateway_entry["headers"] = {
            "Authorization": "Bearer ${env:MCP_CURSOR_AUTH_TOKEN}",
        }

    cursor_servers: dict[str, Any] = {
        "mcp-workshop-gateway": cursor_gateway_entry,
    }
    if include_direct_mlflow:
        cursor_servers["mlflow"] = {"url": settings.mlflow.mcp_url}
    cursor_payload = {"mcpServers": cursor_servers}

    codex_gateway_lines = [
        "[mcp_servers.mcp_workshop_gateway]",
        f'url = "{gw_url}"',
    ]
    if auth_enabled:
        codex_gateway_lines.append('bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"')

    codex_parts: list[str] = [*codex_gateway_lines, ""]
    if include_direct_mlflow:
        codex_parts.extend(
            [
                "[mcp_servers.mlflow]",
                f'url = "{settings.mlflow.mcp_url}"',
                "",
            ]
        )
    codex_toml = "\n".join(codex_parts)

    if auth_enabled:
        antigravity_entry: dict[str, Any] = _stdio_bridge_entry(
            settings,
            repo_root,
            token_env_var="MCP_ANTIGRAVITY_AUTH_TOKEN",
            profile=profile,
        )
    else:
        antigravity_entry = {"url": gw_url}
    ag_servers: dict[str, Any] = {"mcp-workshop-gateway": antigravity_entry}
    if include_direct_mlflow:
        ag_servers["mlflow"] = {"url": settings.mlflow.mcp_url}
    antigravity_payload = {"mcpServers": ag_servers}

    gemini_entry: dict[str, Any] = {"httpUrl": gw_url}
    if auth_enabled:
        gemini_entry["headers"] = {"Authorization": "Bearer ${MCP_GEMINI_AUTH_TOKEN}"}
    gem_servers: dict[str, Any] = {"mcp-workshop-gateway": gemini_entry}
    if include_direct_mlflow:
        gem_servers["mlflow"] = {"httpUrl": settings.mlflow.mcp_url}
    gemini_payload = {"mcpServers": gem_servers}

    omnigent_yaml, _, _ = build_omnigent_registry_payload(
        settings,
        tool_catalog=tool_catalog,
    )

    return {
        "antigravity": json.dumps(antigravity_payload, indent=2) + "\n",
        "claude-code": json.dumps(claude_code_payload, indent=2) + "\n",
        "claude-desktop": json.dumps(claude_desktop_payload, indent=2) + "\n",
        "cursor": json.dumps(cursor_payload, indent=2) + "\n",
        "codex": codex_toml,
        "gemini-cli": json.dumps(gemini_payload, indent=2) + "\n",
        "omnigent": omnigent_yaml,
    }


def write_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
    target: str = "all",
    *,
    profile: str | None = None,
) -> list[Path]:
    """Write selected client configs into repo root."""
    rendered = generate_client_configs(settings, repo_root, profile=profile)
    targets_map = {
        "claude-code": repo_root / ".mcp.json",
        "claude-desktop": repo_root / "claude-desktop-config.json",
        "cursor": repo_root / "cursor-mcp-config.json",
        "codex": repo_root / "config" / "codex-mcp-snippet.toml",
        "omnigent": repo_root / "config" / "omnigent-mcp-registry.yaml",
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


def _omnigent_local_host_lacks_cipher(home: Path) -> bool:
    """Return True when a local Omnigent host plist exists with no KMS/Vault cipher configured."""
    plist_path = home / "Library/LaunchAgents/ai.omnigent.host.plist"
    if not plist_path.is_file():
        return False
    env_vars: dict[str, Any] = {}
    try:
        data = plistlib.loads(plist_path.read_bytes())
        if isinstance(data, dict) and isinstance(data.get("EnvironmentVariables"), dict):
            env_vars = data["EnvironmentVariables"]
    except Exception:
        return True
    for key in ("OMNIGENT_CREDENTIAL_KMS_KEY_ID", "OMNIGENT_CREDENTIAL_VAULT_KEY"):
        if str(env_vars.get(key) or "").strip() or str(os.environ.get(key) or "").strip():
            return False
    return True


def _backup_file(path: Path, stamp: str) -> str | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return str(backup)


def _gateway_managed_slugs(settings: MCPStackSettings) -> set[str]:
    slugs = {s.strip().replace("_", "-").lower() for s in settings.gateway.enabled_servers}
    slugs.add("mlflow")
    slugs.add("mlflow-upstream")
    for name in settings.gateway.upstream_servers:
        slugs.add(name.strip().replace("_", "-").lower())
    return slugs


def _gateway_known_targets(settings: MCPStackSettings) -> set[str]:
    targets = {settings.mlflow.mcp_url.rstrip("/")}
    for cfg in settings.gateway.upstream_servers.values():
        if cfg.url:
            targets.add(cfg.url.rstrip("/"))
        if cfg.command:
            targets.add(cfg.command)
    return targets


def _extract_mcp_target(entry: dict[str, Any]) -> str:
    for key in ("url", "serverUrl", "httpUrl"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    cmd = str(entry.get("command") or "").strip()
    args = entry.get("args")
    if isinstance(args, list) and args:
        return f"{cmd} {' '.join(str(a) for a in args)}".strip()
    return cmd


def _is_shadowed_entry(
    name: str,
    entry: dict[str, Any],
    settings: MCPStackSettings,
    managed_slugs: set[str],
    known_targets: set[str],
) -> tuple[bool, str]:
    norm = name.strip().replace("_", "-").lower()
    if norm in _NATIVE_CLIENT_SERVERS or name in _NATIVE_CLIENT_SERVERS:
        return False, "client-native"
    if norm in {"mcp-workshop-gateway"}:
        return False, "gateway"
    if entry.get("enabled") is False or entry.get("disabled") is True:
        return False, "disabled"
    target = _extract_mcp_target(entry)
    if not target:
        return False, "override-only"
    if norm == "memory":
        env_map = entry.get("env")
        if isinstance(env_map, dict):
            mem_file = str(env_map.get("MEMORY_FILE_PATH") or "").strip()
            if mem_file.endswith(".jsonl"):
                return False, "project-scoped"
    base = _gateway_base_url(settings)
    if target.startswith(base):
        return False, "gateway-routed"
    if (
        ("mcp-stack" in target and " bridge " in f" {target} ")
        or "mcp-gateway-stdio-bridge.py" in target
    ):
        return False, "gateway-routed"
    if norm in managed_slugs:
        return True, f"server slug '{norm}' is managed by mcp-server gateway"
    if target.rstrip("/") in known_targets or str(entry.get("command") or "") in known_targets:
        return True, f"target '{target}' is already federated in mcp-server gateway"
    if norm == "agent-memory" and "agent_memory_mcp.py" in target:
        return True, "repo-local agent-memory shadows gateway 'printer-agent-memory'"
    if _is_legacy_claude_desktop_stdio_entry(name, entry):
        return (
            True,
            f"standalone stdio server '{norm}' should route via 'mcp-workshop-gateway'",
        )
    return False, "custom"


def audit_client_configs(
    settings: MCPStackSettings,
    *,
    home_dir: Path | None = None,
    repos_root: Path | None = None,
) -> dict[str, Any]:
    """Audit live MCP client configs and repo-local overrides for shadowed duplicates."""
    home = (home_dir or Path.home()).resolve()
    r_root = (repos_root or settings.skills.repos_root).expanduser()
    managed_slugs = _gateway_managed_slugs(settings)
    known_targets = _gateway_known_targets(settings)

    clients_report: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    repo_shadows: list[dict[str, Any]] = []

    def _record_entry(
        client_id: str,
        path: Path,
        srv_name: str,
        srv_obj: dict[str, Any],
    ) -> dict[str, Any]:
        target = _extract_mcp_target(srv_obj)
        shadowed, reason = _is_shadowed_entry(
            srv_name, srv_obj, settings, managed_slugs, known_targets
        )
        item = {
            "name": srv_name,
            "target": target,
            "shadowed": shadowed,
            "reason": reason,
        }
        if shadowed:
            duplicates.append(
                {
                    "client": client_id,
                    "path": str(path),
                    "server": srv_name,
                    "target": target,
                    "reason": reason,
                }
            )
        return item

    # 1. Codex
    codex_path = home / ".codex/config.toml"
    codex_entries: list[dict[str, Any]] = []
    codex_err: str | None = None
    codex_exists = False
    try:
        codex_exists = codex_path.exists()
        if codex_exists:
            doc = tomllib.loads(codex_path.read_text(encoding="utf-8"))
            for k, v in sorted((doc.get("mcp_servers") or {}).items()):
                if isinstance(v, dict):
                    codex_entries.append(_record_entry("codex", codex_path, k, v))
    except Exception as exc:
        codex_err = str(exc)
    clients_report.append(
        {
            "client": "codex",
            "path": str(codex_path),
            "exists": codex_exists,
            "error": codex_err,
            "servers": codex_entries,
        }
    )

    # 2. JSON-based clients
    json_clients = [
        ("claude-code", home / ".claude.json"),
        (
            "claude-desktop",
            home / "Library/Application Support/Claude/claude_desktop_config.json",
        ),
        ("cursor", home / ".cursor/mcp.json"),
        ("antigravity", home / ".gemini/config/mcp_config.json"),
        (
            "antigravity-legacy",
            home / ".gemini/antigravity/mcp_config.json",
        ),
        (
            "antigravity-migrated",
            home / ".gemini/config/plugins/migrated-settings/mcp_config.json",
        ),
        ("gemini-cli", home / ".gemini/settings.json"),
    ]
    for cid, cpath in json_clients:
        doc, err = _safe_load_json_dict(cpath)
        entries: list[dict[str, Any]] = []
        for k, v in sorted((doc.get("mcpServers") or {}).items()):
            if isinstance(v, dict):
                entries.append(_record_entry(cid, cpath, k, v))
        try:
            c_exists = cpath.exists()
        except OSError:
            c_exists = False
        clients_report.append(
            {
                "client": cid,
                "path": str(cpath),
                "exists": c_exists,
                "error": err,
                "servers": entries,
            }
        )

    # 3. Omnigent mcp_registry.yaml
    omni_path = home / ".omnigent/mcp_registry.yaml"
    omni_entries: list[dict[str, Any]] = []
    omni_err: str | None = None
    omni_exists = False
    try:
        omni_exists = omni_path.exists()
        if omni_exists:
            loaded = yaml.safe_load(omni_path.read_text(encoding="utf-8")) or {}
            for svc in loaded.get("services", []):
                if isinstance(svc, dict) and svc.get("id"):
                    omni_entries.append(
                        _record_entry("omnigent", omni_path, str(svc["id"]), svc)
                    )
    except Exception as exc:
        omni_err = str(exc)
    clients_report.append(
        {
            "client": "omnigent",
            "path": str(omni_path),
            "exists": omni_exists,
            "error": omni_err,
            "servers": omni_entries,
        }
    )

    # 4. Repo-local .mcp.json and .codex/config.toml shadows
    try:
        repos_ok = r_root.exists() and r_root.is_dir()
    except OSError:
        repos_ok = False
    if repos_ok:
        seen_repos: set[Path] = set()
        try:
            repo_dirs = sorted(r_root.iterdir())
        except OSError:
            repo_dirs = []
        for repo_dir in repo_dirs:
            try:
                if not repo_dir.is_dir():
                    continue
                resolved = repo_dir.resolve()
            except OSError:
                continue
            if resolved in seen_repos:
                continue
            seen_repos.add(resolved)
            mcp_json = resolved / ".mcp.json"
            try:
                mcp_exists = mcp_json.exists()
            except OSError:
                mcp_exists = False
            if mcp_exists:
                doc, _ = _safe_load_json_dict(mcp_json)
                for k, v in sorted((doc.get("mcpServers") or {}).items()):
                    if isinstance(v, dict):
                        shadowed, reason = _is_shadowed_entry(
                            k, v, settings, managed_slugs, known_targets
                        )
                        if shadowed:
                            repo_shadows.append(
                                {
                                    "repo": repo_dir.name,
                                    "path": str(mcp_json),
                                    "server": k,
                                    "target": _extract_mcp_target(v),
                                    "reason": reason,
                                }
                            )
            codex_toml = resolved / ".codex/config.toml"
            try:
                if codex_toml.exists():
                    cdoc = tomllib.loads(codex_toml.read_text(encoding="utf-8"))
                    for k, v in sorted((cdoc.get("mcp_servers") or {}).items()):
                        if isinstance(v, dict):
                            shadowed, reason = _is_shadowed_entry(
                                k, v, settings, managed_slugs, known_targets
                            )
                            if shadowed:
                                repo_shadows.append(
                                    {
                                        "repo": repo_dir.name,
                                        "path": str(codex_toml),
                                        "server": k,
                                        "target": _extract_mcp_target(v),
                                        "reason": reason,
                                    }
                                )
            except Exception:
                pass

    return {
        "clients": clients_report,
        "duplicates": duplicates,
        "repoShadows": repo_shadows,
        "summary": {
            "totalClients": len(clients_report),
            "shadowedClientEntries": len(duplicates),
            "repoShadows": len(repo_shadows),
        },
    }


def _strip_toml_mcp_section(raw_toml: str, server_key: str) -> str:
    """Remove `[mcp_servers.<key>]` (quoted or bare) and its body from TOML text."""
    lines = raw_toml.splitlines()
    target_headers = {
        f"[mcp_servers.{server_key}]",
        f'[mcp_servers."{server_key}"]',
    }
    subtable_prefixes = (
        f"[mcp_servers.{server_key}.",
        f'[mcp_servers."{server_key}".',
    )
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped in target_headers or stripped.startswith(subtable_prefixes):
                skipping = True
                continue
            skipping = False
        if not skipping:
            out.append(line)
    cleaned = "\n".join(out).strip("\n")
    return (cleaned + "\n") if cleaned else ""


def _retarget_toml_server_to_gateway(
    raw_toml: str,
    *,
    server_key: str,
    gateway_url: str,
    auth_enabled: bool,
) -> str:
    """Update [mcp_servers.<key>] to a gateway HTTP endpoint while preserving extra flags."""
    lines = raw_toml.splitlines()
    headers_match = {f"[mcp_servers.{server_key}]", f'[mcp_servers."{server_key}"]'}
    start_idx: int | None = None
    end_idx = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped in headers_match:
            start_idx = idx
            continue
        if start_idx is not None and stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break
    if start_idx is None:
        return raw_toml

    new_block: list[str] = [lines[start_idx]]
    saw_url = False
    saw_bearer = False
    for line in lines[start_idx + 1 : end_idx]:
        stripped = line.strip()
        if stripped.startswith(("url", "command", "args")):
            if not saw_url:
                new_block.append(f'url = "{gateway_url}"')
                saw_url = True
        elif stripped.startswith("bearer_token_env_var"):
            if auth_enabled:
                new_block.append('bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"')
            saw_bearer = True
        else:
            new_block.append(line)
    if not saw_url:
        new_block.insert(1, f'url = "{gateway_url}"')
    if auth_enabled and not saw_bearer:
        new_block.append('bearer_token_env_var = "MCP_CODEX_AUTH_TOKEN"')

    updated = "\n".join([*lines[:start_idx], *new_block, *lines[end_idx:]]).rstrip("\n") + "\n"
    tomllib.loads(updated)
    return updated


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


def _is_bridge_entry(entry: dict[str, Any]) -> bool:
    """Return True when an MCP client entry invokes `mcp-stack bridge`."""
    target = _extract_mcp_target(entry)
    return "mcp-stack" in target and " bridge " in f" {target} "


def install_client_configs(
    settings: MCPStackSettings,
    repo_root: Path,
    clients: list[str],
    *,
    profile: str | None = None,
    dry_run: bool = False,
    home_dir: Path | None = None,
    prune_duplicates: bool = False,
    tool_catalog: dict[str, list[str]] | None = None,
    sync_atelier_template: Path | None = None,
    extra_servers: list[str] | None = None,
) -> dict[str, Any]:
    """Non-destructively merge gateway/stdio MCP entries into live host client configs."""
    home = (home_dir or Path.home()).resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rendered = generate_client_configs(
        settings, repo_root, profile=profile, tool_catalog=tool_catalog
    )
    gw_url = _gateway_mcp_url(settings, profile=profile)
    auth_enabled = settings.gateway.effective_auth_enabled
    managed_slugs = _gateway_managed_slugs(settings)
    known_targets = _gateway_known_targets(settings)
    selected_profile = (
        profile if profile is not None else settings.gateway.default_client_profile
    ).strip() or "full"
    profile_members = {
        m.strip().replace("_", "-").lower()
        for m in settings.gateway.profiles.get(selected_profile, [])
    }
    if "mlflow-upstream" in profile_members or selected_profile == "core":
        profile_members.add("mlflow")
    if selected_profile == "full":
        profile_members |= managed_slugs
    live_upstreams = {
        k.strip().replace("_", "-").lower()
        for k, v in settings.gateway.upstream_servers.items()
        if v.enabled
        and (tool_catalog is None or k.strip().replace("_", "-").lower() in tool_catalog)
    }
    normalized_extras = [
        s.strip().replace("_", "-").lower()
        for s in (extra_servers or [])
        if s.strip()
    ]

    results: dict[str, Any] = {}
    for client_name in clients:
        key = client_name.strip().lower()
        if key == "codex":
            target = home / ".codex/config.toml"
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            updated = _upsert_codex_gateway_section(
                existing, gw_url=gw_url, auth_enabled=auth_enabled
            )
            pruned: list[str] = []
            retargeted: list[str] = []
            if prune_duplicates and updated.strip():
                parsed_codex = tomllib.loads(updated)
                for srv_key, srv_val in list((parsed_codex.get("mcp_servers") or {}).items()):
                    if not isinstance(srv_val, dict):
                        continue
                    norm_key = srv_key.strip().replace("_", "-").lower()
                    if norm_key in profile_members:
                        shadowed, _ = _is_shadowed_entry(
                            srv_key, srv_val, settings, managed_slugs, known_targets
                        )
                        if shadowed:
                            updated = _strip_toml_mcp_section(updated, srv_key)
                            pruned.append(srv_key)
                    elif norm_key in live_upstreams:
                        gw_srv_url = f"{_gateway_base_url(settings)}/servers/{norm_key}/mcp"
                        if str(srv_val.get("url") or "").rstrip("/") != gw_srv_url:
                            updated = _retarget_toml_server_to_gateway(
                                updated,
                                server_key=srv_key,
                                gateway_url=gw_srv_url,
                                auth_enabled=auth_enabled,
                            )
                            retargeted.append(srv_key)
                tomllib.loads(updated)
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(updated, encoding="utf-8")
            results["codex"] = {
                "path": str(target),
                "backup": backup,
                "pruned": pruned,
                "retargeted": retargeted,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "claude-code":
            target = home / ".claude.json"
            doc, _ = _safe_load_json_dict(target)
            servers = dict(doc.get("mcpServers") or {})
            src_cc = json.loads(rendered["claude-code"])["mcpServers"]
            servers["mcp-workshop-gateway"] = src_cc["mcp-workshop-gateway"]
            pruned_cc: list[str] = []
            retargeted_cc: list[str] = []
            if prune_duplicates:
                for srv_key in list(servers.keys()):
                    srv_val = servers[srv_key]
                    if not isinstance(srv_val, dict):
                        continue
                    norm_key = srv_key.strip().replace("_", "-").lower()
                    if norm_key in profile_members:
                        shadowed, _ = _is_shadowed_entry(
                            srv_key, srv_val, settings, managed_slugs, known_targets
                        )
                        if shadowed:
                            del servers[srv_key]
                            pruned_cc.append(srv_key)
                    elif norm_key in live_upstreams:
                        gw_srv_url = f"{_gateway_base_url(settings)}/servers/{norm_key}/mcp"
                        if str(srv_val.get("url") or "").rstrip("/") != gw_srv_url:
                            new_entry: dict[str, Any] = {"type": "http", "url": gw_srv_url}
                            if auth_enabled:
                                new_entry["headers"] = {
                                    "Authorization": "Bearer ${MCP_CLAUDE_AUTH_TOKEN}"
                                }
                            servers[srv_key] = new_entry
                            retargeted_cc.append(srv_key)
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["claude-code"] = {
                "path": str(target),
                "backup": backup,
                "pruned": pruned_cc,
                "retargeted": retargeted_cc,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "claude-desktop":
            target = home / "Library/Application Support/Claude/claude_desktop_config.json"
            doc, _ = _safe_load_json_dict(target)
            servers = dict(doc.get("mcpServers") or {})
            src_cd = json.loads(rendered["claude-desktop"])["mcpServers"]
            for name_k, val in src_cd.items():
                servers[name_k] = val
            pruned_cd: list[str] = []
            retargeted_cd: list[str] = []
            added_cd: list[str] = []
            if prune_duplicates:
                for srv_key in list(servers.keys()):
                    srv_val = servers[srv_key]
                    if not isinstance(srv_val, dict):
                        continue
                    if _is_legacy_claude_desktop_stdio_entry(srv_key, srv_val):
                        del servers[srv_key]
                        pruned_cd.append(srv_key)
                        continue
                    norm_key = srv_key.strip().replace("_", "-").lower()
                    if norm_key in profile_members:
                        shadowed, _ = _is_shadowed_entry(
                            srv_key, srv_val, settings, managed_slugs, known_targets
                        )
                        if shadowed:
                            del servers[srv_key]
                            pruned_cd.append(srv_key)
                    elif norm_key in live_upstreams and not _is_bridge_entry(srv_val):
                        servers[srv_key] = _stdio_bridge_entry(
                            settings,
                            repo_root,
                            token_env_var="MCP_CLAUDE_AUTH_TOKEN",
                            server=norm_key,
                        )
                        retargeted_cd.append(srv_key)
            for slug in normalized_extras:
                servers[slug] = _stdio_bridge_entry(
                    settings,
                    repo_root,
                    token_env_var="MCP_CLAUDE_AUTH_TOKEN",
                    server=slug,
                )
                added_cd.append(slug)
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["claude-desktop"] = {
                "path": str(target),
                "backup": backup,
                "pruned": pruned_cd,
                "retargeted": retargeted_cd,
                "added": added_cd,
                "status": "dry_run" if dry_run else "updated",
                "entries": sorted(servers.keys()),
            }
        elif key == "antigravity":
            target = home / ".gemini/config/mcp_config.json"
            migrated_target = (
                home / ".gemini/config/plugins/migrated-settings/mcp_config.json"
            )
            doc, _ = _safe_load_json_dict(target)
            servers = dict(doc.get("mcpServers") or {})
            src_ag = json.loads(rendered["antigravity"])["mcpServers"]
            servers["mcp-workshop-gateway"] = src_ag["mcp-workshop-gateway"]

            def _ag_server_entry(server_slug: str) -> dict[str, Any]:
                if auth_enabled:
                    return _stdio_bridge_entry(
                        settings,
                        repo_root,
                        token_env_var="MCP_ANTIGRAVITY_AUTH_TOKEN",
                        server=server_slug,
                    )
                return {"url": f"{_gateway_base_url(settings)}/servers/{server_slug}/mcp"}

            pruned_ag: list[str] = []
            retargeted_ag: list[str] = []
            added_ag: list[str] = []
            migrated_pruned: list[str] = []
            migrated_backup: str | None = None

            if prune_duplicates:
                for srv_key in list(servers.keys()):
                    srv_val = servers[srv_key]
                    if not isinstance(srv_val, dict):
                        continue
                    norm_key = srv_key.strip().replace("_", "-").lower()
                    if norm_key in profile_members:
                        shadowed, _ = _is_shadowed_entry(
                            srv_key, srv_val, settings, managed_slugs, known_targets
                        )
                        if shadowed:
                            del servers[srv_key]
                            pruned_ag.append(srv_key)
                    elif norm_key in live_upstreams:
                        desired_entry = _ag_server_entry(norm_key)
                        if servers[srv_key] != desired_entry:
                            servers[srv_key] = desired_entry
                            retargeted_ag.append(srv_key)

                if migrated_target.exists():
                    migrated_doc, _ = _safe_load_json_dict(migrated_target)
                    migrated_servers = dict(migrated_doc.get("mcpServers") or {})
                    for srv_key in list(migrated_servers.keys()):
                        srv_val = migrated_servers[srv_key]
                        if not isinstance(srv_val, dict):
                            continue
                        norm_key = srv_key.strip().replace("_", "-").lower()
                        shadowed, _ = _is_shadowed_entry(
                            srv_key, srv_val, settings, managed_slugs, known_targets
                        )
                        if not shadowed:
                            continue
                        if norm_key in profile_members:
                            del migrated_servers[srv_key]
                            migrated_pruned.append(srv_key)
                        elif norm_key in live_upstreams:
                            del migrated_servers[srv_key]
                            migrated_pruned.append(srv_key)
                            existing_primary = servers.get(norm_key)
                            existing_shadowed = isinstance(existing_primary, dict) and (
                                _is_shadowed_entry(
                                    norm_key,
                                    existing_primary,
                                    settings,
                                    managed_slugs,
                                    known_targets,
                                )[0]
                            )
                            if norm_key not in servers or existing_shadowed:
                                servers[norm_key] = _ag_server_entry(norm_key)
                                if norm_key not in retargeted_ag:
                                    retargeted_ag.append(norm_key)

                    if migrated_pruned and not dry_run:
                        migrated_doc["mcpServers"] = migrated_servers
                        migrated_backup = _backup_file(migrated_target, stamp)
                        migrated_target.write_text(
                            json.dumps(migrated_doc, indent=2) + "\n", encoding="utf-8"
                        )

            for slug in normalized_extras:
                servers[slug] = _ag_server_entry(slug)
                added_ag.append(slug)

            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["antigravity"] = {
                "path": str(target),
                "backup": backup,
                "pruned": pruned_ag,
                "retargeted": retargeted_ag,
                "added": added_ag,
                "migratedPruned": migrated_pruned,
                "migratedBackup": migrated_backup,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "gemini-cli":
            target = home / ".gemini/settings.json"
            doc, _ = _safe_load_json_dict(target)
            servers = dict(doc.get("mcpServers") or {})
            src_gc = json.loads(rendered["gemini-cli"])["mcpServers"]
            servers["mcp-workshop-gateway"] = src_gc["mcp-workshop-gateway"]
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["gemini-cli"] = {
                "path": str(target),
                "backup": backup,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "cursor":
            target = home / ".cursor/mcp.json"
            doc, _ = _safe_load_json_dict(target)
            servers = dict(doc.get("mcpServers") or {})
            src_cu = json.loads(rendered["cursor"])["mcpServers"]
            servers["mcp-workshop-gateway"] = src_cu["mcp-workshop-gateway"]
            pruned_cu: list[str] = []
            if prune_duplicates:
                for srv_key in list(servers.keys()):
                    srv_val = servers[srv_key]
                    if not isinstance(srv_val, dict):
                        continue
                    shadowed, _ = _is_shadowed_entry(
                        srv_key, srv_val, settings, managed_slugs, known_targets
                    )
                    if shadowed:
                        del servers[srv_key]
                        pruned_cu.append(srv_key)
            doc["mcpServers"] = servers
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            results["cursor"] = {
                "path": str(target),
                "backup": backup,
                "pruned": pruned_cu,
                "status": "dry_run" if dry_run else "updated",
            }
        elif key == "omnigent":
            target = (
                home / ".omnigent/mcp_registry.yaml"
                if home_dir is not None
                else settings.omnigent_registry_path.expanduser()
            )
            existing_services: list[dict[str, Any]] = []
            if target.exists():
                loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict) and isinstance(loaded.get("services"), list):
                    existing_services = [
                        s for s in loaded["services"] if isinstance(s, dict)
                    ]
            omni_yaml, managed_ids, warnings = build_omnigent_registry_payload(
                settings,
                tool_catalog=tool_catalog,
                existing_services=existing_services,
            )
            generated_doc = yaml.safe_load(omni_yaml) or {}
            gen_services = list(generated_doc.get("services") or [])
            gen_ids = {str(s["id"]) for s in gen_services}
            preserved_custom = [
                s for s in existing_services if str(s.get("id")) not in gen_ids
            ]
            merged_services = [*gen_services, *preserved_custom]
            schema_errors = validate_omnigent_registry_services(merged_services)
            if schema_errors:
                raise ValueError(
                    "Generated Omnigent mcp_registry.yaml failed validation: "
                    + "; ".join(schema_errors)
                )
            if (
                any(str(s.get("auth") or "") in {"bearer", "oauth"} for s in merged_services)
                and _omnigent_local_host_lacks_cipher(home)
            ):
                warnings.append(
                    "Skipped writing ~/.omnigent/mcp_registry.yaml with auth=bearer/oauth: "
                    "local ai.omnigent.host.plist has neither OMNIGENT_CREDENTIAL_KMS_KEY_ID "
                    "nor OMNIGENT_CREDENTIAL_VAULT_KEY configured "
                    "(omnigent >=0.23 fails startup without a cipher)."
                )
                results["omnigent"] = {
                    "path": str(target),
                    "backup": None,
                    "managedServices": managed_ids,
                    "preservedCustom": len(preserved_custom),
                    "warnings": warnings,
                    "status": "skipped_missing_cipher",
                }
                continue
            final_yaml = yaml.safe_dump({"services": merged_services}, sort_keys=False)
            backup = None
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = _backup_file(target, stamp)
                target.write_text(final_yaml, encoding="utf-8")
                if sync_atelier_template is not None:
                    sync_atelier_template.parent.mkdir(parents=True, exist_ok=True)
                    sync_atelier_template.write_text(final_yaml, encoding="utf-8")
            results["omnigent"] = {
                "path": str(target),
                "backup": backup,
                "services": managed_ids,
                "preservedCustom": [str(s.get("id")) for s in preserved_custom],
                "warnings": warnings,
                "atelierTemplateSynced": str(sync_atelier_template)
                if (sync_atelier_template is not None and not dry_run)
                else None,
                "status": "dry_run" if dry_run else "updated",
            }
        else:
            raise ValueError(f"Unsupported live install target: {client_name}")

    return {"dry_run": dry_run, "results": results}


_CLIENT_TOKEN_ENV: dict[str, str] = {
    "codex": "MCP_CODEX_AUTH_TOKEN",
    "claude-code": "MCP_CLAUDE_AUTH_TOKEN",
    "claude-desktop": "MCP_CLAUDE_AUTH_TOKEN",
    "cursor": "MCP_CURSOR_AUTH_TOKEN",
    "antigravity": "MCP_ANTIGRAVITY_AUTH_TOKEN",
    "gemini-cli": "MCP_GEMINI_AUTH_TOKEN",
    "omnigent": "MCP_OMNIGENT_AUTH_TOKEN",
}


async def verify_client_connection(
    settings: MCPStackSettings,
    *,
    client: str = "codex",
    profile: str | None = None,
    timeout_s: float = 5.0,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Perform a live Streamable HTTP MCP initialize + tools/list probe for a client profile."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    clean_client = client.strip().lower()
    gw_url = _gateway_mcp_url(settings, profile=profile)
    selected_profile = (
        profile if profile is not None else settings.gateway.default_client_profile
    ).strip() or "full"
    headers: dict[str, str] = {}
    auth_status = "open"
    if settings.gateway.effective_auth_enabled:
        tok = _resolve_auth_token(settings, clean_client)
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
            auth_status = "bearer"
        else:
            auth_status = "missing_token"

    omnigent_check: dict[str, Any] | None = None
    if clean_client == "omnigent":
        reg_path = (
            (home_dir.resolve() / ".omnigent/mcp_registry.yaml")
            if home_dir is not None
            else settings.omnigent_registry_path.expanduser()
        )
        if reg_path.exists():
            loaded = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            svcs = [s for s in loaded.get("services", []) if isinstance(s, dict)]
            errs = validate_omnigent_registry_services(svcs)
            cel_warns = check_omnigent_cel_compatibility(svcs)
            omnigent_check = {
                "registryPath": str(reg_path),
                "serviceCount": len(svcs),
                "schemaValid": len(errs) == 0,
                "schemaErrors": errs,
                "celWarnings": cel_warns,
            }
        else:
            omnigent_check = {
                "registryPath": str(reg_path),
                "serviceCount": 0,
                "schemaValid": False,
                "schemaErrors": [f"Registry file not found: {reg_path}"],
                "celWarnings": [],
            }

    t0 = time.monotonic()
    out: dict[str, Any]
    try:
        transport = StreamableHttpTransport(gw_url, headers=headers or None)
        async with Client(transport, timeout=timeout_s) as mcp_cli:
            tools = await mcp_cli.list_tools()
            init_res = getattr(mcp_cli, "initialize_result", None)
            proto = getattr(init_res, "protocolVersion", None) if init_res else None
            out = {
                "ok": True,
                "client": clean_client,
                "profile": selected_profile,
                "url": gw_url,
                "authStatus": auth_status,
                "protocolVersion": proto or "2025-11-25",
                "toolCount": len(tools),
                "latencyMs": round((time.monotonic() - t0) * 1000.0, 2),
            }
            if omnigent_check is not None:
                out["omnigentRegistry"] = omnigent_check
                if not omnigent_check["schemaValid"]:
                    out["ok"] = False
    except Exception as exc:
        out_err: dict[str, Any] = {
            "ok": False,
            "client": clean_client,
            "profile": selected_profile,
            "url": gw_url,
            "authStatus": auth_status,
            "latencyMs": round((time.monotonic() - t0) * 1000.0, 2),
            "error": str(exc),
        }
        if omnigent_check is not None:
            out_err["omnigentRegistry"] = omnigent_check
        return out_err

    if clean_client in {"antigravity", "claude-desktop"}:
        from fastmcp.client.transports import StdioTransport

        repo_root = Path(__file__).resolve().parents[2]
        token_env_var = _CLIENT_TOKEN_ENV.get(clean_client, "MCP_CLAUDE_AUTH_TOKEN")
        bridge_entry = _stdio_bridge_entry(
            settings,
            repo_root,
            token_env_var=token_env_var,
            profile=profile,
        )
        stripped_env = {
            k: v
            for k, v in os.environ.items()
            if not (k.startswith("MCP_") and k.endswith("_AUTH_TOKEN")) and k != "AUTH_TOKEN"
        }
        bt0 = time.monotonic()
        try:
            stdio_transport = StdioTransport(
                command=bridge_entry["command"],
                args=bridge_entry["args"],
                env=stripped_env,
            )
            async with Client(stdio_transport, timeout=timeout_s) as bridge_cli:
                bridge_tools = await bridge_cli.list_tools()
            out["bridgeOk"] = True
            out["bridgeToolCount"] = len(bridge_tools)
            out["bridgeLatencyMs"] = round((time.monotonic() - bt0) * 1000.0, 2)
        except Exception as exc:
            out["bridgeOk"] = False
            out["bridgeError"] = str(exc)
            out["bridgeLatencyMs"] = round((time.monotonic() - bt0) * 1000.0, 2)
            out["ok"] = False

    return out


_HOOK_START = "# >>> mcp-workshop-stack tokens >>>"
_HOOK_END = "# <<< mcp-workshop-stack tokens <<<"


def install_shell_hook(
    repo_root: Path,
    *,
    shell_rc: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Idempotently install a silent guarded token-autoload block into ~/.zshrc."""
    target = (shell_rc or (Path.home() / ".zshrc")).expanduser().resolve()
    loader = (repo_root.resolve() / "deploy/launchd/load_mcp_tokens.sh").resolve()
    block_lines = [
        _HOOK_START,
        f'if [ -r "{loader}" ]; then',
        f'  . "{loader}" >/dev/null 2>&1 || true',
        "fi",
        _HOOK_END,
    ]
    block = "\n".join(block_lines)

    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    start_pos = existing.find(_HOOK_START)
    end_pos = existing.find(_HOOK_END)
    if start_pos != -1 and end_pos != -1 and end_pos >= start_pos:
        after_end = end_pos + len(_HOOK_END)
        updated = existing[:start_pos].rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += block + existing[after_end:]
        if not updated.endswith("\n"):
            updated += "\n"
        action = "updated"
    else:
        prefix = existing.rstrip("\n")
        sep = "\n\n" if prefix else ""
        updated = prefix + sep + block + "\n"
        action = "appended"

    backup: str | None = None
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = _backup_file(target, stamp)
        target.write_text(updated, encoding="utf-8")

    return {
        "dry_run": dry_run,
        "path": str(target),
        "loader": str(loader),
        "backup": backup,
        "status": f"dry_run_{action}" if dry_run else action,
    }
