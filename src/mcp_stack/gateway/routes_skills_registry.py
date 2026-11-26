"""MLflow 3.18 Skill Registry REST routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from mcp_stack.gateway.state import GatewayRuntimeState
from mcp_stack.skill_registry import (
    get_mlflow_skill_detail,
    list_mlflow_skills,
    register_mlflow_skill,
    update_mlflow_skill_version,
)


def build_skills_registry_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/mlflow/skills")
    async def mlflow_skills_list_api(
        q: str = "",
        status: str = "",
        organization: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            list_mlflow_skills,
            settings,
            query=q,
            status=status,
            organization=organization,
            max_results=limit,
        )

    @router.get("/api/v1/mlflow/skills/{name}", response_model=None)
    async def mlflow_skill_detail_api(
        name: str,
        organization: str = "",
        version_or_alias: str | None = None,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return await asyncio.to_thread(
                get_mlflow_skill_detail,
                settings,
                name,
                organization=organization,
                version_or_alias=version_or_alias,
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=501,
                content={"error": {"code": "SKILL_REGISTRY_UNSUPPORTED", "message": str(exc)}},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "SKILL_NOT_FOUND", "message": str(exc)}},
            )

    @router.post("/api/v1/mlflow/skills", response_model=None)
    async def mlflow_skill_register_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        try:
            res = await asyncio.to_thread(
                register_mlflow_skill,
                settings,
                source=body.get("source"),
                local_skill_id=body.get("localSkillId"),
                name=body.get("name"),
                organization=str(body.get("organization") or ""),
                status=str(body.get("status") or "draft"),
                alias=body.get("alias"),
            )
            sk_info = res["skill"]
            state.activity_bus.record(
                "skill_register",
                status="ok",
                summary=f"Registered skill {sk_info.get('name')} v{sk_info.get('version')}",
            )
            return res
        except PermissionError as exc:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "MLFLOW_MUTATIONS_DISABLED", "message": str(exc)}},
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": str(exc)}},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "SKILL_REGISTRY_ERROR", "message": str(exc)}},
            )

    @router.patch("/api/v1/mlflow/skills/{name}/versions/{version}", response_model=None)
    async def mlflow_skill_version_update_api(
        name: str,
        version: int,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        try:
            return await asyncio.to_thread(
                update_mlflow_skill_version,
                settings,
                name=name,
                version=version,
                organization=str(body.get("organization") or ""),
                status=body.get("status"),
                alias=body.get("alias"),
                delete_alias=body.get("deleteAlias"),
            )
        except PermissionError as exc:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "MLFLOW_MUTATIONS_DISABLED", "message": str(exc)}},
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": str(exc)}},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "SKILL_REGISTRY_ERROR", "message": str(exc)}},
            )

    return router
