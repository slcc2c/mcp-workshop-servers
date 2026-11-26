"""Gateway proxy routes to the co-hosted MLflow Agent Server (ResponsesAgent)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse, StreamingResponse

from mcp_stack.gateway.state import GatewayRuntimeState


def build_agent_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/agent/status")
    async def agent_status_api() -> dict[str, Any]:
        agent_url = settings.agent.url.rstrip("/")
        reachable = False
        detail: str | None = None
        try:
            async with httpx.AsyncClient(timeout=2.0) as cli:
                r = await cli.get(f"{agent_url}/health")
                reachable = r.status_code < 400
                if not reachable:
                    detail = f"HTTP {r.status_code}"
        except Exception as exc:
            detail = str(exc)[:180]
        return {
            "reachable": reachable,
            "agentUrl": agent_url,
            "defaultProfile": settings.agent.default_profile,
            "defaultModel": settings.agent.llm_model,
            "llmBaseUrl": settings.agent.llm_base_url
            or f"{settings.mlflow.tracking_uri.rstrip('/')}/gateway/mlflow/v1",
            "maxToolRounds": settings.agent.max_tool_rounds,
            "detail": detail,
        }

    @router.post("/api/v1/agent/invocations", response_model=None)
    async def agent_invocations_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse | StreamingResponse:
        body = payload if isinstance(payload, dict) else {}
        agent_url = f"{settings.agent.url.rstrip('/')}/invocations"
        wants_stream = bool(body.get("stream", False))
        t0 = time.monotonic()

        if wants_stream:
            async def _proxy_sse() -> AsyncIterator[bytes]:
                try:
                    async with (
                        httpx.AsyncClient(timeout=settings.agent.timeout_seconds) as cli,
                        cli.stream("POST", agent_url, json=body) as resp,
                    ):
                        resp.raise_for_status()
                        async for chunk in resp.aiter_bytes():
                            yield chunk
                    elapsed = round((time.monotonic() - t0) * 1000.0, 2)
                    state.activity_bus.record(
                        "agent_turn",
                        status="ok",
                        duration_ms=elapsed,
                        summary="Agent Server streaming turn completed",
                    )
                except Exception as exc:
                    elapsed = round((time.monotonic() - t0) * 1000.0, 2)
                    state.activity_bus.record(
                        "agent_turn",
                        status="error",
                        duration_ms=elapsed,
                        summary=str(exc)[:180],
                    )
                    err_frame = json.dumps({"error": str(exc)})
                    yield f"event: error\ndata: {err_frame}\n\n".encode()

            return StreamingResponse(_proxy_sse(), media_type="text/event-stream")

        try:
            async with httpx.AsyncClient(timeout=settings.agent.timeout_seconds) as cli:
                resp = await cli.post(agent_url, json=body)
            elapsed = round((time.monotonic() - t0) * 1000.0, 2)
            if resp.status_code >= 400:
                state.activity_bus.record(
                    "agent_turn",
                    status="error",
                    duration_ms=elapsed,
                    summary=f"Agent Server HTTP {resp.status_code}",
                )
                return JSONResponse(
                    status_code=resp.status_code,
                    content={"error": {"code": "AGENT_ERROR", "message": resp.text[:400]}},
                )
            data = resp.json()
            trace_id = (data.get("custom_outputs") or {}).get("traceId") or resp.headers.get(
                "x-mlflow-trace-id"
            )
            state.activity_bus.record(
                "agent_turn",
                status="ok",
                duration_ms=elapsed,
                trace_id=trace_id,
                summary=f"Agent Server turn OK ({elapsed} ms)",
            )
            return data
        except Exception as exc:
            elapsed = round((time.monotonic() - t0) * 1000.0, 2)
            state.activity_bus.record(
                "agent_turn",
                status="error",
                duration_ms=elapsed,
                summary=str(exc)[:180],
            )
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "AGENT_UNAVAILABLE", "message": str(exc)}},
            )

    return router
