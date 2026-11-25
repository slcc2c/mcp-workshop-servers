"""Unit tests for MLflow 3.x comparison, prompt version history, and alias promotion."""

from __future__ import annotations

import json
import types

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.mlflow_server import create_mlflow_server


async def test_mlflow_compare_prompt_versions_and_gated_promotion(make_settings) -> None:
    settings = make_settings()
    settings.mlflow.allow_mutations = True
    alias_calls: list[tuple[str, str, str]] = []

    class FakeClient:
        def get_run(self, run_id: str):
            metrics = {"quality": 0.92} if run_id == "run-good" else {"quality": 0.40}
            return types.SimpleNamespace(
                info=types.SimpleNamespace(
                    run_id=run_id, run_name=f"name-{run_id}", status="FINISHED"
                ),
                data=types.SimpleNamespace(params={"model": "qwen"}, metrics=metrics),
            )

        def search_prompt_versions(self, name: str, max_results: int = 20):
            return [
                types.SimpleNamespace(
                    name=name,
                    version=2,
                    commit_message="refine rubric",
                    aliases=["champion"],
                    tags={"stage": "prod"},
                )
            ]

        def get_model_version(self, name: str, version: str):
            run_id = "run-good" if version == "2" else "run-bad"
            return types.SimpleNamespace(name=name, version=version, run_id=run_id)

        def set_registered_model_alias(self, name: str, alias: str, version: str):
            alias_calls.append((name, alias, version))

    srv = create_mlflow_server(settings, client_factory=lambda: FakeClient())
    async with Client(srv) as client:
        comp = await client.call_tool(
            "mlflow_compare_runs",
            {"run_ids": ["run-good", "run-bad"], "metrics": ["quality"]},
        )
        assert len(json.loads(comp.content[0].text)["runs"]) == 2

        pvs = await client.call_tool("mlflow_get_prompt_versions", {"name": "grader"})
        assert json.loads(pvs.content[0].text)[0]["version"] == 2

        with pytest.raises(ToolError, match="Metric gate failed"):
            await client.call_tool(
                "mlflow_promote_model_alias",
                {
                    "name": "m",
                    "version": "1",
                    "alias": "champion",
                    "min_metric_name": "quality",
                    "min_metric_value": 0.8,
                },
            )

        ok = await client.call_tool(
            "mlflow_promote_model_alias",
            {
                "name": "m",
                "version": "2",
                "alias": "champion",
                "min_metric_name": "quality",
                "min_metric_value": 0.8,
            },
        )
        assert json.loads(ok.content[0].text)["promoted"] is True
        assert alias_calls == [("m", "champion", "2")]
