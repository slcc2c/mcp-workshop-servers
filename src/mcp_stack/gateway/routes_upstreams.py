"""Federated external MCP upstream CRUD and live probe routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from mcp_stack.core.config import UpstreamServerConfig, validate_upstream_secret_refs
from mcp_stack.gateway.state import GatewayRuntimeState, slug_for


def parse_upstream_payload(body: dict[str, Any]) -> UpstreamServerConfig:
    """Validate and parse an HTTP or stdio upstream payload without accepting raw secrets."""
    transport = str(body.get("transport") or "http").strip().lower()
    if transport not in {"http", "stdio"}:
        raise ValueError("transport must be 'http' or 'stdio'")
    raw_headers = body.get("headers") or {}
    raw_env = body.get("env") or {}
    if not isinstance(raw_headers, dict) or not isinstance(raw_env, dict):
        raise ValueError("headers and env must be JSON objects")
    raw_args = body.get("args") or []
    if isinstance(raw_args, str):
        raw_args = [line for line in raw_args.splitlines() if line.strip()]
    raw_profiles = body.get("profiles") or ["studio"]
    if isinstance(raw_profiles, str):
        raw_profiles = [p.strip() for p in raw_profiles.split(",") if p.strip()]
    raw_allow = body.get("allow_tools") or []
    if isinstance(raw_allow, str):
        raw_allow = [p.strip() for p in raw_allow.replace(",", "\n").splitlines() if p.strip()]
    raw_deny = body.get("deny_tools") or []
    if isinstance(raw_deny, str):
        raw_deny = [p.strip() for p in raw_deny.replace(",", "\n").splitlines() if p.strip()]
    raw_cwd = str(body.get("cwd") or "").strip() or None
    cfg = UpstreamServerConfig(
        transport=transport,  # type: ignore[arg-type]
        url=str(body.get("url") or "").strip() or None,
        headers={str(k): SecretStr(str(v)) for k, v in raw_headers.items() if str(k).strip()},
        command=str(body.get("command") or "").strip() or None,
        args=[str(a) for a in raw_args],
        cwd=Path(raw_cwd) if raw_cwd else None,
        env={str(k): SecretStr(str(v)) for k, v in raw_env.items() if str(k).strip()},
        allow_tools=[str(a).strip() for a in raw_allow if str(a).strip()],
        deny_tools=[str(d).strip() for d in raw_deny if str(d).strip()],
        enabled=bool(body.get("enabled", True)),
        compose_into_full=bool(body.get("compose_into_full", True)),
        profiles=[str(p).strip() for p in raw_profiles if str(p).strip()] or ["studio"],
        timeout_s=float(body.get("timeout_s", 5.0)),
        registry_name=str(body.get("registry_name") or "").strip() or None,
        governance=str(body.get("governance") or "external-proxy").strip() or "external-proxy",
        description=str(body.get("description") or "").strip(),
    )
    validate_upstream_secret_refs(cfg)
    if cfg.transport == "http" and not cfg.url:
        raise ValueError("url is required for http upstream")
    if cfg.transport == "stdio" and not cfg.command:
        raise ValueError("command is required for stdio upstream")
    return cfg


def build_upstreams_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    upstreams = state.settings.gateway.upstream_servers

    @router.get("/api/v1/upstreams")
    async def list_upstreams_api() -> dict[str, Any]:
        items = [state.serialize_upstream_item(k, cfg) for k, cfg in upstreams.items()]
        return {"configPath": str(state.local_upstreams_path()), "upstreams": items}

    @router.post("/api/v1/upstreams", response_model=None)
    async def create_upstream_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        slug = slug_for(str(body.get("slug") or body.get("name") or ""))
        if not slug:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'slug'"}},
            )
        try:
            cfg = parse_upstream_payload(body)
        except ValueError as exc:
            code = "RAW_SECRET_REJECTED" if "raw secret" in str(exc) else "INVALID_REQUEST"
            return JSONResponse(
                status_code=400,
                content={"error": {"code": code, "message": str(exc)}},
            )
        item = await state.sync_upstream_runtime(slug, cfg)
        return {"upstream": item}

    @router.put("/api/v1/upstreams/{slug}", response_model=None)
    async def update_upstream_api(
        slug: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        clean_slug = slug_for(slug)
        body = payload if isinstance(payload, dict) else {}
        try:
            cfg = parse_upstream_payload(body)
        except ValueError as exc:
            code = "RAW_SECRET_REJECTED" if "raw secret" in str(exc) else "INVALID_REQUEST"
            return JSONResponse(
                status_code=400,
                content={"error": {"code": code, "message": str(exc)}},
            )
        item = await state.sync_upstream_runtime(clean_slug, cfg)
        return {"upstream": item}

    @router.delete("/api/v1/upstreams/{slug}", response_model=None)
    async def delete_upstream_api(slug: str) -> dict[str, Any] | JSONResponse:
        clean_slug = slug_for(slug)
        if not any(slug_for(k) == clean_slug for k in upstreams):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "UPSTREAM_NOT_FOUND",
                        "message": f"Unknown '{clean_slug}'",
                    }
                },
            )
        return await state.sync_upstream_runtime(clean_slug, None)

    @router.post("/api/v1/upstreams/{slug}/probe", response_model=None)
    async def probe_single_upstream_api(slug: str) -> dict[str, Any] | JSONResponse:
        clean_slug = slug_for(slug)
        cfg = next(
            (v for k, v in upstreams.items() if slug_for(k) == clean_slug),
            None,
        )
        if cfg is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "UPSTREAM_NOT_FOUND",
                        "message": f"Unknown '{clean_slug}'",
                    }
                },
            )
        item = await state.sync_upstream_runtime(clean_slug, cfg)
        return {"upstream": item}

    return router
