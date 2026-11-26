"""Build, curate, and probe federated external HTTP/stdio MCP proxies for the Gateway."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.server import create_proxy
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import Tool, ToolResult
from pydantic import SecretStr

from mcp_stack.core.config import MCPStackSettings, UpstreamServerConfig
from mcp_stack.core.secrets import SecretResolutionError, SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware

_PREFIXED_ENV_RE = re.compile(r"^(.*?)\benv:([A-Za-z_][A-Za-z0-9_]*)(.*)$")


def _slug_for(name: str) -> str:
    return name.strip().replace("_", "-").lower()


def is_tool_allowed(
    tool_name: str,
    allow_tools: Sequence[str],
    deny_tools: Sequence[str],
) -> bool:
    """Return True if `tool_name` passes upstream allow/deny fnmatchcase globs."""
    clean_deny = [p.strip() for p in deny_tools if p and p.strip()]
    if any(fnmatch.fnmatchcase(tool_name, pat) for pat in clean_deny):
        return False
    clean_allow = [p.strip() for p in allow_tools if p and p.strip()]
    if not clean_allow:
        return True
    return any(fnmatch.fnmatchcase(tool_name, pat) for pat in clean_allow)


def filter_tool_names(
    names: Sequence[str],
    allow_tools: Sequence[str],
    deny_tools: Sequence[str],
) -> list[str]:
    """Filter a list of tool names using allow/deny glob patterns."""
    return [name for name in names if is_tool_allowed(name, allow_tools, deny_tools)]


class ToolCurationMiddleware(Middleware):
    """Hide denied/non-allowlisted upstream tools from discovery and execution."""

    def __init__(
        self,
        server_slug: str,
        allow_tools: Sequence[str],
        deny_tools: Sequence[str],
    ) -> None:
        self._slug = server_slug
        self._allow = [p.strip() for p in allow_tools if p and p.strip()]
        self._deny = [p.strip() for p in deny_tools if p and p.strip()]

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        return [
            t
            for t in tools
            if is_tool_allowed(getattr(t, "name", ""), self._allow, self._deny)
        ]

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        tool_name = str(getattr(context.message, "name", "") or "")
        if not is_tool_allowed(tool_name, self._allow, self._deny):
            raise ToolError(
                f"[TOOL_CURATED_OUT] Tool '{tool_name}' is excluded by curation policy "
                f"on upstream '{self._slug}'"
            )
        return await call_next(context)


def resolve_secret_mapping_with_reasons(
    mapping: dict[str, SecretStr],
    resolver: SecretResolver,
) -> tuple[dict[str, str], list[str], list[tuple[str, str]]]:
    """Resolve SecretStr mapping values returning `(resolved, missing_items, reasons)`."""
    resolved: dict[str, str] = {}
    missing_items: list[str] = []
    reasons: list[tuple[str, str]] = []
    for key, secret in mapping.items():
        raw = secret.get_secret_value().strip()
        if raw.startswith(("env:", "op://")):
            try:
                val = resolver.resolve(secret)
            except SecretResolutionError as exc:
                missing_items.append(raw)
                reasons.append((exc.reason_code, str(exc)))
                continue
            if not val:
                ref_label = raw.removeprefix("env:").strip() if raw.startswith("env:") else raw
                missing_items.append(ref_label)
                reasons.append(("missing", f"Empty secret value for {ref_label}"))
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
                missing_items.append(op_ref)
                reasons.append((exc.reason_code, str(exc)))
                continue
            if not val:
                missing_items.append(op_ref)
                reasons.append(("empty_value", f"Empty 1Password secret for {op_ref}"))
                continue
            resolved[key] = f"{prefix}{val}"
            continue

        match = _PREFIXED_ENV_RE.match(raw)
        if match:
            prefix, var_name, suffix = match.groups()
            env_val = os.getenv(var_name, "").strip()
            if not env_val:
                missing_items.append(var_name)
                reasons.append(("env_missing", f"Environment variable '{var_name}' is not set"))
                continue
            resolved[key] = f"{prefix}{env_val}{suffix}"
            continue

        if raw:
            resolved[key] = raw
    return resolved, missing_items, reasons


def resolve_secret_mapping(
    mapping: dict[str, SecretStr],
    resolver: SecretResolver,
) -> tuple[dict[str, str], list[str]]:
    """Resolve SecretStr mapping values including `Bearer env:VAR` & `Bearer op://...`."""
    resolved, missing_items, _reasons = resolve_secret_mapping_with_reasons(mapping, resolver)
    return resolved, missing_items


def _format_auth_required_detail(
    slug: str,
    missing_items: list[str],
    reasons: list[tuple[str, str]],
) -> tuple[str, str]:
    if reasons:
        code, message = reasons[0]
        if code in {"timeout", "locked", "cli_missing", "provider_disabled", "vault_denied"}:
            return code, f"{message} (click Probe once resolved)"
        return code, f"{message} ({', '.join(missing_items)})"
    return "missing", f"Configure {', '.join(missing_items)} to activate {slug}"


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
        headers, missing_env, reasons = resolve_secret_mapping_with_reasons(cfg.headers, res)
        if missing_env:
            reason_code, detail = _format_auth_required_detail(slug, missing_env, reasons)
            info["status"] = "auth_required"
            info["connectionStatus"] = "auth_required"
            info["missingEnv"] = missing_env
            info["authReasonCode"] = reason_code
            info["detail"] = detail
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
        try:
            cmd_exists = (
                cmd_path.exists()
                if cmd_path.is_absolute() or "/" in cfg.command
                else shutil.which(cfg.command) is not None
            )
        except OSError:
            cmd_exists = False
        if not cmd_exists:
            info["status"] = "unreachable"
            info["connectionStatus"] = "unreachable"
            info["detail"] = f"Command not accessible: {cfg.command}"
            return None, info
        try:
            cwd_ok = cfg.cwd is None or cfg.cwd.exists()
        except OSError:
            cwd_ok = False
        if not cwd_ok:
            info["status"] = "unreachable"
            info["connectionStatus"] = "unreachable"
            info["detail"] = f"Working directory not accessible: {cfg.cwd}"
            return None, info
        env_overrides, missing_env, reasons = resolve_secret_mapping_with_reasons(cfg.env, res)
        if missing_env:
            reason_code, detail = _format_auth_required_detail(slug, missing_env, reasons)
            info["status"] = "auth_required"
            info["connectionStatus"] = "auth_required"
            info["missingEnv"] = missing_env
            info["authReasonCode"] = reason_code
            info["detail"] = detail
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
    if cfg.allow_tools or cfg.deny_tools:
        proxy.add_middleware(ToolCurationMiddleware(slug, cfg.allow_tools, cfg.deny_tools))
    proxy.add_middleware(MLflowTracingMiddleware(settings, slug))
    info["status"] = "proxy"
    info["connectionStatus"] = "configured"
    return proxy, info


async def probe_upstream_proxy(
    proxy: FastMCP,
    *,
    timeout_s: float = 5.0,
    allow_tools: Sequence[str] = (),
    deny_tools: Sequence[str] = (),
) -> dict[str, Any]:
    """List tools through an instantiated upstream proxy and compute curated counts."""
    try:
        try:
            coro = proxy.list_tools(run_middleware=False)
        except TypeError:
            coro = proxy.list_tools()
        raw_tools = await asyncio.wait_for(coro, timeout=timeout_s)
        raw_names = [getattr(t, "name", "") for t in raw_tools]
        exposed_names = filter_tool_names(raw_names, allow_tools, deny_tools)
        return {
            "reachable": True,
            "connectionStatus": "connected",
            "rawToolCount": len(raw_names),
            "exposedToolCount": len(exposed_names),
            "filteredOutCount": max(0, len(raw_names) - len(exposed_names)),
            "toolCount": len(exposed_names),
            "tools": exposed_names,
            "sampleTools": exposed_names[:5],
        }
    except Exception as exc:
        return {
            "reachable": False,
            "connectionStatus": "unreachable",
            "rawToolCount": 0,
            "exposedToolCount": 0,
            "filteredOutCount": 0,
            "toolCount": 0,
            "error": str(exc)[:240],
        }


async def probe_all_upstreams(settings: MCPStackSettings) -> list[dict[str, Any]]:
    """Build and probe all configured upstream_servers without starting the full gateway."""
    results: list[dict[str, Any]] = []
    resolver = SecretResolver(settings.secrets)
    for name, cfg in settings.gateway.upstream_servers.items():
        proxy, meta = build_upstream_proxy(name, cfg, settings, resolver=resolver)
        if proxy is None:
            results.append(meta)
            continue
        if cfg.transport == "http" and cfg.url:
            headers, _ = resolve_secret_mapping(cfg.headers, resolver)
            transport: StreamableHttpTransport | StdioTransport = StreamableHttpTransport(
                cfg.url, headers=headers or None
            )
        else:
            env_ovr, _ = resolve_secret_mapping(cfg.env, resolver)
            transport = StdioTransport(
                command=cfg.command or "",
                args=list(cfg.args),
                env={**os.environ, **env_ovr} if env_ovr else None,
                cwd=str(cfg.cwd) if cfg.cwd is not None else None,
            )
        try:
            async with Client(transport) as cli:
                tools = await asyncio.wait_for(cli.list_tools(), timeout=cfg.timeout_s)
            raw_names = [getattr(t, "name", "") for t in tools]
            exposed = filter_tool_names(raw_names, cfg.allow_tools, cfg.deny_tools)
            meta["connectionStatus"] = "connected"
            meta["rawToolCount"] = len(raw_names)
            meta["exposedToolCount"] = len(exposed)
            meta["filteredOutCount"] = max(0, len(raw_names) - len(exposed))
            meta["toolCount"] = len(exposed)
            meta["sampleTools"] = exposed[:5]
        except Exception as exc:
            meta["connectionStatus"] = "unreachable"
            meta["toolCount"] = 0
            meta["error"] = str(exc)[:240]
        results.append(meta)
    return results
