"""Shared runtime state and upstream/profile lifecycle helpers for Gateway HTTP routers."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from mcp_stack.core.auth import LoginNonceStore
from mcp_stack.core.config import (
    MCPStackSettings,
    ProfileToolFilter,
    UpstreamServerConfig,
    save_local_profiles,
    save_local_upstreams,
    serialize_upstream_config,
)
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.gateway.activity import ActivityBus
from mcp_stack.gateway.presets import PresetStore
from mcp_stack.gateway.upstreams import (
    ToolCurationMiddleware,
    build_upstream_proxy,
    is_tool_allowed,
    probe_upstream_proxy,
)
from mcp_stack.servers.gateway_meta import MLflowPromptRegistryProvider
from mcp_stack.servers.unity_catalog import UCClientAdapter

if TYPE_CHECKING:
    from fastapi import FastAPI

BUILTIN_PROFILES = frozenset({"discover", "core", "data", "ops", "macos"})
PROFILE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def estimate_tool_schema_tokens(tools: Sequence[dict[str, Any]]) -> int:
    """Estimate approximate LLM prompt token footprint (~4 chars/token) for serialized tools."""
    if not tools:
        return 0
    return sum(max(1, len(json.dumps(tool, default=str)) // 4) for tool in tools)


def slug_for(server_key: str) -> str:
    """Normalize an internal server key into its URL slug."""
    return server_key.replace("_", "-")


@dataclass
class ProfileLifespanRunner:
    """Own one profile ASGI lifespan inside its own dedicated asyncio task."""

    p_http: Any
    app: FastAPI
    _stop: asyncio.Event = field(default_factory=asyncio.Event)
    _ready: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async def _runner() -> None:
            async with self.p_http.lifespan(self.app):
                self._ready.set()
                await self._stop.wait()

        self._task = asyncio.create_task(_runner())
        await self._ready.wait()

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with suppress(Exception):
                await self._task


@dataclass
class GatewayRuntimeState:
    """Mutable runtime state shared between gateway lifespan and modular FastAPI routers."""

    settings: MCPStackSettings
    logger: Any
    servers: dict[str, FastMCP]
    uc_adapter: UCClientAdapter | None
    upstream_proxy: FastMCP | None
    federated_proxies: dict[str, FastMCP]
    federated_meta: dict[str, dict[str, Any]]
    federated_cfg_map: dict[str, UpstreamServerConfig]
    server_inventory: list[dict[str, Any]]
    profile_inventory: list[dict[str, Any]]
    profile_apps: dict[str, FastMCP]
    profile_http: dict[str, Any]
    meta_prompt_provider: MLflowPromptRegistryProvider
    preset_store: PresetStore
    login_nonces: LoginNonceStore
    upstream_composed: bool = False
    activity_bus: ActivityBus = field(default_factory=ActivityBus)
    secret_resolver: SecretResolver = field(init=False)
    profile_runners: dict[str, ProfileLifespanRunner] = field(default_factory=dict)
    app_ref: FastAPI | None = None
    mlflow_experiment_id: str | None = None

    def __post_init__(self) -> None:
        self.secret_resolver = SecretResolver(self.settings.secrets)

    def local_upstreams_path(self) -> Path:
        return Path(os.getenv("MCP_LOCAL_CONFIG_PATH") or "config/gateway.local.yaml")

    def target_server_instances(self) -> dict[str, FastMCP]:
        instances: dict[str, FastMCP] = {slug_for(k): s for k, s in self.servers.items()}
        if self.upstream_proxy is not None:
            instances["mlflow-upstream"] = self.upstream_proxy
        for fed_slug, fed_proxy in self.federated_proxies.items():
            instances[fed_slug] = fed_proxy
        return instances

    def meta_state_snapshot(self) -> dict[str, Any]:
        return {
            "servers": self.server_inventory,
            "profiles": self.profile_inventory,
            "server_instances": self.target_server_instances(),
            "federated_configs": self.federated_cfg_map,
            "activity_bus": self.activity_bus,
            "settings": self.settings,
        }

    async def collect_tools_for_server(
        self,
        slug: str,
        srv: FastMCP,
        *,
        timeout_s: float = 2.0,
    ) -> list[dict[str, Any]]:
        try:
            items = await asyncio.wait_for(srv.list_tools(), timeout=timeout_s)
        except Exception as exc:
            self.logger.debug("Tool inspection skipped for server", server=slug, error=str(exc))
            return []
        collected: list[dict[str, Any]] = []
        for tool in items:
            params = getattr(tool, "parameters", None)
            if not isinstance(params, dict):
                params = {}
            collected.append(
                {
                    "name": getattr(tool, "name", ""),
                    "server": slug,
                    "description": (getattr(tool, "description", None) or "").strip(),
                    "parameters": params,
                }
            )
        return collected

    def serialize_upstream_item(
        self,
        raw_key: str,
        cfg: UpstreamServerConfig,
    ) -> dict[str, Any]:
        slug = slug_for(raw_key)
        meta = dict(self.federated_meta.get(slug) or {})
        safe_cfg = serialize_upstream_config(cfg)
        tool_count = int(meta.get("exposedToolCount", meta.get("toolCount", 0)) or 0)
        raw_count = int(meta.get("rawToolCount", tool_count) or tool_count)
        return {
            **safe_cfg,
            "slug": slug,
            "route": f"/servers/{slug}/mcp",
            "connectionStatus": meta.get(
                "connectionStatus", "disabled" if not cfg.enabled else "configured"
            ),
            "toolCount": tool_count,
            "rawToolCount": raw_count,
            "exposedToolCount": tool_count,
            "filteredOutCount": int(meta.get("filteredOutCount", max(0, raw_count - tool_count))),
            "sampleTools": meta.get("sampleTools", []),
            "missingEnv": meta.get("missingEnv", []),
            "authReasonCode": meta.get("authReasonCode"),
            "detail": meta.get("detail") or meta.get("error"),
        }

    async def sync_upstream_runtime(
        self,
        slug: str,
        cfg: UpstreamServerConfig | None,
    ) -> dict[str, Any]:
        upstreams = self.settings.gateway.upstream_servers
        target_key = next(
            (k for k in list(upstreams.keys()) if slug_for(k) == slug),
            slug,
        )
        if cfg is None:
            upstreams.pop(target_key, None)
            self.federated_proxies.pop(slug, None)
            self.federated_meta.pop(slug, None)
            self.federated_cfg_map.pop(slug, None)
            self.server_inventory[:] = [
                s
                for s in self.server_inventory
                if not (s.get("external") and s.get("slug") == slug)
            ]
            save_local_upstreams(self.local_upstreams_path(), upstreams)
            self.activity_bus.record(
                "upstream_probe", status="ok", server=slug, summary="Deleted upstream"
            )
            return {"deleted": slug}

        if target_key != slug and target_key in upstreams:
            upstreams.pop(target_key, None)
        upstreams[slug] = cfg
        save_local_upstreams(self.local_upstreams_path(), upstreams)

        proxy_srv, up_info = build_upstream_proxy(
            slug, cfg, self.settings, resolver=self.secret_resolver
        )
        self.federated_cfg_map[slug] = cfg
        if proxy_srv is not None:
            self.federated_proxies[slug] = proxy_srv
            probe_res = await probe_upstream_proxy(
                proxy_srv,
                timeout_s=cfg.timeout_s,
                allow_tools=cfg.allow_tools,
                deny_tools=cfg.deny_tools,
            )
            up_info["connectionStatus"] = probe_res["connectionStatus"]
            up_info["toolCount"] = probe_res.get("toolCount", 0)
            up_info["rawToolCount"] = probe_res.get("rawToolCount", up_info["toolCount"])
            up_info["exposedToolCount"] = probe_res.get("exposedToolCount", up_info["toolCount"])
            up_info["filteredOutCount"] = probe_res.get("filteredOutCount", 0)
            up_info["sampleTools"] = probe_res.get("sampleTools", [])
            if probe_res.get("error"):
                up_info["error"] = probe_res["error"]
            self.activity_bus.record(
                "upstream_probe",
                status="ok" if probe_res.get("reachable") else "error",
                server=slug,
                summary=(
                    f"{slug} -> {up_info['connectionStatus']} "
                    f"({up_info['exposedToolCount']}/{up_info['rawToolCount']} tools)"
                ),
            )
        else:
            self.federated_proxies.pop(slug, None)
            self.activity_bus.record(
                "upstream_probe",
                status="warn",
                server=slug,
                summary=str(up_info.get("detail") or up_info.get("connectionStatus")),
            )

        self.federated_meta[slug] = up_info
        existing_idx = next(
            (
                idx
                for idx, s in enumerate(self.server_inventory)
                if s.get("external") and s.get("slug") == slug
            ),
            None,
        )
        if existing_idx is not None:
            self.server_inventory[existing_idx] = up_info
        else:
            self.server_inventory.append(up_info)
        return self.serialize_upstream_item(slug, cfg)

    def get_profile_tool_filter(self, clean_profile: str) -> tuple[list[str], list[str]]:
        filt = self.settings.gateway.profile_tool_filters.get(clean_profile)
        if filt is None:
            return [], []
        return list(filt.allow_tools), list(filt.deny_tools)

    def _build_profile_bundle(
        self, clean_profile: str, raw_members: list[str]
    ) -> tuple[FastMCP, Any, dict[str, Any]]:
        p_mcp = FastMCP(f"mcp-profile-{clean_profile}")
        allow_tools, deny_tools = self.get_profile_tool_filter(clean_profile)
        if allow_tools or deny_tools:
            p_mcp.add_middleware(ToolCurationMiddleware(clean_profile, allow_tools, deny_tools))
        resolved_slugs: list[str] = []
        wants_upstream = False
        for member in raw_members:
            norm = member.strip().replace("-", "_")
            fed_slug_cand = member.strip().replace("_", "-").lower()
            if norm == "mlflow_upstream":
                if self.upstream_proxy is not None:
                    wants_upstream = True
                    if self.upstream_composed:
                        p_mcp.mount(self.upstream_proxy)
                continue
            if norm in self.servers:
                p_mcp.mount(self.servers[norm])
                resolved_slugs.append(slug_for(norm))
            elif fed_slug_cand in self.federated_proxies:
                fed_status = self.federated_meta.get(fed_slug_cand, {}).get("connectionStatus")
                if fed_status == "connected":
                    p_mcp.mount(self.federated_proxies[fed_slug_cand])
                resolved_slugs.append(fed_slug_cand)
        p_http = p_mcp.http_app(path="/")
        inv_entry = {
            "name": clean_profile,
            "route": f"/profiles/{clean_profile}/mcp",
            "servers": resolved_slugs,
            "includesUpstreamMcp": wants_upstream,
            "builtin": clean_profile in BUILTIN_PROFILES,
            "allowTools": allow_tools,
            "denyTools": deny_tools,
        }
        return p_mcp, p_http, inv_entry

    async def upsert_profile(
        self,
        name: str,
        members: list[str],
        *,
        allow_tools: Sequence[str] | None = None,
        deny_tools: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Create or update a gateway profile live and persist to gateway.local.yaml."""
        clean = name.strip().lower()
        if not PROFILE_SLUG_RE.match(clean):
            raise ValueError(
                "Profile name must be lowercase alphanumeric/hyphen/underscore (1-48 chars)"
            )
        if clean == "discover":
            raise ValueError("Built-in 'discover' profile cannot be modified")
        normalized_members = [str(m).strip().replace("_", "-") for m in members if str(m).strip()]
        if not normalized_members:
            raise ValueError("Profile must include at least one server")

        self.settings.gateway.profiles[clean] = normalized_members
        if allow_tools is not None or deny_tools is not None:
            clean_allow = [str(p).strip() for p in (allow_tools or []) if str(p).strip()]
            clean_deny = [str(p).strip() for p in (deny_tools or []) if str(p).strip()]
            if clean_allow or clean_deny:
                self.settings.gateway.profile_tool_filters[clean] = ProfileToolFilter(
                    allow_tools=clean_allow,
                    deny_tools=clean_deny,
                )
            else:
                self.settings.gateway.profile_tool_filters.pop(clean, None)

        save_local_profiles(
            self.local_upstreams_path(),
            self.settings.gateway.profiles,
            self.settings.gateway.profile_tool_filters,
        )

        old_runner = self.profile_runners.pop(clean, None)
        if old_runner is not None:
            await old_runner.stop()

        p_mcp, p_http, inv_entry = self._build_profile_bundle(clean, normalized_members)
        self.profile_apps[clean] = p_mcp
        self.profile_http[clean] = p_http
        if self.app_ref is not None:
            runner = ProfileLifespanRunner(p_http=p_http, app=self.app_ref)
            await runner.start()
            self.profile_runners[clean] = runner

        existing_idx = next(
            (i for i, p in enumerate(self.profile_inventory) if p.get("name") == clean),
            None,
        )
        if existing_idx is not None:
            self.profile_inventory[existing_idx] = inv_entry
        else:
            self.profile_inventory.append(inv_entry)

        self.activity_bus.record(
            "profile_update",
            status="ok",
            summary=f"Saved profile '{clean}' ({len(inv_entry['servers'])} servers)",
        )
        return inv_entry

    async def delete_profile(self, name: str) -> dict[str, Any]:
        """Delete a custom profile (rejecting built-in profiles)."""
        clean = name.strip().lower()
        if clean in BUILTIN_PROFILES:
            raise ValueError(f"Built-in profile '{clean}' cannot be deleted")
        if clean not in self.settings.gateway.profiles and clean not in self.profile_apps:
            raise KeyError(f"Unknown profile '{clean}'")

        self.settings.gateway.profiles.pop(clean, None)
        self.settings.gateway.profile_tool_filters.pop(clean, None)
        save_local_profiles(
            self.local_upstreams_path(),
            self.settings.gateway.profiles,
            self.settings.gateway.profile_tool_filters,
        )

        old_runner = self.profile_runners.pop(clean, None)
        if old_runner is not None:
            await old_runner.stop()
        self.profile_apps.pop(clean, None)
        self.profile_http.pop(clean, None)
        self.profile_inventory[:] = [p for p in self.profile_inventory if p.get("name") != clean]
        self.activity_bus.record(
            "profile_update", status="ok", summary=f"Deleted profile '{clean}'"
        )
        return {"deleted": clean}

    async def gather_tools_by_server(self) -> dict[str, list[dict[str, Any]]]:
        target_slugs = self.target_server_instances()

        async def _gather_one(slug: str, srv: FastMCP) -> tuple[str, list[dict[str, Any]]]:
            t_out = (
                self.federated_cfg_map[slug].timeout_s
                if slug in self.federated_cfg_map
                else 2.0
            )
            return slug, await self.collect_tools_for_server(slug, srv, timeout_s=t_out)

        gathered = await asyncio.gather(
            *(_gather_one(slug, srv) for slug, srv in target_slugs.items())
        )
        return dict(gathered)

    def tools_for_profile(
        self,
        profile_entry: dict[str, Any],
        per_server_tools: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        profile_name = str(profile_entry.get("name") or "")
        allow_tools, deny_tools = self.get_profile_tool_filter(profile_name)
        allowed_servers = list(profile_entry.get("servers") or [])
        if profile_entry.get("includesUpstreamMcp") and "mlflow-upstream" not in allowed_servers:
            allowed_servers.append("mlflow-upstream")
        out: list[dict[str, Any]] = []
        for srv_slug in allowed_servers:
            for item in per_server_tools.get(srv_slug, []):
                if is_tool_allowed(str(item.get("name") or ""), allow_tools, deny_tools):
                    out.append(item)
        return out
