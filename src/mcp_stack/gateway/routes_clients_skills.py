"""Client config generation/verification and local Skills audit/sync routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from fastmcp import FastMCP

from mcp_stack.client_configs import (
    audit_client_configs,
    generate_client_configs,
    verify_client_connection,
)
from mcp_stack.gateway.state import GatewayRuntimeState
from mcp_stack.skills import (
    audit_skills,
    load_skills_manifest,
    resolve_manifest_path,
    sync_skills,
)


def build_clients_skills_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/clients/configs")
    async def client_configs_api(profile: str | None = None) -> dict[str, Any]:
        selected = (
            profile.strip()
            if isinstance(profile, str) and profile.strip()
            else settings.gateway.default_client_profile
        )
        target_slugs = state.target_server_instances()

        async def _gather_names(slug: str, srv: FastMCP) -> tuple[str, list[str]]:
            t_out = (
                state.federated_cfg_map[slug].timeout_s
                if slug in state.federated_cfg_map
                else 2.0
            )
            items = await state.collect_tools_for_server(slug, srv, timeout_s=t_out)
            return slug, sorted({str(t["name"]) for t in items if t.get("name")})

        gathered = await asyncio.gather(
            *(_gather_names(slug, srv) for slug, srv in target_slugs.items())
        )
        tool_catalog: dict[str, list[str]] = {
            slug: names for slug, names in gathered if names
        }
        for prof in state.profile_inventory:
            pname = str(prof.get("name") or "").strip()
            if not pname:
                continue
            combined: set[str] = set()
            for srv in prof.get("servers", []):
                combined.update(tool_catalog.get(str(srv), ()))
            if prof.get("includesUpstreamMcp"):
                combined.update(tool_catalog.get("mlflow-upstream", ()))
            if combined:
                tool_catalog[f"profile:{pname}"] = sorted(combined)

        configs = generate_client_configs(
            settings,
            repo_root=Path.cwd(),
            profile=selected,
            tool_catalog=tool_catalog,
        )
        return {
            "defaultProfile": settings.gateway.default_client_profile,
            "selectedProfile": selected,
            "profiles": state.profile_inventory,
            "configs": configs,
        }

    @router.get("/api/v1/clients/audit")
    async def client_audit_api() -> dict[str, Any]:
        return await asyncio.to_thread(audit_client_configs, settings)

    @router.post("/api/v1/clients/verify", response_model=None)
    async def client_verify_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        client_name = str(body.get("client") or "codex").strip().lower()
        raw_profile = body.get("profile")
        prof = str(raw_profile).strip() if isinstance(raw_profile, str) and raw_profile else None
        return await verify_client_connection(settings, client=client_name, profile=prof)

    @router.get("/api/v1/skills")
    async def skills_audit_api() -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
            if not mpath.exists():
                return {
                    "available": False,
                    "manifestPath": str(mpath),
                    "error": f"Skills manifest not found: {mpath}",
                }
            manifest = load_skills_manifest(mpath)
            report = audit_skills(manifest, repos_root=settings.skills.repos_root)
            report["manifestPath"] = str(mpath)
            return report

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    @router.post("/api/v1/actions/skills-sync", response_model=None)
    async def skills_sync_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        dry_run = bool(body.get("dry_run", True))
        quarantine_legacy = bool(body.get("quarantine_legacy", False))
        raw_targets = body.get("targets")
        targets = (
            [str(t).strip() for t in raw_targets if str(t).strip()]
            if isinstance(raw_targets, list)
            else None
        )

        def _run() -> dict[str, Any]:
            mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
            manifest = load_skills_manifest(mpath)
            res = sync_skills(
                manifest,
                dry_run=dry_run,
                quarantine_legacy=quarantine_legacy,
                targets=targets,
            )
            res["manifestPath"] = str(mpath)
            return res

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "SKILLS_SYNC_FAILED", "message": str(exc)}},
            )

    return router
