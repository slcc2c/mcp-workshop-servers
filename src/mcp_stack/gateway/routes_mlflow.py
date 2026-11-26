"""MLflow traces, prompt/model registry, dataset promotion, and eval action routes."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from mcp_stack.core.auth import caller_client_id_var
from mcp_stack.core.tracing import redact_payload
from mcp_stack.evals import (
    GOLDEN_DATASET_NAME,
    _trace_duration_ms,
    is_expected_policy_refusal,
)
from mcp_stack.gateway.state import GatewayRuntimeState
from mcp_stack.watchdog import _EVAL_SCORE_KEYS


def build_mlflow_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/api/v1/traces")
    async def recent_traces_api(
        limit: int = 25,
        experiment: str = "",
        server: str = "",
        user: str = "",
        model_id: str = "",
        trace_state: str = "",
        state: str = "",
        policy_refusal: str = "all",
        q: str = "",
    ) -> dict[str, Any]:
        clamped = max(1, min(limit, 100))
        effective_state = state or trace_state

        def _fetch() -> dict[str, Any]:
            import mlflow

            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            target_exp_name = experiment.strip() or settings.mlflow.experiment_name
            exp = client.get_experiment_by_name(target_exp_name)
            experiments_out: list[dict[str, str]] = []
            try:
                for item in client.search_experiments(max_results=50):
                    if getattr(item, "lifecycle_stage", "active") == "active":
                        experiments_out.append(
                            {
                                "id": str(item.experiment_id),
                                "name": str(item.name),
                            }
                        )
            except Exception:
                pass
            if exp is None:
                return {
                    "available": True,
                    "experiment": target_exp_name,
                    "experiments": experiments_out,
                    "traces": [],
                    "facets": {"servers": [], "users": [], "modelIds": []},
                    "latestEvalRun": None,
                    "evalHistory": [],
                    "evalRegression": {
                        "status": "no_eval_runs",
                        "threshold": settings.gateway.eval_regression_threshold,
                    },
                }
            search_limit = max(clamped * 3, 60)
            traces = client.search_traces(
                locations=[exp.experiment_id],
                max_results=search_limit,
                order_by=["timestamp_ms DESC"],
            )
            all_rows: list[dict[str, Any]] = []
            facet_servers: set[str] = set()
            facet_users: set[str] = set()
            facet_models: set[str] = set()
            for tr in traces:
                info = getattr(tr, "info", tr)
                spans = getattr(getattr(tr, "data", None), "spans", None) or []
                root_name = getattr(spans[0], "name", "") if spans else ""
                tags = dict(getattr(info, "tags", None) or {})
                meta = dict(getattr(info, "trace_metadata", None) or {})
                srv_val = str(
                    tags.get("mcp.server")
                    or (root_name.split(".", 1)[0] if "." in root_name else "")
                ).strip()
                tool_val = str(
                    tags.get("mcp.tool")
                    or (root_name.split(".", 1)[1] if "." in root_name else "")
                ).strip()
                user_val = str(
                    meta.get("mlflow.trace.user") or tags.get("mcp.user") or ""
                ).strip()
                model_val = str(
                    getattr(info, "model_id", None) or meta.get("mlflow.modelId") or ""
                ).strip()
                if srv_val:
                    facet_servers.add(srv_val)
                if user_val:
                    facet_users.add(user_val)
                if model_val:
                    facet_models.add(model_val)
                all_rows.append(
                    {
                        "traceId": getattr(info, "trace_id", None)
                        or getattr(info, "request_id", None),
                        "name": root_name,
                        "state": str(getattr(info, "state", "")),
                        "policyRefusal": is_expected_policy_refusal(tr),
                        "durationMs": round(_trace_duration_ms(tr), 1),
                        "timestampMs": getattr(info, "timestamp_ms", None),
                        "user": user_val or None,
                        "sessionId": meta.get("mlflow.trace.session"),
                        "modelId": model_val or None,
                        "server": srv_val or None,
                        "tool": tool_val or None,
                        "profile": tags.get("mcp.profile"),
                        "assessmentCount": len(getattr(info, "assessments", None) or []),
                    }
                )

            srv_f = server.strip().lower()
            usr_f = user.strip().lower()
            mdl_f = model_id.strip()
            st_f = effective_state.strip().upper()
            pr_f = policy_refusal.strip().lower()
            q_f = q.strip().lower()

            filtered: list[dict[str, Any]] = []
            for row in all_rows:
                if srv_f and str(row.get("server") or "").lower() != srv_f:
                    continue
                if usr_f and str(row.get("user") or "").lower() != usr_f:
                    continue
                if mdl_f and str(row.get("modelId") or "") != mdl_f:
                    continue
                if st_f and st_f not in str(row.get("state") or "").upper():
                    continue
                if pr_f == "only" and not row["policyRefusal"]:
                    continue
                if pr_f == "exclude" and row["policyRefusal"]:
                    continue
                if q_f:
                    hay = (
                        f"{row.get('traceId', '')} {row.get('name', '')} "
                        f"{row.get('server', '')} {row.get('tool', '')} {row.get('user', '')}"
                    ).lower()
                    if q_f not in hay:
                        continue
                filtered.append(row)
                if len(filtered) >= clamped:
                    break

            eval_history: list[dict[str, Any]] = []
            try:
                runs = client.search_runs(
                    [exp.experiment_id],
                    order_by=["attributes.start_time DESC"],
                    max_results=25,
                )
                for run in runs:
                    metrics = {
                        k: round(float(v), 4)
                        for k, v in (run.data.metrics or {}).items()
                        if "/" in k or "tool_" in k or "policy_" in k
                    }
                    if metrics:
                        core_vals = [
                            metrics[k] for k in _EVAL_SCORE_KEYS if k in metrics
                        ] or list(metrics.values())
                        min_score = round(min(core_vals), 4)
                        eval_history.append(
                            {
                                "run_id": run.info.run_id,
                                "run_name": getattr(run.info, "run_name", None),
                                "timestamp_ms": getattr(run.info, "start_time", None),
                                "min_score": min_score,
                                "metrics": metrics,
                            }
                        )
                        if len(eval_history) >= 10:
                            break
            except Exception:
                pass

            latest_eval = eval_history[0] if eval_history else None
            threshold = settings.gateway.eval_regression_threshold
            if latest_eval is None:
                eval_regression: dict[str, Any] = {
                    "status": "no_eval_runs",
                    "threshold": threshold,
                }
            else:
                failing = {
                    k: v
                    for k, v in latest_eval["metrics"].items()
                    if k in _EVAL_SCORE_KEYS and v < threshold
                }
                eval_regression = {
                    "status": "regression" if failing else "ok",
                    "threshold": threshold,
                    "run_id": latest_eval["run_id"],
                    "run_name": latest_eval.get("run_name"),
                    "min_score": latest_eval["min_score"],
                    "failing_metrics": failing,
                }

            return {
                "available": True,
                "experiment": target_exp_name,
                "experimentId": exp.experiment_id,
                "experiments": experiments_out,
                "traces": filtered,
                "facets": {
                    "servers": sorted(facet_servers),
                    "users": sorted(facet_users),
                    "modelIds": sorted(facet_models),
                },
                "latestEvalRun": latest_eval,
                "evalHistory": eval_history,
                "evalRegression": eval_regression,
            }

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            return {
                "available": False,
                "experiment": experiment.strip() or settings.mlflow.experiment_name,
                "experiments": [],
                "error": str(exc),
                "traces": [],
                "facets": {"servers": [], "users": [], "modelIds": []},
                "latestEvalRun": None,
                "evalHistory": [],
                "evalRegression": {
                    "status": "unavailable",
                    "threshold": settings.gateway.eval_regression_threshold,
                },
            }

    @router.get("/api/v1/traces/{trace_id}", response_model=None)
    async def trace_detail_api(trace_id: str) -> dict[str, Any] | JSONResponse:
        def _safe_json(val: Any) -> Any:
            try:
                return json.loads(json.dumps(val, default=str))
            except Exception:
                return str(val)

        def _fetch_one() -> dict[str, Any]:
            import mlflow

            flush_fn = getattr(mlflow, "flush_trace_async_logging", None)
            if callable(flush_fn):
                with suppress(Exception):
                    flush_fn(terminate=False)
            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            trace = None
            last_exc: Exception | None = None
            for attempt in range(4):
                try:
                    trace = client.get_trace(trace_id)
                    break
                except Exception as exc:
                    last_exc = exc
                    msg_l = str(exc).lower()
                    is_transient = (
                        "not found" in msg_l
                        or "does not exist" in msg_l
                        or "corrupted" in msg_l
                    )
                    if not is_transient or attempt == 3:
                        raise
                    time.sleep(0.35)
            if trace is None and last_exc is not None:
                raise last_exc
            info = getattr(trace, "info", trace)
            raw_spans = getattr(getattr(trace, "data", None), "spans", None) or []
            spans_out: list[dict[str, Any]] = []
            for sp in raw_spans:
                start_ns = getattr(sp, "start_time_ns", None)
                end_ns = getattr(sp, "end_time_ns", None)
                dur_ms = (
                    round((end_ns - start_ns) / 1_000_000.0, 2)
                    if isinstance(start_ns, int)
                    and isinstance(end_ns, int)
                    and end_ns >= start_ns
                    else None
                )
                events_out: list[dict[str, Any]] = []
                for ev in getattr(sp, "events", None) or []:
                    attrs = getattr(ev, "attributes", None)
                    clean_attrs = (
                        {
                            k: v
                            for k, v in attrs.items()
                            if k != "exception.stacktrace"
                        }
                        if isinstance(attrs, dict)
                        else attrs
                    )
                    events_out.append(
                        {
                            "name": getattr(ev, "name", None),
                            "attributes": _safe_json(clean_attrs),
                        }
                    )
                raw_attrs = getattr(sp, "attributes", None)
                clean_span_attrs = (
                    redact_payload(dict(raw_attrs))
                    if isinstance(raw_attrs, dict)
                    else {}
                )
                spans_out.append(
                    {
                        "spanId": getattr(sp, "span_id", None),
                        "parentId": getattr(sp, "parent_id", None),
                        "name": getattr(sp, "name", ""),
                        "spanType": str(getattr(sp, "span_type", "")),
                        "status": str(getattr(sp, "status", "")),
                        "durationMs": dur_ms,
                        "startTimeMs": (
                            round(start_ns / 1_000_000.0, 2)
                            if isinstance(start_ns, int)
                            else None
                        ),
                        "endTimeMs": (
                            round(end_ns / 1_000_000.0, 2)
                            if isinstance(end_ns, int)
                            else None
                        ),
                        "attributes": _safe_json(clean_span_attrs),
                        "inputs": _safe_json(getattr(sp, "inputs", None)),
                        "outputs": _safe_json(getattr(sp, "outputs", None)),
                        "events": events_out,
                    }
                )

            assessments_out: list[dict[str, Any]] = []
            for item in getattr(info, "assessments", None) or []:
                feedback = getattr(item, "feedback", None)
                expectation = getattr(item, "expectation", None)
                if feedback is not None:
                    kind = "feedback"
                    val = getattr(feedback, "value", None)
                elif expectation is not None:
                    kind = "expectation"
                    val = getattr(expectation, "value", None)
                else:
                    kind = "assessment"
                    val = getattr(item, "value", None)
                assessments_out.append(
                    {
                        "kind": kind,
                        "name": getattr(item, "name", None),
                        "value": _safe_json(val),
                        "rationale": getattr(item, "rationale", None),
                    }
                )

            tags = dict(getattr(info, "tags", None) or {})
            meta = dict(getattr(info, "trace_metadata", None) or {})
            root_span = next((s for s in spans_out if not s.get("parentId")), None) or (
                spans_out[0] if spans_out else {}
            )
            root_attrs = root_span.get("attributes") if isinstance(root_span, dict) else {}
            srv_name = tags.get("mcp.server") or (
                root_attrs.get("mcp.server") if isinstance(root_attrs, dict) else None
            )
            tl_name = tags.get("mcp.tool") or (
                root_attrs.get("mcp.tool") if isinstance(root_attrs, dict) else None
            )
            if (not srv_name or not tl_name) and isinstance(root_span, dict):
                rname = str(root_span.get("name") or "")
                if "." in rname:
                    cand_s, cand_t = rname.split(".", 1)
                    srv_name = srv_name or cand_s
                    tl_name = tl_name or cand_t
            return {
                "traceId": getattr(info, "trace_id", None) or trace_id,
                "state": str(getattr(info, "state", "")),
                "policyRefusal": is_expected_policy_refusal(trace),
                "durationMs": round(_trace_duration_ms(trace), 2),
                "timestampMs": getattr(info, "timestamp_ms", None),
                "server": srv_name,
                "tool": tl_name,
                "user": meta.get("mlflow.trace.user"),
                "sessionId": meta.get("mlflow.trace.session"),
                "modelId": meta.get("mlflow.modelId") or getattr(info, "model_id", None),
                "tags": _safe_json(tags),
                "spans": spans_out,
                "assessments": assessments_out,
            }

        try:
            return await asyncio.to_thread(_fetch_one)
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            status_code = 404 if ("not found" in lowered or "does not exist" in lowered) else 503
            code = "NOT_FOUND" if status_code == 404 else "MLFLOW_UNAVAILABLE"
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": msg}},
            )

    @router.post("/api/v1/traces/{trace_id}/feedback", response_model=None)
    async def trace_feedback_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict) or "value" not in payload:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'value'"}},
            )
        name = str(payload.get("name") or "human_quality").strip() or "human_quality"
        value = payload["value"]
        rationale = (
            str(payload["rationale"]).strip()
            if payload.get("rationale") is not None
            else None
        )
        caller_id = caller_client_id_var.get() or "dashboard"

        def _log() -> dict[str, Any]:
            import mlflow
            from mlflow.entities.assessment_source import AssessmentSource, AssessmentSourceType

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            assessment = mlflow.log_feedback(
                trace_id=trace_id,
                name=name,
                value=value,
                rationale=rationale or None,
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN,
                    source_id=caller_id,
                ),
            )
            return {
                "logged": True,
                "traceId": trace_id,
                "assessmentId": getattr(assessment, "assessment_id", None),
                "name": name,
                "value": value,
            }

        try:
            return await asyncio.to_thread(_log)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/traces/{trace_id}/expectation", response_model=None)
    async def trace_expectation_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not isinstance(payload, dict) or "value" not in payload:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'value'"}},
            )
        name = str(payload.get("name") or "expected_outcome").strip() or "expected_outcome"
        value = payload["value"]
        caller_id = caller_client_id_var.get() or "dashboard"

        def _log() -> dict[str, Any]:
            import mlflow
            from mlflow.entities.assessment_source import AssessmentSource, AssessmentSourceType

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            assessment = mlflow.log_expectation(
                trace_id=trace_id,
                name=name,
                value=value,
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN,
                    source_id=caller_id,
                ),
            )
            return {
                "logged": True,
                "traceId": trace_id,
                "assessmentId": getattr(assessment, "assessment_id", None),
                "name": name,
                "value": value,
            }

        try:
            return await asyncio.to_thread(_log)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/traces/{trace_id}/tag", response_model=None)
    async def trace_tag_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        key = str((payload or {}).get("key") or "").strip() if isinstance(payload, dict) else ""
        val = str((payload or {}).get("value") or "").strip() if isinstance(payload, dict) else ""
        if not key:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide 'key'"}},
            )

        def _tag() -> dict[str, Any]:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            mlflow.set_trace_tag(trace_id=trace_id, key=key, value=val)
            return {"tagged": True, "traceId": trace_id, "key": key, "value": val}

        try:
            return await asyncio.to_thread(_tag)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/traces/{trace_id}/promote-to-dataset", response_model=None)
    async def trace_promote_to_dataset_api(
        trace_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        body = payload if isinstance(payload, dict) else {}
        dataset_name = str(body.get("dataset_name") or GOLDEN_DATASET_NAME).strip()
        expected_outcome = str(body.get("expected_outcome") or "").strip()
        must_contain = body.get("must_contain")

        def _promote() -> dict[str, Any]:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
            trace = client.get_trace(trace_id)
            spans = getattr(getattr(trace, "data", None), "spans", None) or []
            if not spans:
                raise ValueError(f"Trace '{trace_id}' has no spans")
            root = spans[0]
            attrs = dict(getattr(root, "attributes", None) or {})
            raw_inputs = getattr(root, "inputs", None)
            inputs_dict = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}

            if {"server", "tool"} <= set(inputs_dict.keys()):
                srv_name = str(inputs_dict["server"])
                tool_name = str(inputs_dict["tool"])
                args_dict = dict(inputs_dict.get("arguments") or {})
            else:
                srv_name = str(attrs.get("mcp.server") or "")
                tool_name = str(attrs.get("mcp.tool") or "")
                span_name = str(getattr(root, "name", "") or "")
                if (not srv_name or not tool_name) and "." in span_name:
                    p_srv, p_tool = span_name.split(".", 1)
                    srv_name = srv_name or p_srv
                    tool_name = tool_name or p_tool
                args_dict = inputs_dict

            if not srv_name or not tool_name:
                raise ValueError("Could not determine 'server' and 'tool' from trace root span")

            outcome = expected_outcome or (
                "policy_refusal" if is_expected_policy_refusal(trace) else "ok"
            )
            expectations: dict[str, Any] = {"expected_outcome": outcome}
            if isinstance(must_contain, str) and must_contain.strip():
                expectations["must_contain"] = must_contain.strip()

            record = {
                "inputs": {
                    "server": srv_name,
                    "tool": tool_name,
                    "arguments": args_dict,
                },
                "expectations": expectations,
            }
            import mcp_stack.gateway.app as app_mod

            sync_res = app_mod.sync_golden_dataset(
                settings,
                dataset_name=dataset_name,
                cases=[record],
            )
            mlflow.set_trace_tag(trace_id=trace_id, key="promoted_to_dataset", value=dataset_name)
            return {
                "promoted": True,
                "traceId": trace_id,
                "dataset": sync_res,
                "record": record,
            }

        try:
            return await asyncio.to_thread(_promote)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_TRACE", "message": str(exc)}},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.get("/api/v1/mlflow/registry")
    async def mlflow_registry_api() -> dict[str, Any]:
        def _load_registry() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

            mcp_servers_out: list[dict[str, Any]] = []
            try:
                for srv in client.search_mcp_servers(max_results=50):
                    aliases_dict = dict(getattr(srv, "aliases", None) or {})
                    tags_dict = dict(getattr(srv, "tags", None) or {})
                    srv_url = getattr(srv, "url", None) or tags_dict.get("gateway_route") or ""
                    if not srv_url and aliases_dict:
                        first_ver = str(next(iter(aliases_dict.values())))
                        try:
                            mv = client.get_mcp_server_version(
                                name=str(srv.name), version=first_ver
                            )
                            remotes = getattr(mv, "remotes", None) or []
                            if remotes:
                                r0 = remotes[0]
                                srv_url = (
                                    str(r0.get("url") or "")
                                    if isinstance(r0, dict)
                                    else str(getattr(r0, "url", "") or "")
                                )
                        except Exception:
                            pass
                    mcp_servers_out.append(
                        {
                            "name": getattr(srv, "name", None),
                            "url": srv_url or None,
                            "version": getattr(srv, "version", None),
                            "description": getattr(srv, "description", None),
                            "aliases": aliases_dict,
                            "tags": tags_dict,
                        }
                    )
            except Exception:
                pass

            prompts_out: list[dict[str, Any]] = []
            try:
                prompts = mlflow.genai.search_prompts(max_results=50)
                for p in prompts[:50]:
                    p_name = str(getattr(p, "name", ""))
                    versions_out: list[dict[str, Any]] = []
                    try:
                        vers = client.search_prompt_versions(name=p_name, max_results=25)
                        for v in vers:
                            versions_out.append(
                                {
                                    "version": getattr(v, "version", None),
                                    "aliases": list(getattr(v, "aliases", None) or []),
                                    "commitMessage": getattr(v, "commit_message", None),
                                    "creationTimestamp": getattr(v, "creation_timestamp", None),
                                }
                            )
                        versions_out.sort(
                            key=lambda item: (
                                int(item["version"])
                                if str(item.get("version") or "").isdigit()
                                else -1
                            ),
                            reverse=True,
                        )
                    except Exception:
                        pass
                    prompts_out.append(
                        {
                            "name": p_name,
                            "description": getattr(p, "description", None),
                            "tags": dict(getattr(p, "tags", None) or {}),
                            "versions": versions_out,
                        }
                    )
            except Exception:
                pass

            reg_models_out: list[dict[str, Any]] = []
            try:
                for m in client.search_registered_models(max_results=30):
                    latest = [
                        {
                            "version": getattr(lv, "version", None),
                            "currentStage": getattr(lv, "current_stage", None),
                            "aliases": list(getattr(lv, "aliases", None) or []),
                        }
                        for lv in (getattr(m, "latest_versions", None) or [])
                    ]
                    reg_models_out.append(
                        {
                            "name": getattr(m, "name", None),
                            "description": getattr(m, "description", None),
                            "aliases": dict(getattr(m, "aliases", None) or {}),
                            "tags": dict(getattr(m, "tags", None) or {}),
                            "latestVersions": latest,
                        }
                    )
            except Exception:
                pass

            logged_models_out: list[dict[str, Any]] = []
            try:
                exp = client.get_experiment_by_name(settings.mlflow.experiment_name)
                if exp is not None:
                    for lm in client.search_logged_models(
                        experiment_ids=[exp.experiment_id], max_results=20
                    ):
                        logged_models_out.append(
                            {
                                "modelId": getattr(lm, "model_id", None),
                                "name": getattr(lm, "name", None),
                                "status": str(getattr(lm, "status", "")),
                                "tags": dict(getattr(lm, "tags", None) or {}),
                                "metrics": [
                                    {
                                        "key": getattr(met, "key", None),
                                        "value": getattr(met, "value", None),
                                    }
                                    for met in (getattr(lm, "metrics", None) or [])
                                ],
                            }
                        )
            except Exception:
                pass

            return {
                "available": True,
                "mutationsEnabled": settings.mlflow.allow_mutations,
                "experiment": settings.mlflow.experiment_name,
                "mcpServers": mcp_servers_out,
                "prompts": prompts_out,
                "registeredModels": reg_models_out,
                "loggedModels": logged_models_out,
            }

        try:
            return await asyncio.to_thread(_load_registry)
        except Exception as exc:
            return {
                "available": False,
                "mutationsEnabled": settings.mlflow.allow_mutations,
                "experiment": settings.mlflow.experiment_name,
                "error": str(exc),
                "mcpServers": [],
                "prompts": [],
                "registeredModels": [],
                "loggedModels": [],
            }

    @router.get("/api/v1/mlflow/prompts/{name}", response_model=None)
    async def mlflow_prompt_detail_api(
        name: str,
        version_or_alias: str = "latest",
    ) -> dict[str, Any] | JSONResponse:
        def _load() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            if version_or_alias.isdigit():
                pv = mlflow.genai.load_prompt(name, version=int(version_or_alias))
            else:
                pv = mlflow.genai.load_prompt(f"prompts:/{name}@{version_or_alias}")
            return {
                "name": getattr(pv, "name", name),
                "version": getattr(pv, "version", None),
                "template": getattr(pv, "template", None),
                "commitMessage": getattr(pv, "commit_message", None),
                "tags": dict(getattr(pv, "tags", None) or {}),
                "uri": getattr(pv, "uri", None),
            }

        try:
            return await asyncio.to_thread(_load)
        except Exception as exc:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "PROMPT_NOT_FOUND", "message": str(exc)}},
            )

    @router.post("/api/v1/mlflow/prompts/{name}/alias", response_model=None)
    async def mlflow_prompt_alias_api(
        name: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": "Set MLFLOW_ALLOW_MUTATIONS=true to update prompt aliases",
                    }
                },
            )
        body = payload if isinstance(payload, dict) else {}
        alias = str(body.get("alias") or "").strip()
        raw_ver = body.get("version")
        if not alias or raw_ver is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'alias' and integer 'version'",
                    }
                },
            )
        version_int = int(raw_ver)

        def _set() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            mlflow.genai.set_prompt_alias(name=name, alias=alias, version=version_int)
            state.meta_prompt_provider.invalidate_cache()
            return {"updated": True, "name": name, "alias": alias, "version": version_int}

        try:
            return await asyncio.to_thread(_set)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.delete("/api/v1/mlflow/prompts/{name}/alias/{alias}", response_model=None)
    async def mlflow_prompt_alias_delete_api(
        name: str, alias: str
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": "Set MLFLOW_ALLOW_MUTATIONS=true to delete prompt aliases",
                    }
                },
            )
        clean_alias = alias.strip().lstrip("@")
        if not clean_alias:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_REQUEST", "message": "Provide valid 'alias'"}},
            )

        def _delete() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            delete_fn = getattr(mlflow.genai, "delete_prompt_alias", None)
            if callable(delete_fn):
                delete_fn(name=name, alias=clean_alias)
            else:
                client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
                client.delete_prompt_alias(name=name, alias=clean_alias)
            state.meta_prompt_provider.invalidate_cache()
            return {"deleted": True, "name": name, "alias": clean_alias}

        try:
            return await asyncio.to_thread(_delete)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/mlflow/prompts", response_model=None)
    async def mlflow_prompt_create_api(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": (
                            "Set MLFLOW_ALLOW_MUTATIONS=true to register or version prompts"
                        ),
                    }
                },
            )
        body = payload if isinstance(payload, dict) else {}
        name = str(body.get("name") or "").strip()
        template = str(body.get("template") or "")
        commit_msg = str(body.get("commitMessage") or "").strip()
        alias = str(body.get("alias") or "").strip()
        if not name or not template:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide non-empty 'name' and 'template'",
                    }
                },
            )

        def _create() -> dict[str, Any]:
            import mlflow
            import mlflow.genai

            mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
            pv = mlflow.genai.register_prompt(
                name=name,
                template=template,
                commit_message=commit_msg or "Registered from Control Plane Workbench",
            )
            ver = getattr(pv, "version", None)
            set_alias_fn = getattr(mlflow.genai, "set_prompt_alias", None)
            if alias and ver is not None and callable(set_alias_fn):
                set_alias_fn(name=name, alias=alias, version=int(ver))
            state.meta_prompt_provider.invalidate_cache()
            return {
                "created": True,
                "name": getattr(pv, "name", name),
                "version": ver,
                "alias": alias or None,
                "template": getattr(pv, "template", template),
                "commitMessage": getattr(pv, "commit_message", commit_msg),
            }

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/mlflow/models/{name}/alias", response_model=None)
    async def mlflow_model_alias_api(
        name: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any] | JSONResponse:
        if not settings.mlflow.allow_mutations:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "MLFLOW_MUTATIONS_DISABLED",
                        "message": "Set MLFLOW_ALLOW_MUTATIONS=true to update model aliases",
                    }
                },
            )
        body = payload if isinstance(payload, dict) else {}
        alias = str(body.get("alias") or "").strip()
        raw_ver = body.get("version")
        if not alias or raw_ver is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Provide 'alias' and 'version'",
                    }
                },
            )
        ver_str = str(raw_ver).strip()

        def _set() -> dict[str, Any]:
            import mlflow

            client = mlflow.MlflowClient(
                tracking_uri=settings.mlflow.tracking_uri,
                registry_uri=settings.effective_mlflow_registry_uri,
            )
            client.set_registered_model_alias(name=name, alias=alias, version=ver_str)
            return {"updated": True, "name": name, "alias": alias, "version": ver_str}

        try:
            return await asyncio.to_thread(_set)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MLFLOW_UNAVAILABLE", "message": str(exc)}},
            )

    @router.post("/api/v1/actions/eval")
    async def action_eval(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        import mcp_stack.gateway.app as app_mod

        raw_limit = 20 if not isinstance(payload, dict) else int(payload.get("limit", 20))
        clamped = max(1, min(raw_limit, 100))
        return await asyncio.to_thread(app_mod.run_trace_evaluation, settings, limit=clamped)

    @router.post("/api/v1/actions/benchmark")
    async def action_benchmark(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        import mcp_stack.gateway.app as app_mod

        with_judge = (
            False
            if not isinstance(payload, dict)
            else bool(payload.get("with_llm_judge", False))
        )
        raw_model = None if not isinstance(payload, dict) else payload.get("judge_model")
        judge_model = str(raw_model).strip() if isinstance(raw_model, str) and raw_model else None
        return await asyncio.to_thread(
            app_mod.run_golden_benchmark,
            settings,
            with_llm_judge=with_judge,
            judge_model=judge_model,
        )

    return router
