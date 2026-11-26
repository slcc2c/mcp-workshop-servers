"""Servers, profiles, tool catalog, presets, UC sync, and tool execution routes."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.client_configs import generate_client_configs
from mcp_stack.core.auth import caller_client_policy_var, is_server_allowed
from mcp_stack.core.tracing import last_trace_id_var
from mcp_stack.evals import _POLICY_REFUSAL_MARKERS
from mcp_stack.gateway.state import GatewayRuntimeState
from mcp_stack.servers.unity_catalog import sync_uc_function_tools


def build_tools_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/servers")
    async def list_servers() -> dict[str, Any]:
        return {
            "composedRoute": "/mcp",
            "servers": state.server_inventory,
        }

    @router.get("/api/v1/profiles")
    async def list_profiles() -> dict[str, Any]:
        return {
            "defaultProfile": settings.gateway.default_client_profile,
            "fullRoute": "/mcp",
            "profiles": state.profile_inventory,
            "clientSnippets": generate_client_configs(settings, repo_root=Path.cwd()),
        }

    @router.post("/api/v1/profiles", response_model=None)
    async def create_profile_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        name = str(body.get("name") or "").strip().lower()
        raw_servers = body.get("servers") or []
        if isinstance(raw_servers, str):
            raw_servers = [s.strip() for s in raw_servers.split(",") if s.strip()]
        try:
            item = await state.upsert_profile(name, list(raw_servers))
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_PROFILE", "message": str(exc)}},
            )
        return {"profile": item, "restartRequired": False}

    @router.put("/api/v1/profiles/{name}", response_model=None)
    async def update_profile_api(
        name: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        raw_servers = body.get("servers") or []
        if isinstance(raw_servers, str):
            raw_servers = [s.strip() for s in raw_servers.split(",") if s.strip()]
        try:
            item = await state.upsert_profile(name, list(raw_servers))
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_PROFILE", "message": str(exc)}},
            )
        return {"profile": item, "restartRequired": False}

    @router.delete("/api/v1/profiles/{name}", response_model=None)
    async def delete_profile_api(name: str) -> dict[str, Any] | JSONResponse:
        try:
            res = await state.delete_profile(name)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "BUILTIN_PROFILE", "message": str(exc)}},
            )
        except KeyError as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "PROFILE_NOT_FOUND", "message": str(exc)}},
            )
        return {**res, "restartRequired": False}

    @router.get("/api/v1/tools")
    async def list_tools_api(
        server: str | None = None,
        profile: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        target_slugs = state.target_server_instances()

        allowed_by_profile: set[str] | None = None
        if profile:
            prof_entry = next(
                (p for p in state.profile_inventory if p["name"] == profile),
                None,
            )
            if prof_entry is None:
                return {"totalTools": 0, "profileCounts": {}, "tools": []}
            allowed_by_profile = set(prof_entry["servers"])
            if prof_entry.get("includesUpstreamMcp"):
                allowed_by_profile.add("mlflow-upstream")

        async def _gather_one(slug: str, srv: FastMCP) -> tuple[str, list[dict[str, Any]]]:
            t_out = (
                state.federated_cfg_map[slug].timeout_s
                if slug in state.federated_cfg_map
                else 2.0
            )
            return slug, await state.collect_tools_for_server(slug, srv, timeout_s=t_out)

        gathered = await asyncio.gather(
            *(_gather_one(slug, srv) for slug, srv in target_slugs.items())
        )
        per_server_tools: dict[str, list[dict[str, Any]]] = dict(gathered)

        profile_counts: dict[str, int] = {}
        for prof in state.profile_inventory:
            total = sum(len(per_server_tools.get(s, [])) for s in prof["servers"])
            if prof.get("includesUpstreamMcp"):
                total += len(per_server_tools.get("mlflow-upstream", []))
            profile_counts[str(prof["name"])] = total

        needle = (q or "").strip().lower()
        srv_filter = (server or "").strip().replace("_", "-").lower()

        filtered: list[dict[str, Any]] = []
        for slug, items in per_server_tools.items():
            if srv_filter and slug.lower() != srv_filter:
                continue
            if allowed_by_profile is not None and slug not in allowed_by_profile:
                continue
            for item in items:
                if needle:
                    hay = f"{item['name']} {item['description']} {slug}".lower()
                    if needle not in hay:
                        continue
                filtered.append(item)

        return {
            "totalTools": len(filtered),
            "profileCounts": profile_counts,
            "tools": filtered,
        }

    @router.get("/api/v1/presets")
    async def presets_list_api() -> dict[str, Any]:
        return {
            "path": str(state.preset_store.path),
            "presets": [p.model_dump(mode="json") for p in state.preset_store.list_presets()],
        }

    @router.post("/api/v1/presets", response_model=None)
    async def presets_create_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "JSON body required"}},
            )
        try:
            preset = state.preset_store.create_preset(
                name=str(payload.get("name") or ""),
                server=str(payload.get("server") or ""),
                tool=str(payload.get("tool") or ""),
                arguments=payload.get("arguments"),
                description=str(payload.get("description") or ""),
                pinned=bool(payload.get("pinned", False)),
                preset_id=payload.get("id"),
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_PRESET", "message": str(exc)}},
            )
        return {"preset": preset.model_dump(mode="json")}

    @router.put("/api/v1/presets/{preset_id}", response_model=None)
    async def presets_update_api(
        preset_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "JSON body required"}},
            )
        try:
            updated = state.preset_store.update_preset(preset_id, payload)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_PRESET", "message": str(exc)}},
            )
        if updated is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "PRESET_NOT_FOUND",
                        "message": f"Unknown preset '{preset_id}'",
                    }
                },
            )
        return {"preset": updated.model_dump(mode="json")}

    @router.delete("/api/v1/presets/{preset_id}", response_model=None)
    async def presets_delete_api(preset_id: str) -> dict[str, Any] | JSONResponse:
        deleted = state.preset_store.delete_preset(preset_id)
        if not deleted:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "PRESET_NOT_FOUND",
                        "message": f"Unknown preset '{preset_id}'",
                    }
                },
            )
        return {"deleted": preset_id}

    @router.post("/api/v1/actions/refresh-uc")
    async def action_refresh_uc() -> dict[str, Any]:
        if "unity_catalog" not in state.servers or state.uc_adapter is None:
            return {"status": "skipped", "reason": "unity_catalog server is not enabled"}
        return await sync_uc_function_tools(
            state.servers["unity_catalog"],
            state.uc_adapter,
            settings,
        )

    @router.post("/api/v1/actions/call-tool", response_model=None)
    async def action_call_tool(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "JSON body required"}},
            )
        raw_server = str(payload.get("server") or "").strip()
        tool_name = str(payload.get("tool") or "").strip()
        arguments = payload.get("arguments")
        if arguments is None:
            arguments = {}
        if not raw_server or not tool_name or not isinstance(arguments, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'server', 'tool', and object 'arguments'",
                    }
                },
            )

        slug = raw_server.replace("_", "-").lower()
        key = slug.replace("-", "_")
        if settings.gateway.effective_auth_enabled:
            policy = caller_client_policy_var.get()
            if not is_server_allowed(policy, slug):
                client_label = policy.client_name if policy else "caller"
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": (
                                f"Client '{client_label}' is not allowed to invoke tools "
                                f"on server '{slug}'"
                            ),
                        }
                    },
                )

        target_srv = (
            state.upstream_proxy
            if slug == "mlflow-upstream"
            else (state.federated_proxies.get(slug) or state.servers.get(key))
        )
        if target_srv is None:
            fed_meta = state.federated_meta.get(slug)
            if fed_meta is not None:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "SERVER_UNAVAILABLE",
                            "message": str(
                                fed_meta.get("detail")
                                or f"Upstream server '{slug}' is {fed_meta.get('connectionStatus')}"
                            ),
                        }
                    },
                )
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "SERVER_NOT_FOUND", "message": f"Unknown '{slug}'"}},
            )

        try:
            avail_tools = await asyncio.wait_for(target_srv.list_tools(), timeout=3.0)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "SERVER_UNAVAILABLE", "message": str(exc)}},
            )

        if not any(getattr(t, "name", "") == tool_name for t in avail_tools):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "TOOL_NOT_FOUND",
                        "message": f"Tool '{tool_name}' not found on server '{slug}'",
                    }
                },
            )

        t0 = time.monotonic()
        trace_token = last_trace_id_var.set(None)
        try:
            tool_res = await asyncio.wait_for(
                target_srv.call_tool(tool_name, arguments=arguments, run_middleware=True),
                timeout=30.0,
            )
            captured_trace_id = last_trace_id_var.get()
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            blocks = getattr(tool_res, "content", None) or []
            content_blocks: list[dict[str, Any]] = []
            text_parts: list[str] = []
            for block in blocks:
                b_type = getattr(block, "type", None)
                b_text = getattr(block, "text", None)
                b_data = getattr(block, "data", None)
                b_mime = getattr(block, "mimeType", None)
                if b_type == "image" or (isinstance(b_data, str) and isinstance(b_mime, str)):
                    content_blocks.append(
                        {
                            "type": "image",
                            "mimeType": str(b_mime or "image/png"),
                            "data": str(b_data or "")[:5_000_000],
                        }
                    )
                elif b_type == "resource" or getattr(block, "resource", None) is not None:
                    res_obj = getattr(block, "resource", None) or block
                    res_text = getattr(res_obj, "text", None)
                    content_blocks.append(
                        {
                            "type": "resource",
                            "uri": str(getattr(res_obj, "uri", "") or ""),
                            "mimeType": getattr(res_obj, "mimeType", None),
                            "text": str(res_text) if res_text is not None else None,
                        }
                    )
                    if isinstance(res_text, str):
                        text_parts.append(res_text)
                elif b_text is not None:
                    txt = str(b_text)
                    content_blocks.append({"type": "text", "text": txt})
                    text_parts.append(txt)
                else:
                    txt = str(block)
                    content_blocks.append({"type": "text", "text": txt})
                    text_parts.append(txt)

            raw_text = "\n".join(text_parts)
            structured = getattr(tool_res, "structured_content", None)
            if not raw_text and structured is not None:
                raw_text = json.dumps(structured, default=str)

            max_chars = 50_000
            truncated = len(raw_text) > max_chars
            clipped = raw_text[:max_chars] if truncated else raw_text
            parsed_out: Any = clipped
            if not truncated:
                try:
                    parsed_out = json.loads(clipped)
                except Exception:
                    parsed_out = clipped

            state.activity_bus.record(
                "tool_call",
                status="ok",
                server=slug,
                tool=tool_name,
                duration_ms=elapsed_ms,
                trace_id=captured_trace_id,
                summary=f"{slug}.{tool_name} -> ok ({elapsed_ms} ms)",
            )
            return {
                "ok": True,
                "policyRefusal": False,
                "server": slug,
                "tool": tool_name,
                "durationMs": elapsed_ms,
                "traceId": captured_trace_id,
                "truncated": truncated,
                "result": parsed_out,
                "structuredContent": structured,
                "contentBlocks": content_blocks,
            }
        except ToolError as exc:
            captured_trace_id = last_trace_id_var.get()
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            msg = str(exc)
            is_refusal = any(m in msg.lower() for m in _POLICY_REFUSAL_MARKERS)
            state.activity_bus.record(
                "tool_call",
                status="policy_refusal" if is_refusal else "error",
                server=slug,
                tool=tool_name,
                duration_ms=elapsed_ms,
                trace_id=captured_trace_id,
                summary=msg[:160],
            )
            return {
                "ok": False,
                "policyRefusal": is_refusal,
                "server": slug,
                "tool": tool_name,
                "durationMs": elapsed_ms,
                "traceId": captured_trace_id,
                "error": msg,
            }
        except TimeoutError:
            elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
            state.activity_bus.record(
                "tool_call",
                status="error",
                server=slug,
                tool=tool_name,
                duration_ms=elapsed_ms,
                summary="Tool execution timed out after 30s",
            )
            return JSONResponse(
                status_code=504,
                content={
                    "ok": False,
                    "server": slug,
                    "tool": tool_name,
                    "durationMs": elapsed_ms,
                    "error": "Tool execution timed out after 30s",
                },
            )
        finally:
            last_trace_id_var.reset(trace_token)

    return router
