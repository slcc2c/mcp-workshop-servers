"""MLflow 3.x MCP Server (Prompts, LoggedModels, UC Registry, Evals) and upstream proxy."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def _require_mlflow_mutations(settings: MCPStackSettings) -> None:
    if not settings.mlflow.allow_mutations:
        raise ToolError(
            "MLflow mutations are disabled by policy. "
            "Set MLFLOW_ALLOW_MUTATIONS=true to enable prompt/alias writes."
        )


async def probe_mcp_http_endpoint(url: str, timeout: float = 2.0) -> dict[str, Any]:
    """Perform a real MCP JSON-RPC initialize probe against a Streamable HTTP endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "id": "healthcheck-init",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcp-stack-probe", "version": "2.0.0"},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 202):
            return {"reachable": True, "status_code": resp.status_code, "url": url}
        return {
            "reachable": False,
            "status_code": resp.status_code,
            "url": url,
            "detail": resp.text[:300],
        }
    except Exception as exc:
        return {"reachable": False, "status_code": None, "url": url, "error": str(exc)}


def create_mlflow_upstream_proxy(settings: MCPStackSettings) -> FastMCP:
    """Create a FastMCP proxy forwarding to Atelier's mlflow[mcp] endpoint."""
    return FastMCP.as_proxy(settings.mlflow.mcp_url, name="mlflow-upstream")


