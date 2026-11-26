"""MLflow GenAI Datasets & Evaluations Workbench REST routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from mcp_stack.evals import (
    GOLDEN_DATASET_NAME,
    compare_eval_runs,
    get_eval_dataset,
    get_eval_run_detail,
    list_eval_datasets,
    list_eval_runs,
    merge_dataset_records,
    run_agent_dataset_evaluation,
    run_golden_benchmark,
    run_trace_evaluation,
)
from mcp_stack.gateway.state import GatewayRuntimeState


def build_evals_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/evals/datasets")
    async def eval_datasets_list_api(experiment: str = "") -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                list_eval_datasets,
                settings,
                experiment_name=experiment.strip() or None,
            )
        except Exception as exc:
            return {
                "available": False,
                "experiment": experiment.strip() or settings.mlflow.experiment_name,
                "error": str(exc),
                "datasets": [],
            }

    @router.get("/api/v1/evals/datasets/{dataset_id}", response_model=None)
    async def eval_dataset_detail_api(dataset_id: str) -> dict[str, Any] | JSONResponse:
        try:
            return await asyncio.to_thread(get_eval_dataset, settings, dataset_id)
        except Exception as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "DATASET_NOT_FOUND", "message": str(exc)}},
            )

    @router.post("/api/v1/evals/datasets/{dataset_id}/records", response_model=None)
    async def eval_dataset_merge_records_api(
        dataset_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        raw_records = body.get("records")
        if isinstance(raw_records, dict):
            records = [raw_records]
        elif isinstance(raw_records, list):
            records = [r for r in raw_records if isinstance(r, dict)]
        elif "inputs" in body:
            records = [{"inputs": body["inputs"], "expectations": body.get("expectations") or {}}]
        else:
            records = []
        if not records:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'records' list"}},
            )
        try:
            return await asyncio.to_thread(merge_dataset_records, settings, dataset_id, records)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.get("/api/v1/evals/runs")
    async def eval_runs_list_api(experiment: str = "", limit: int = 25) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                list_eval_runs,
                settings,
                experiment_name=experiment.strip() or None,
                limit=max(1, min(limit, 50)),
            )
        except Exception as exc:
            return {
                "available": False,
                "experiment": experiment.strip() or settings.mlflow.experiment_name,
                "error": str(exc),
                "runs": [],
            }

    @router.get("/api/v1/evals/runs/{run_id}", response_model=None)
    async def eval_run_detail_api(run_id: str) -> dict[str, Any] | JSONResponse:
        try:
            return await asyncio.to_thread(get_eval_run_detail, settings, run_id)
        except Exception as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "RUN_NOT_FOUND", "message": str(exc)}},
            )

    @router.get("/api/v1/evals/compare", response_model=None)
    async def eval_runs_compare_api(run_a: str, run_b: str) -> dict[str, Any] | JSONResponse:
        try:
            return await asyncio.to_thread(compare_eval_runs, settings, run_a, run_b)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "COMPARE_FAILED", "message": str(exc)}},
            )

    @router.post("/api/v1/evals/run", response_model=None)
    async def eval_run_launch_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        mode = str(body.get("mode") or "golden").strip().lower()
        with_judge = bool(body.get("with_llm_judge", False))
        judge_model = str(body.get("judge_model") or "").strip() or None
        model_api = str(body.get("model_api") or "default").strip().lower() or "default"
        dataset_name = str(body.get("dataset_name") or GOLDEN_DATASET_NAME).strip()
        experiment_name = str(body.get("experiment") or "").strip() or None

        try:
            if mode == "traces":
                limit = max(1, min(int(body.get("limit", 20)), 100))
                res = await asyncio.to_thread(
                    run_trace_evaluation,
                    settings,
                    experiment_name=experiment_name,
                    limit=limit,
                    with_llm_judge=with_judge,
                    judge_model=judge_model,
                    model_api=model_api,
                )
            elif mode == "agent":
                res = await asyncio.to_thread(
                    run_agent_dataset_evaluation,
                    settings,
                    dataset_name=dataset_name,
                    experiment_name=experiment_name,
                    profile=str(body.get("profile") or "").strip() or None,
                    model=str(body.get("model") or "").strip() or None,
                    with_llm_judge=with_judge,
                    judge_model=judge_model,
                    model_api=model_api,
                )
            elif mode == "golden":
                res = await asyncio.to_thread(
                    run_golden_benchmark,
                    settings,
                    experiment_name=experiment_name,
                    dataset_name=dataset_name,
                    with_llm_judge=with_judge,
                    judge_model=judge_model,
                    model_api=model_api,
                )
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_REQUEST",
                            "message": "mode must be 'golden', 'traces', or 'agent'",
                        }
                    },
                )
            state.activity_bus.record(
                "eval_run",
                status="ok",
                summary=f"Eval '{mode}' finished (run={res.get('run_id')})",
            )
            return res
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": str(exc)}},
            )
        except Exception as exc:
            state.activity_bus.record("eval_run", status="error", summary=str(exc)[:180])
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "EVAL_FAILED", "message": str(exc)}},
            )

    return router
