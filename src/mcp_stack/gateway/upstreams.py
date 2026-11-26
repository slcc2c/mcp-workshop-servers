"""Build and probe federated external HTTP/stdio MCP proxies for the Gateway."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fastmcp.server import create_proxy
from pydantic import SecretStr

from mcp_stack.core.config import MCPStackSettings, UpstreamServerConfig
from mcp_stack.core.secrets import SecretResolutionError, SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware

_PREFIXED_ENV_RE = re.compile(r"^(.*?)\benv:([A-Za-z_][A-Za-z0-9_]*)(.*)$")


def _slug_for(name: str) -> str:
    return name.strip().replace("_", "-").lower()


def resolve_secret_mapping(
    mapping: dict[str, SecretStr],
    resolver: SecretResolver,
) -> tuple[dict[str, str], list[str]]:
    """Resolve SecretStr mapping values including `Bearer env:VAR` & `Bearer op://...`."""
    resolved: dict[str, str] = {}
    missing_env: list[str] = []
    for key, secret in mapping.items():
        raw = secret.get_secret_value().strip()
        if raw.startswith(("env:", "op://")):
            try:
                val = resolver.resolve(secret)
            except SecretResolutionError as exc:
                missing_env.append(f"{raw} ({exc})")
                continue
            if not val:
                if raw.startswith("env:"):
                    missing_env.append(raw.removeprefix("env:").strip())
                else:
                    missing_env.append(raw)
                continue
            resolved[key] = val
            continue

        if "op://" in raw:
            op_idx = raw.index("op://")
            prefix = raw[:op_idx]
            op_ref = raw[op_idx:].strip()
            try:
                val = resolver.resolve(op_ref)
            except SecretResolutionError as exc:
                missing_env.append(f"{op_ref} ({exc})")
                continue
            if not val:
                missing_env.append(op_ref)
                continue
            resolved[key] = f"{prefix}{val}"
            continue

        match = _PREFIXED_ENV_RE.match(raw)
        if match:
            prefix, var_name, suffix = match.groups()
            env_val = os.getenv(var_name, "").strip()
            if not env_val:
                missing_env.append(var_name)
                continue
            resolved[key] = f"{prefix}{env_val}{suffix}"
            continue

        if raw:
            resolved[key] = raw
    return resolved, missing_env


def build_upstream_proxy(
    raw_name: str,
    cfg: UpstreamServerConfig,
    settings: MCPStackSettings,
    *,
    resolver: SecretResolver | None = None,
) -> tuple[FastMCP | None, dict[str, Any]]:
    """Create a FastMCP proxy + initial metadata for a configured external MCP server."""
    slug = _slug_for(raw_name)
    res = resolver or SecretResolver(settings.secrets)
    info: dict[str, Any] = {
        "key": raw_name.replace("-", "_"),
        "slug": slug,
        "route": f"/servers/{slug}/mcp",
        "transport": cfg.transport,
        "external": True,
        "registryName": cfg.registry_name,
        "governance": cfg.governance,
        "description": cfg.description,
    }

    if not cfg.enabled:
        info["status"] = "disabled"
        info["connectionStatus"] = "disabled"
        return None, info

    if cfg.transport == "http":
        if not cfg.url:
            info["status"] = "unconfigured"
            info["connectionStatus"] = "unconfigured"
            info["detail"] = "Missing upstream URL"
            return None, info
        info["target"] = cfg.url
        headers, missing_env = resolve_secret_mapping(cfg.headers, res)
        if missing_env:
            info["status"] = "auth_required"
            info["connectionStatus"] = "auth_required"
            info["missingEnv"] = missing_env
            info["detail"] = f"Set {', '.join(missing_env)} to activate {slug}"
            return None, info
        transport: StreamableHttpTransport | StdioTransport = StreamableHttpTransport(
            cfg.url,
            headers=headers or None,
        )
    else:
        if not cfg.command:
            info["status"] = "unconfigured"
            info["connectionStatus"] = "unconfigured"
            info["detail"] = "Missing stdio command"
            return None, info
        cmd_path = Path(cfg.command)
        cmd_exists = (
            cmd_path.exists()
            if cmd_path.is_absolute() or "/" in cfg.command
            else shutil.which(cfg.command) is not None
        )
        if not cmd_exists:
            info["status"] = "unreachable"
            info["connectionStatus"] = "unreachable"
            info["detail"] = f"Command not found: {cfg.command}"
            return None, info
        if cfg.cwd is not None and not cfg.cwd.exists():
            info["status"] = "unreachable"
            info["connectionStatus"] = "unreachable"
            info["detail"] = f"Working directory not found: {cfg.cwd}"
            return None, info
        env_overrides, missing_env = resolve_secret_mapping(cfg.env, res)
        if missing_env:
            info["status"] = "auth_required"
            info["connectionStatus"] = "auth_required"
            info["missingEnv"] = missing_env
            info["detail"] = f"Set {', '.join(missing_env)} to activate {slug}"
            return None, info
        merged_env = {**os.environ, **env_overrides} if env_overrides else None
        transport = StdioTransport(
            command=cfg.command,
            args=list(cfg.args),
            env=merged_env,
            cwd=str(cfg.cwd) if cfg.cwd is not None else None,
            keep_alive=True,
        )

    proxy = create_proxy(transport, name=slug)
    proxy.add_middleware(MLflowTracingMiddleware(settings, slug))
    info["status"] = "proxy"
    info["connectionStatus"] = "configured"
    return proxy, info


async def probe_upstream_proxy(
    proxy: FastMCP,
    *,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """List tools through an instantiated upstream proxy to check live reachability."""
    try:
        tools = await asyncio.wait_for(proxy.list_tools(), timeout=timeout_s)
        tool_names = [getattr(t, "name", "") for t in tools]
        return {
            "reachable": True,
            "connectionStatus": "connected",
            "toolCount": len(tools),
            "tools": tool_names,
            "sampleTools": tool_names[:5],
        }
    except Exception as exc:
        return {
            "reachable": False,
            "connectionStatus": "unreachable",
            "toolCount": 0,
            "error": str(exc)[:240],
        }


async def probe_all_upstreams(settings: MCPStackSettings) -> list[dict[str, Any]]:
    """Build and probe all configured upstream_servers without starting the full gateway."""
    results: list[dict[str, Any]] = []
    for name, cfg in settings.gateway.upstream_servers.items():
        proxy, meta = build_upstream_proxy(name, cfg, settings)
        if proxy is None:
            results.append(meta)
            continue
        # Probe backend transport directly when gateway lifespan is not active
        if cfg.transport == "http" and cfg.url:
            headers, _ = resolve_secret_mapping(cfg.headers, SecretResolver(settings.secrets))
            transport: StreamableHttpTransport | StdioTransport = StreamableHttpTransport(
                cfg.url, headers=headers or None
            )
        else:
            env_ovr, _ = resolve_secret_mapping(cfg.env, SecretResolver(settings.secrets))
            transport = StdioTransport(
                command=cfg.command or "",
                args=list(cfg.args),
                env={**os.environ, **env_ovr} if env_ovr else None,
                cwd=str(cfg.cwd) if cfg.cwd is not None else None,
            )
        try:
            async with Client(transport) as cli:
                tools = await asyncio.wait_for(cli.list_tools(), timeout=cfg.timeout_s)
            meta["connectionStatus"] = "connected"
            meta["toolCount"] = len(tools)
            meta["sampleTools"] = [getattr(t, "name", "") for t in tools[:5]]
        except Exception as exc:
            meta["connectionStatus"] = "unreachable"
            meta["toolCount"] = 0
            meta["error"] = str(exc)[:240]
        results.append(meta)
    return results
