"""Gateway-native meta-tools, MCP Resources, MLflow Prompt bridge, and gated admin tools."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.prompts import Message, Prompt, PromptArgument, PromptResult
from fastmcp.server.providers import Provider
from fastmcp.utilities.versions import VersionSpec
from pydantic import SecretStr

from mcp_stack import __version__
from mcp_stack.client_configs import generate_client_configs
from mcp_stack.core.auth import caller_client_policy_var, is_server_allowed
from mcp_stack.core.config import (
    MCPStackSettings,
    UpstreamServerConfig,
    save_local_upstreams,
    validate_upstream_secret_refs,
)
from mcp_stack.core.tracing import last_trace_id_var
from mcp_stack.evals import (
    compare_eval_runs,
    list_eval_datasets,
    run_golden_benchmark,
)
from mcp_stack.gateway.presets import PresetStore
from mcp_stack.gateway.upstreams import build_upstream_proxy, probe_upstream_proxy
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint
from mcp_stack.skill_registry import get_mlflow_skill_detail, list_mlflow_skills
from mcp_stack.watchdog import (
    DEFAULT_STATE_PATH,
    _load_state,
    run_watchdog_once,
)

_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")
_PROMPT_CACHE_TTL_S = 30.0


def _extract_template_vars(template: str) -> list[str]:
    seen: list[str] = []
    for match in _TEMPLATE_VAR_RE.findall(template):
        if match not in seen:
            seen.append(match)
    return seen


def _render_mustache_template(template: str, arguments: dict[str, Any] | None) -> str:
    args = arguments or {}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in args and args[key] is not None:
            return str(args[key])
        return match.group(0)

    return _TEMPLATE_VAR_RE.sub(_replace, template)


class MLflowBridgedPrompt(Prompt):
    """MCP Prompt backed by an MLflow 3.x Prompt Registry entry."""

    template: str = ""
    commit_message: str | None = None
    prompt_aliases: list[str] = []

    async def render(self, arguments: dict[str, Any] | None = None) -> PromptResult:
        rendered = _render_mustache_template(self.template, arguments)
        return PromptResult(
            messages=[Message(rendered, role="user")],
            description=self.description,
            meta=self.meta,
        )


class MLflowPromptRegistryProvider(Provider):
    """Fail-open FastMCP Provider exposing MLflow Prompt Registry as native MCP Prompts."""

    def __init__(
        self,
        settings: MCPStackSettings,
        *,
        ttl_s: float = _PROMPT_CACHE_TTL_S,
        mlflow_module: Any = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._ttl_s = ttl_s
        self._mlflow_module = mlflow_module
        self._cached_at = 0.0
        self._cached_prompts: list[Prompt] = []

    def _get_mlflow_pair(self) -> tuple[Any, Any]:
        if self._mlflow_module is not None:
            return self._mlflow_module, getattr(self._mlflow_module, "genai", None)
        import mlflow
        import mlflow.genai

        return mlflow, mlflow.genai

    def _fetch_prompts_sync(self) -> list[Prompt]:
        mlflow_mod, genai_mod = self._get_mlflow_pair()
        tracking_uri = self._settings.mlflow.tracking_uri
        mlflow_mod.set_tracking_uri(tracking_uri)
        search_fn = getattr(genai_mod, "search_prompts", None)
        load_fn = getattr(genai_mod, "load_prompt", None)
        if not callable(search_fn) or not callable(load_fn):
            return []

        summaries = search_fn(max_results=50) or []
        prompts: list[Prompt] = []
        for summary in summaries:
            p_name = str(getattr(summary, "name", "") or "").strip()
            if not p_name:
                continue
            version_num = getattr(summary, "latest_version", None)
            aliases = list(getattr(summary, "aliases", []) or [])
            ref = (
                f"prompts:/{p_name}/{version_num}"
                if version_num is not None
                else f"prompts:/{p_name}@latest"
            )
            template = ""
            commit_msg: str | None = None
            loaded_ver = str(version_num) if version_num is not None else "1"
            try:
                loaded = load_fn(ref)
                template = str(getattr(loaded, "template", "") or "")
                commit_msg = getattr(loaded, "commit_message", None)
                if getattr(loaded, "version", None) is not None:
                    loaded_ver = str(loaded.version)
            except Exception:
                continue

            var_names = _extract_template_vars(template)
            args = [
                PromptArgument(
                    name=v,
                    description=f"Template variable '{{{{{v}}}}}'",
                    required=False,
                )
                for v in var_names
            ]
            alias_label = f" ({', '.join('@' + str(a) for a in aliases)})" if aliases else ""
            desc = (
                f"MLflow prompt '{p_name}' v{loaded_ver}{alias_label}"
                + (f" — {commit_msg}" if commit_msg else "")
            )
            prompts.append(
                MLflowBridgedPrompt(
                    name=p_name,
                    version=loaded_ver,
                    title=p_name,
                    description=desc,
                    arguments=args,
                    tags={"mlflow-prompt"},
                    meta={
                        "mlflow": {
                            "name": p_name,
                            "version": loaded_ver,
                            "aliases": [str(a) for a in aliases],
                        }
                    },
                    template=template,
                    commit_message=str(commit_msg) if commit_msg else None,
                    prompt_aliases=[str(a) for a in aliases],
                )
            )
        return prompts

    async def _list_prompts(self) -> Sequence[Prompt]:
        now = time.monotonic()
        if self._cached_prompts and (now - self._cached_at) < self._ttl_s:
            return self._cached_prompts
        try:
            prompts = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_prompts_sync),
                timeout=4.0,
            )
            self._cached_prompts = prompts
            self._cached_at = time.monotonic()
            return prompts
        except Exception:
            return self._cached_prompts

    async def _get_prompt(self, name: str, version: VersionSpec | None = None) -> Prompt | None:
        prompts = await self._list_prompts()
        matching = [p for p in prompts if p.name == name]
        if version is not None:
            matching = [p for p in matching if version.matches(p.version)]
        return matching[0] if matching else None

    def invalidate_cache(self) -> None:
        self._cached_at = 0.0
        self._cached_prompts = []


def _local_config_path() -> Path:
    return Path(os.getenv("MCP_LOCAL_CONFIG_PATH") or "config/gateway.local.yaml")


def _require_admin_tools(settings: MCPStackSettings) -> None:
    if not settings.gateway.admin_tools_enabled:
        raise ToolError(
            "[POLICY_REFUSAL] Gateway admin tools are disabled by policy. "
            "Set MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true to enable admin mutations."
        )


def create_gateway_meta_server(
    settings: MCPStackSettings,
    state_provider: Callable[[], dict[str, Any]],
    *,
    prompt_provider: MLflowPromptRegistryProvider | None = None,
) -> FastMCP:
    """Create the gateway-native meta-server exposing discovery, resources, and bridged prompts."""
    mcp = FastMCP(
        "mcp-workshop-gateway-meta",
        instructions=(
            "Gateway discovery and observability server. Prefer calling gateway_search_tools, "
            "gateway_list_servers, or reading gateway://resources before enumerating every tool."
        ),
    )

    bridge = prompt_provider or MLflowPromptRegistryProvider(settings)
    mcp.add_provider(bridge)

    async def _collect_ready_status() -> dict[str, Any]:
        checks: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                r = await client.get(
                    f"{settings.mlflow.tracking_uri.rstrip('/')}/api/2.0/mlflow/experiments/search",
                    params={"max_results": 1},
                )
                checks["mlflow_tracking"] = {
                    "healthy": r.status_code == 200,
                    "status_code": r.status_code,
                    "url": settings.mlflow.tracking_uri,
                }
            except Exception as exc:
                checks["mlflow_tracking"] = {
                    "healthy": False,
                    "url": settings.mlflow.tracking_uri,
                    "error": str(exc),
                }
            try:
                r = await client.get(
                    f"{settings.unity_catalog.effective_api_base}/catalogs",
                    params={"max_results": 1},
                )
                checks["unity_catalog"] = {
                    "healthy": r.status_code == 200,
                    "status_code": r.status_code,
                    "url": settings.unity_catalog.effective_api_base,
                }
            except Exception as exc:
                checks["unity_catalog"] = {
                    "healthy": False,
                    "url": settings.unity_catalog.effective_api_base,
                    "error": str(exc),
                }
        checks["mlflow_mcp_upstream"] = await probe_mcp_http_endpoint(
            settings.mlflow.mcp_url, timeout=2.0
        )
        all_ok = all(c.get("healthy", c.get("reachable", False)) for c in checks.values())
        state = _load_state(DEFAULT_STATE_PATH)
        return {
            "status": "ready" if all_ok else "degraded",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
            "watchdog": state,
        }

    @mcp.tool(
        name="gateway_health",
        description=(
            "Return live gateway version, dependency readiness (MLflow, Unity Catalog, "
            "mlflow[mcp]), and watchdog/eval regression status."
        ),
    )
    async def gateway_health() -> dict[str, Any]:
        snapshot = await _collect_ready_status()
        gw_state = state_provider()
        servers = gw_state.get("servers", [])
        connected = sum(
            1
            for s in servers
            if s.get("connectionStatus", "connected") in {"connected", "configured"}
        )
        snapshot["serverSummary"] = {
            "total": len(servers),
            "healthy": connected,
            "profiles": len(gw_state.get("profiles", [])),
        }
        return snapshot

    @mcp.tool(
        name="gateway_list_servers",
        description=(
            "List all mounted built-in and federated external MCP servers with transport, "
            "connectionStatus, governance, route, and optional tool names."
        ),
    )
    async def gateway_list_servers(include_tools: bool = False) -> dict[str, Any]:
        gw_state = state_provider()
        servers = [dict(s) for s in gw_state.get("servers", [])]
        instances: dict[str, FastMCP] = gw_state.get("server_instances", {})
        if include_tools:
            for item in servers:
                slug = str(item.get("slug", ""))
                srv_obj = instances.get(slug)
                if srv_obj is None:
                    item["tools"] = []
                    continue
                try:
                    tools = await asyncio.wait_for(srv_obj.list_tools(), timeout=2.5)
                    item["tools"] = sorted(str(getattr(t, "name", "")) for t in tools)
                    item["toolCount"] = len(item["tools"])
                except Exception as exc:
                    item["tools"] = []
                    item["toolError"] = str(exc)
        return {"composedRoute": "/mcp", "servers": servers}

    @mcp.tool(
        name="gateway_search_tools",
        description=(
            "Search across live tools on mounted built-in and federated MCP servers by keyword, "
            "returning exact server slug, tool name, MCP route, summary, and required parameters."
        ),
    )
    async def gateway_search_tools(
        query: str,
        server: str | None = None,
        profile: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        gw_state = state_provider()
        instances: dict[str, FastMCP] = gw_state.get("server_instances", {})
        profiles = gw_state.get("profiles", [])
        allowed_slugs: set[str] | None = None
        if profile:
            clean_p = profile.strip()
            prof_obj = next((p for p in profiles if p.get("name") == clean_p), None)
            if prof_obj is None:
                raise ToolError(
                    f"[PROFILE_NOT_FOUND] Unknown profile '{clean_p}'. "
                    "Call gateway_list_profiles() to see available profiles."
                )
            allowed_slugs = set(prof_obj.get("servers", []))
        if server:
            clean_s = server.strip().replace("_", "-").lower()
            allowed_slugs = (
                {clean_s}
                if allowed_slugs is None
                else (allowed_slugs & {clean_s})
            )

        tokens = [tok for tok in re.split(r"\W+", query.lower()) if tok]
        matches: list[tuple[int, dict[str, Any]]] = []
        target_slugs = [
            s for s in instances if allowed_slugs is None or s in allowed_slugs
        ]

        async def _scan(slug: str) -> list[tuple[int, dict[str, Any]]]:
            srv_obj = instances[slug]
            out: list[tuple[int, dict[str, Any]]] = []
            try:
                tools = await asyncio.wait_for(srv_obj.list_tools(), timeout=2.5)
            except Exception:
                return out
            for t in tools:
                t_name = str(getattr(t, "name", "") or "")
                t_desc = str(getattr(t, "description", "") or "")
                schema = getattr(t, "parameters", None) or {}
                props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                required = schema.get("required", []) if isinstance(schema, dict) else []
                haystack = " ".join(
                    [slug, t_name, t_desc, " ".join(str(k) for k in props)]
                ).lower()
                if tokens:
                    score = sum(
                        (3 if tok in t_name.lower() else 1)
                        for tok in tokens
                        if tok in haystack
                    )
                    if score == 0:
                        continue
                else:
                    score = 1
                summary = t_desc.strip().splitlines()[0][:200] if t_desc.strip() else ""
                out.append(
                    (
                        score,
                        {
                            "server": slug,
                            "tool": t_name,
                            "route": f"/servers/{slug}/mcp",
                            "summary": summary,
                            "requiredParams": list(required),
                            "params": sorted(str(k) for k in props),
                        },
                    )
                )
            return out

        nested = await asyncio.gather(*(_scan(s) for s in target_slugs))
        for chunk in nested:
            matches.extend(chunk)
        matches.sort(key=lambda item: (-item[0], item[1]["server"], item[1]["tool"]))
        capped = [item[1] for item in matches[: max(1, min(limit, 100))]]
        return {"query": query, "count": len(capped), "tools": capped}

    def _resolve_target_server(server: str) -> tuple[str, FastMCP]:
        slug = server.strip().replace("_", "-").lower()
        if settings.gateway.effective_auth_enabled:
            policy = caller_client_policy_var.get()
            if not is_server_allowed(policy, slug):
                client_label = policy.client_name if policy else "caller"
                raise ToolError(
                    f"[ACCESS_DENIED] Client '{client_label}' is not allowed to access '{slug}'."
                )
        gw_state = state_provider()
        instances: dict[str, FastMCP] = gw_state.get("server_instances", {})
        target = instances.get(slug)
        if target is None:
            raise ToolError(
                f"[SERVER_NOT_FOUND] Unknown or disconnected server '{slug}'. "
                "Call gateway_list_servers() to see live slugs."
            )
        return slug, target

    @mcp.tool(
        name="gateway_describe_tool",
        description=(
            "Return full JSON Schema parameters, description, and governance metadata for a "
            "single tool on any mounted built-in or federated server."
        ),
    )
    async def gateway_describe_tool(server: str, tool: str) -> dict[str, Any]:
        slug, target = _resolve_target_server(server)
        try:
            items = await asyncio.wait_for(target.list_tools(), timeout=4.0)
        except Exception as exc:
            raise ToolError(
                f"[SERVER_UNAVAILABLE] Failed to list tools on '{slug}': {exc}"
            ) from exc
        found = next((t for t in items if getattr(t, "name", "") == tool.strip()), None)
        if found is None:
            raise ToolError(
                f"[TOOL_NOT_FOUND] Tool '{tool}' not found (or curated out) on server '{slug}'."
            )
        gw_state = state_provider()
        srv_meta: dict[str, Any] = next(
            (s for s in gw_state.get("servers", []) if s.get("slug") == slug),
            {},
        )
        params = getattr(found, "parameters", None)
        return {
            "server": slug,
            "tool": getattr(found, "name", tool),
            "route": f"/servers/{slug}/mcp",
            "governance": srv_meta.get("governance"),
            "external": bool(srv_meta.get("external", False)),
            "description": (getattr(found, "description", None) or "").strip(),
            "parameters": params if isinstance(params, dict) else {},
        }

    @mcp.tool(
        name="gateway_call_tool",
        description=(
            "Progressive-disclosure proxy tool: dynamically invoke any curated tool across "
            "built-in and federated MCP servers while enforcing client ACLs and MLflow tracing."
        ),
    )
    async def gateway_call_tool(
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        slug, target = _resolve_target_server(server)
        clean_tool = tool.strip()
        try:
            items = await asyncio.wait_for(target.list_tools(), timeout=4.0)
        except Exception as exc:
            raise ToolError(f"[SERVER_UNAVAILABLE] Failed to inspect '{slug}': {exc}") from exc
        if not any(getattr(t, "name", "") == clean_tool for t in items):
            raise ToolError(
                f"[TOOL_NOT_FOUND] Tool '{clean_tool}' not found (or curated out) on '{slug}'."
            )

        gw_state = state_provider()
        activity_bus = gw_state.get("activity_bus")
        args_dict = dict(arguments or {})
        t0 = time.monotonic()
        trace_tok = last_trace_id_var.set(None)
        try:
            try:
                import mlflow

                mlflow.update_current_trace(tags={"mcp.via": "discover", "mcp.server": slug})
            except Exception:
                pass
            res = await asyncio.wait_for(
                target.call_tool(clean_tool, arguments=args_dict, run_middleware=True),
                timeout=30.0,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            trace_id = last_trace_id_var.get()
            blocks = getattr(res, "content", None) or []
            texts = [
                str(getattr(b, "text", b))
                for b in blocks
                if getattr(b, "text", None) is not None or getattr(b, "type", "") == "text"
            ]
            raw_text = "\n".join(texts)
            structured = getattr(res, "structured_content", None)
            parsed: Any = raw_text
            if raw_text:
                try:
                    parsed = json.loads(raw_text)
                except Exception:
                    parsed = raw_text[:20_000]
            elif structured is not None:
                parsed = structured
            if activity_bus is not None:
                activity_bus.record(
                    "tool_call",
                    status="ok",
                    server=slug,
                    tool=clean_tool,
                    duration_ms=elapsed_ms,
                    trace_id=trace_id,
                    summary=f"discover -> {slug}.{clean_tool} ({elapsed_ms} ms)",
                )
            return {
                "ok": True,
                "server": slug,
                "tool": clean_tool,
                "durationMs": elapsed_ms,
                "traceId": trace_id,
                "result": parsed,
            }
        except ToolError as exc:
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            if activity_bus is not None:
                activity_bus.record(
                    "tool_call",
                    status="error",
                    server=slug,
                    tool=clean_tool,
                    duration_ms=elapsed_ms,
                    trace_id=last_trace_id_var.get(),
                    summary=str(exc)[:160],
                )
            raise
        finally:
            last_trace_id_var.reset(trace_tok)

    @mcp.tool(
        name="gateway_search_skills",
        description=(
            "Search the MLflow 3.18 Skill Registry (returns capability status gracefully on <3.18)."
        ),
    )
    async def gateway_search_skills(
        query: str = "",
        status: str = "",
        organization: str = "",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            list_mlflow_skills,
            settings,
            query=query,
            status=status,
            organization=organization,
        )

    @mcp.tool(
        name="gateway_get_skill",
        description="Fetch versions, aliases, and SKILL.md content for an MLflow registered skill.",
    )
    async def gateway_get_skill(
        name: str,
        organization: str = "",
        version_or_alias: str | None = None,
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                get_mlflow_skill_detail,
                settings,
                name,
                organization=organization,
                version_or_alias=version_or_alias,
            )
        except Exception as exc:
            raise ToolError(f"[SKILL_UNAVAILABLE] {exc}") from exc

    @mcp.tool(
        name="gateway_list_datasets",
        description="List MLflow GenAI evaluation datasets for closed-loop quality workflows.",
    )
    async def gateway_list_datasets(experiment: str = "") -> dict[str, Any]:
        return await asyncio.to_thread(
            list_eval_datasets,
            settings,
            experiment_name=experiment.strip() or None,
        )

    @mcp.tool(
        name="gateway_compare_eval_runs",
        description="Compare two MLflow GenAI evaluation runs and return per-metric deltas.",
    )
    async def gateway_compare_eval_runs(run_a: str, run_b: str) -> dict[str, Any]:
        return await asyncio.to_thread(compare_eval_runs, settings, run_a, run_b)

    @mcp.tool(
        name="gateway_list_profiles",
        description=(
            "List curated MCP gateway profiles (discover, core, studio, data, ops, macos) "
            "with member servers, live tool counts, and Streamable HTTP URLs."
        ),
    )
    async def gateway_list_profiles() -> dict[str, Any]:
        gw_state = state_provider()
        base_http = f"http://{settings.gateway.host}:{settings.gateway.port}"
        instances: dict[str, FastMCP] = gw_state.get("server_instances", {})
        counts: dict[str, int] = {}
        for slug, srv_obj in instances.items():
            try:
                counts[slug] = len(await asyncio.wait_for(srv_obj.list_tools(), timeout=2.0))
            except Exception:
                counts[slug] = 0

        enriched: list[dict[str, Any]] = []
        for prof in gw_state.get("profiles", []):
            srv_list = list(prof.get("servers", []))
            enriched.append(
                {
                    **prof,
                    "url": f"{base_http}{prof.get('route', '')}",
                    "toolCount": sum(counts.get(s, 0) for s in srv_list),
                }
            )
        return {
            "defaultProfile": settings.gateway.default_client_profile,
            "fullUrl": f"{base_http}/mcp",
            "profiles": enriched,
        }

    @mcp.tool(
        name="gateway_recent_traces",
        description=(
            "Fetch compact recent MLflow trace summaries for self-debugging tool failures "
            "or policy refusals."
        ),
    )
    def gateway_recent_traces(
        server: str | None = None,
        state: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        import mlflow
        from mlflow.tracking import MlflowClient

        try:
            client = MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            exp = mlflow.set_experiment(settings.mlflow.experiment_name)
            filters: list[str] = []
            if server:
                filters.append(f"tags.`mcp.server` = '{server}'")
            if state:
                filters.append(f"status = '{state.upper()}'")
            traces = client.search_traces(
                locations=[exp.experiment_id],
                filter_string=" AND ".join(filters) if filters else None,
                max_results=max(1, min(limit, 50)),
            )
        except Exception as exc:
            return {"available": False, "error": str(exc), "traces": []}

        rows: list[dict[str, Any]] = []
        for tr in traces:
            info = tr.info
            tags = dict(getattr(info, "tags", {}) or {})
            st = str(getattr(info, "state", "") or "")
            if "." in st:
                st = st.split(".")[-1]
            rows.append(
                {
                    "traceId": getattr(info, "trace_id", ""),
                    "server": tags.get("mcp.server", ""),
                    "tool": tags.get("mcp.tool", ""),
                    "user": tags.get("mlflow.trace.user", ""),
                    "state": st,
                    "executionTimeMs": getattr(info, "execution_duration", None),
                }
            )
        return {"available": True, "experiment": settings.mlflow.experiment_name, "traces": rows}

    @mcp.tool(
        name="gateway_probe_upstream",
        description="Live-probe a configured external HTTP or stdio MCP upstream by slug.",
    )
    async def gateway_probe_upstream(slug: str) -> dict[str, Any]:
        clean = slug.strip().replace("_", "-").lower()
        cfg = None
        for k, v in settings.gateway.upstream_servers.items():
            if k.strip().replace("_", "-").lower() == clean:
                cfg = v
                break
        if cfg is None:
            raise ToolError(
                f"[UPSTREAM_NOT_FOUND] No configured upstream '{slug}'. "
                "Call gateway_list_servers() to see configured slugs."
            )
        proxy_srv, info = build_upstream_proxy(clean, cfg, settings)
        if proxy_srv is None:
            return info
        res = await probe_upstream_proxy(proxy_srv, timeout_s=cfg.timeout_s)
        return {**info, **res}

    @mcp.tool(
        name="gateway_run_watchdog",
        description=(
            "Run a gateway watchdog health & eval regression check. dry_run=True is safe and "
            "read-only; dry_run=False requires MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true."
        ),
    )
    async def gateway_run_watchdog(dry_run: bool = True) -> dict[str, Any]:
        if not dry_run:
            _require_admin_tools(settings)
        return await asyncio.to_thread(run_watchdog_once, settings, dry_run=dry_run)

    @mcp.tool(
        name="gateway_run_eval_benchmark",
        description=(
            "Run the MLflow 3.x golden benchmark evaluation suite. Requires "
            "MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true."
        ),
    )
    async def gateway_run_eval_benchmark(
        with_llm_judge: bool = False,
        judge_model: str | None = None,
    ) -> dict[str, Any]:
        _require_admin_tools(settings)
        return await asyncio.to_thread(
            run_golden_benchmark,
            settings,
            with_llm_judge=with_llm_judge,
            judge_model=judge_model,
        )

    @mcp.tool(
        name="gateway_upsert_upstream",
        description=(
            "Add or update an external HTTP/stdio MCP server in config/gateway.local.yaml. "
            "Requires MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true and env:/op:// secret refs only."
        ),
    )
    async def gateway_upsert_upstream(
        slug: str,
        transport: Literal["http", "stdio"],
        url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
        headers: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
        profiles: list[str] | None = None,
        governance: str = "external-proxy",
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        _require_admin_tools(settings)
        clean_slug = slug.strip().replace("_", "-").lower()
        try:
            cfg = UpstreamServerConfig(
                transport=transport,
                url=url,
                headers={k: SecretStr(v) for k, v in (headers or {}).items()},
                command=command,
                args=list(args or []),
                cwd=Path(cwd) if cwd else None,
                env={k: SecretStr(v) for k, v in (env or {}).items()},
                enabled=enabled,
                profiles=list(profiles or ["studio"]),
                governance=governance,
                description=description,
            )
            validate_upstream_secret_refs(cfg)
        except Exception as exc:
            raise ToolError(f"[INVALID_UPSTREAM] {exc}") from exc

        updated = dict(settings.gateway.upstream_servers)
        updated[clean_slug] = cfg
        saved_path = save_local_upstreams(_local_config_path(), updated)
        settings.gateway.upstream_servers[clean_slug] = cfg
        gw_state = state_provider()
        if callable(gw_state.get("on_upstreams_updated")):
            await gw_state["on_upstreams_updated"](clean_slug, cfg)
        return {"saved": clean_slug, "path": str(saved_path), "enabled": enabled}

    @mcp.tool(
        name="gateway_toggle_upstream",
        description=(
            "Enable or disable an external upstream in config/gateway.local.yaml. Requires "
            "MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true."
        ),
    )
    async def gateway_toggle_upstream(slug: str, enabled: bool) -> dict[str, Any]:
        _require_admin_tools(settings)
        clean_slug = slug.strip().replace("_", "-").lower()
        target_key = next(
            (
                k
                for k in settings.gateway.upstream_servers
                if k.strip().replace("_", "-").lower() == clean_slug
            ),
            None,
        )
        if target_key is None:
            raise ToolError(f"[UPSTREAM_NOT_FOUND] Unknown upstream '{slug}'.")
        cfg = settings.gateway.upstream_servers[target_key].model_copy(update={"enabled": enabled})
        settings.gateway.upstream_servers[target_key] = cfg
        saved_path = save_local_upstreams(_local_config_path(), settings.gateway.upstream_servers)
        return {"slug": clean_slug, "enabled": enabled, "path": str(saved_path)}

    @mcp.tool(
        name="gateway_register_prompt",
        description=(
            "Register a new MLflow 3.x Prompt version and optional alias. Requires both "
            "MCP_GATEWAY_ADMIN_TOOLS_ENABLED=true and MLFLOW_ALLOW_MUTATIONS=true."
        ),
    )
    async def gateway_register_prompt(
        name: str,
        template: str,
        commit_message: str = "",
        alias: str | None = None,
    ) -> dict[str, Any]:
        _require_admin_tools(settings)
        if not settings.mlflow.allow_mutations:
            raise ToolError(
                "[POLICY_REFUSAL] Prompt registration requires MLFLOW_ALLOW_MUTATIONS=true."
            )
        import mlflow
        import mlflow.genai

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        pv = mlflow.genai.register_prompt(
            name=name.strip(),
            template=template,
            commit_message=commit_message or "Registered via gateway_register_prompt",
        )
        ver_str = str(getattr(pv, "version", "1"))
        if alias and callable(getattr(mlflow.genai, "set_prompt_alias", None)):
            mlflow.genai.set_prompt_alias(name=name.strip(), alias=alias.strip(), version=ver_str)
        bridge.invalidate_cache()
        return {"name": name.strip(), "version": ver_str, "alias": alias}

    @mcp.resource(
        "gateway://status",
        name="gateway_status",
        description="Live gateway readiness, dependencies, and watchdog state snapshot.",
        mime_type="application/json",
    )
    async def gateway_status_resource() -> str:
        return json.dumps(await _collect_ready_status(), indent=2)

    @mcp.resource(
        "gateway://servers",
        name="gateway_servers",
        description="Mounted built-in and federated external MCP server inventory.",
        mime_type="application/json",
    )
    def gateway_servers_resource() -> str:
        gw_state = state_provider()
        return json.dumps({"servers": gw_state.get("servers", [])}, indent=2)

    @mcp.resource(
        "gateway://profiles",
        name="gateway_profiles",
        description="Curated MCP gateway profiles, member servers, and URLs.",
        mime_type="application/json",
    )
    def gateway_profiles_resource() -> str:
        gw_state = state_provider()
        return json.dumps({"profiles": gw_state.get("profiles", [])}, indent=2)

    @mcp.resource(
        "gateway://presets",
        name="gateway_presets",
        description="Saved Playground tool invocation presets persisted by the gateway.",
        mime_type="application/json",
    )
    def gateway_presets_resource() -> str:
        store = PresetStore(settings.gateway.presets_path)
        return json.dumps(
            {
                "path": str(store.path),
                "presets": [p.model_dump(mode="json") for p in store.list_presets()],
            },
            indent=2,
        )

    @mcp.resource(
        "gateway://skills",
        name="gateway_skills_catalog",
        description="MLflow 3.18 Skill Registry catalog and capability status.",
        mime_type="application/json",
    )
    async def gateway_skills_resource() -> str:
        res = await asyncio.to_thread(list_mlflow_skills, settings)
        return json.dumps(res, indent=2)

    @mcp.resource(
        "gateway://skills/{name}",
        name="gateway_skill_detail",
        description="SKILL.md content and versions for a registered MLflow skill.",
        mime_type="application/json",
    )
    async def gateway_skill_detail_resource(name: str) -> str:
        res = await asyncio.to_thread(get_mlflow_skill_detail, settings, name)
        return json.dumps(res, indent=2)

    @mcp.resource(
        "gateway://client-configs/{client}",
        name="gateway_client_config",
        description=(
            "Ready-to-paste client MCP configuration for antigravity, codex, "
            "claude-code, claude-desktop, cursor, or gemini-cli."
        ),
        mime_type="text/plain",
    )
    def gateway_client_config_resource(client: str) -> str:
        rendered = generate_client_configs(settings, repo_root=Path.cwd())
        key = client.strip().lower()
        if key not in rendered:
            raise ValueError(
                f"Unknown client '{client}'. Expected one of: {', '.join(sorted(rendered))}"
            )
        return rendered[key]

    return mcp