def create_mlflow_server(
    settings: MCPStackSettings,
    *,
    client_factory: Callable[[], Any] | None = None,
    genai_module: Any = None,
) -> FastMCP:
    """Create the complementary MLflow 3.x MCP server."""
    mcp = FastMCP("mlflow")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "mlflow"))

    def _get_client() -> Any:
        if client_factory is not None:
            return client_factory()
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        return mlflow.MlflowClient(
            tracking_uri=settings.mlflow.tracking_uri,
            registry_uri=settings.effective_mlflow_registry_uri,
        )

    def _get_genai() -> Any:
        if genai_module is not None:
            return genai_module
        import mlflow
        import mlflow.genai

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        return mlflow.genai

    @mcp.tool()
    async def mlflow_list_experiments(max_results: int = 50) -> list[dict[str, Any]]:
        """List MLflow experiments on the configured tracking server."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            exps = client.search_experiments(max_results=max_results)
            return [
                {
                    "experiment_id": e.experiment_id,
                    "name": e.name,
                    "lifecycle_stage": e.lifecycle_stage,
                    "artifact_location": e.artifact_location,
                }
                for e in exps
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_search_runs(
        experiment_ids: list[str],
        filter_string: str = "",
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search MLflow runs across one or more experiment IDs."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            runs = client.search_runs(
                experiment_ids=experiment_ids,
                filter_string=filter_string or "",
                max_results=max_results,
            )
            return [
                {
                    "run_id": r.info.run_id,
                    "run_name": r.info.run_name,
                    "experiment_id": r.info.experiment_id,
                    "status": r.info.status,
                    "metrics": dict(r.data.metrics),
                    "params": dict(r.data.params),
                }
                for r in runs
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_get_run(run_id: str) -> dict[str, Any]:
        """Get full details for a single MLflow run."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            r = client.get_run(run_id)
            return {
                "run_id": r.info.run_id,
                "run_name": r.info.run_name,
                "experiment_id": r.info.experiment_id,
                "status": r.info.status,
                "start_time": r.info.start_time,
                "end_time": r.info.end_time,
                "metrics": dict(r.data.metrics),
                "params": dict(r.data.params),
                "tags": dict(r.data.tags),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_search_logged_models(
        experiment_ids: list[str],
        filter_string: str = "",
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search MLflow 3.x first-class LoggedModel entities."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            models = client.search_logged_models(
                experiment_ids=experiment_ids,
                filter_string=filter_string or None,
                max_results=max_results,
            )
            return [
                {
                    "model_id": getattr(m, "model_id", None),
                    "name": getattr(m, "name", None),
                    "experiment_id": getattr(m, "experiment_id", None),
                    "status": str(getattr(m, "status", "")),
                    "params": dict(getattr(m, "params", {}) or {}),
                    "metrics": [
                        {
                            "key": getattr(metric, "key", None),
                            "value": getattr(metric, "value", None),
                        }
                        for metric in (getattr(m, "metrics", None) or [])
                    ],
                }
                for m in models
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_list_prompts(
        filter_string: str = "",
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """List prompts in the MLflow 3.x Prompt Registry."""

        def _run() -> list[dict[str, Any]]:
            genai = _get_genai()
            prompts = genai.search_prompts(
                filter_string=filter_string or None,
                max_results=max_results,
            )
            return [
                {
                    "name": getattr(p, "name", None),
                    "description": getattr(p, "description", None),
                    "tags": dict(getattr(p, "tags", {}) or {}),
                    "creation_timestamp": getattr(p, "creation_timestamp", None),
                }
                for p in prompts
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_load_prompt(
        name: str,
        version_or_alias: str = "latest",
    ) -> dict[str, Any]:
        """Load a prompt version from MLflow Prompt Registry by name and version or alias."""

        def _run() -> dict[str, Any]:
            genai = _get_genai()
            if version_or_alias.isdigit():
                pv = genai.load_prompt(name, version=int(version_or_alias))
            elif version_or_alias == "latest":
                pv = genai.load_prompt(f"prompts:/{name}@latest")
            else:
                pv = genai.load_prompt(f"prompts:/{name}@{version_or_alias}")
            return {
                "name": getattr(pv, "name", name),
                "version": getattr(pv, "version", None),
                "template": getattr(pv, "template", None),
                "commit_message": getattr(pv, "commit_message", None),
                "tags": dict(getattr(pv, "tags", {}) or {}),
                "uri": getattr(pv, "uri", None),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_register_prompt(
        name: str,
        template: str,
        commit_message: str = "",
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Register a new prompt version (requires MLFLOW_ALLOW_MUTATIONS=true)."""
        _require_mlflow_mutations(settings)

        def _run() -> dict[str, Any]:
            genai = _get_genai()
            pv = genai.register_prompt(
                name=name,
                template=template,
                commit_message=commit_message or None,
                tags=tags,
            )
            return {
                "name": getattr(pv, "name", name),
                "version": getattr(pv, "version", None),
                "uri": getattr(pv, "uri", None),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_list_registered_models(max_results: int = 50) -> list[dict[str, Any]]:
        """List registered models from the configured MLflow/Unity Catalog Model Registry."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            models = client.search_registered_models(max_results=max_results)
            return [
                {
                    "name": m.name,
                    "description": getattr(m, "description", None),
                    "aliases": dict(getattr(m, "aliases", {}) or {}),
                    "tags": dict(getattr(m, "tags", {}) or {}),
                }
                for m in models
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_get_model_version_by_alias(name: str, alias: str) -> dict[str, Any]:
        """Get a registered model version by alias (e.g. 'champion', 'staging')."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            mv = client.get_model_version_by_alias(name, alias)
            return {
                "name": mv.name,
                "version": mv.version,
                "aliases": list(getattr(mv, "aliases", []) or []),
                "run_id": getattr(mv, "run_id", None),
                "source": getattr(mv, "source", None),
                "status": getattr(mv, "status", None),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_set_model_alias(name: str, alias: str, version: str) -> dict[str, Any]:
        """Set a registered model alias (requires MLFLOW_ALLOW_MUTATIONS=true)."""
        _require_mlflow_mutations(settings)

        def _run() -> dict[str, Any]:
            client = _get_client()
            client.set_registered_model_alias(name, alias, str(version))
            return {"name": name, "alias": alias, "version": str(version)}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_list_eval_datasets(
        experiment_ids: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """List MLflow 3.x GenAI evaluation datasets."""

        def _run() -> list[dict[str, Any]]:
            genai = _get_genai()
            datasets = genai.search_datasets(
                experiment_ids=experiment_ids,
                max_results=max_results,
            )
            return [
                {
                    "dataset_id": getattr(d, "dataset_id", None),
                    "name": getattr(d, "name", None),
                    "experiment_ids": list(getattr(d, "experiment_ids", []) or []),
                    "tags": dict(getattr(d, "tags", {}) or {}),
                }
                for d in datasets
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_get_eval_dataset(
        dataset_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get metadata and sample records for an MLflow 3.x GenAI evaluation dataset."""
        if not dataset_id and not name:
            raise ToolError("Provide either dataset_id or name")

        def _run() -> dict[str, Any]:
            genai = _get_genai()
            ds = genai.get_dataset(dataset_id=dataset_id, name=name)
            records = list(getattr(ds, "records", []) or [])
            return {
                "dataset_id": getattr(ds, "dataset_id", dataset_id),
                "name": getattr(ds, "name", name),
                "record_count": len(records),
                "records_preview": records[:10],
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_compare_runs(
        run_ids: list[str],
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare parameters, metrics, and statuses across multiple MLflow runs."""
        if not run_ids:
            raise ToolError("Provide at least one run_id")

        def _run() -> dict[str, Any]:
            client = _get_client()
            comparisons: list[dict[str, Any]] = []
            for rid in run_ids:
                r = client.get_run(rid)
                all_metrics = dict(r.data.metrics)
                selected = (
                    {k: all_metrics[k] for k in metrics if k in all_metrics}
                    if metrics
                    else all_metrics
                )
                comparisons.append(
                    {
                        "run_id": r.info.run_id,
                        "run_name": r.info.run_name,
                        "status": r.info.status,
                        "params": dict(r.data.params),
                        "metrics": selected,
                    }
                )
            return {"runs": comparisons, "count": len(comparisons)}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_get_prompt_versions(
        name: str,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """List versions, commit messages, and aliases for an MLflow Prompt Registry prompt."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            versions = client.search_prompt_versions(name=name, max_results=max_results)
            return [
                {
                    "name": getattr(v, "name", name),
                    "version": getattr(v, "version", None),
                    "commit_message": getattr(v, "commit_message", None),
                    "aliases": list(getattr(v, "aliases", []) or []),
                    "tags": dict(getattr(v, "tags", {}) or {}),
                }
                for v in versions
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_promote_model_alias(
        name: str,
        version: str,
        alias: str = "champion",
        min_metric_name: str | None = None,
        min_metric_value: float | None = None,
    ) -> dict[str, Any]:
        """Promote a model version alias with optional metric gating on its source run."""
        _require_mlflow_mutations(settings)

        def _run() -> dict[str, Any]:
            client = _get_client()
            checked_metric: dict[str, Any] | None = None
            if min_metric_name is not None and min_metric_value is not None:
                mv = client.get_model_version(name, str(version))
                run_id = getattr(mv, "run_id", None)
                if not run_id:
                    raise ToolError(
                        f"Model {name} v{version} has no linked run_id for metric gate check"
                    )
                run = client.get_run(run_id)
                actual = run.data.metrics.get(min_metric_name)
                if actual is None or float(actual) < min_metric_value:
                    raise ToolError(
                        f"Metric gate failed: {min_metric_name}={actual} < {min_metric_value}"
                    )
                checked_metric = {
                    "metric": min_metric_name,
                    "actual": float(actual),
                    "threshold": min_metric_value,
                    "run_id": run_id,
                }
            client.set_registered_model_alias(name, alias, str(version))
            return {
                "name": name,
                "version": str(version),
                "alias": alias,
                "promoted": True,
                "metricGate": checked_metric,
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def mlflow_stack_status() -> dict[str, Any]:
        """Inspect MLflow tracking, registry URI, and upstream mlflow[mcp] health."""
        import mlflow

        tracking_ok = False
        tracking_status: int | None = None
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{settings.mlflow.tracking_uri.rstrip('/')}/health")
                tracking_status = r.status_code
                tracking_ok = r.status_code == 200
        except Exception:
            tracking_ok = False

        upstream = await probe_mcp_http_endpoint(settings.mlflow.mcp_url)
        return {
            "mlflow_sdk_version": mlflow.__version__,
            "tracking_uri": settings.mlflow.tracking_uri,
            "tracking_healthy": tracking_ok,
            "tracking_status_code": tracking_status,
            "registry_uri": settings.effective_mlflow_registry_uri,
            "experiment_name": settings.mlflow.experiment_name,
            "tracing_enabled": settings.mlflow.tracing_enabled,
            "upstream_mcp": upstream,
        }

    return mcp
