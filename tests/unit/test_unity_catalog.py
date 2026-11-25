"""Unit tests for the Unity Catalog MCP server."""

from __future__ import annotations

import json
import types

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.core.auth import caller_uc_token_var
from mcp_stack.servers.unity_catalog import (
    UCClientAdapter,
    create_unity_catalog_server,
    sync_uc_function_tools,
)

pytestmark = pytest.mark.unit


async def test_unity_catalog_read_tools_and_obo_header(make_settings) -> None:
    settings = make_settings()

    with respx.mock(assert_all_called=False) as router:
        route_cats = router.get("http://uc.test:8080/api/2.1/unity-catalog/catalogs").mock(
            return_value=httpx.Response(200, json={"catalogs": [{"name": "unity"}]})
        )
        router.get("http://uc.test:8080/api/2.1/unity-catalog/schemas").mock(
            return_value=httpx.Response(200, json={"schemas": [{"name": "default"}]})
        )
        router.get("http://uc.test:8080/api/2.1/unity-catalog/tables").mock(
            return_value=httpx.Response(200, json={"tables": [{"name": "events"}]})
        )
        router.get("http://uc.test:8080/api/2.1/unity-catalog/volumes").mock(
            return_value=httpx.Response(200, json={"volumes": [{"name": "artifacts"}]})
        )
        router.get(
            "http://uc.test:8080/api/2.1/unity-catalog/models/unity.default.clf/versions/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"model_name": "clf", "version": 1, "run_id": "run-abc"},
            )
        )

        class FakeRun:
            info = types.SimpleNamespace(run_id="run-abc", experiment_id="1", status="FINISHED")
            data = types.SimpleNamespace(
                metrics={"rmse": 0.12}, params={"lr": "0.01"}, tags={"env": "dev"}
            )

        class FakeMlflowClient:
            def get_run(self, run_id: str):
                assert run_id == "run-abc"
                return FakeRun()

            def search_traces(self, **_kwargs):
                return [
                    types.SimpleNamespace(
                        info=types.SimpleNamespace(
                            trace_id="tr-1", state="OK", execution_duration=15
                        )
                    )
                ]

        async with httpx.AsyncClient() as http_cli:
            adapter = UCClientAdapter(settings, http_client=http_cli)
            mcp = create_unity_catalog_server(
                settings,
                adapter=adapter,
                mlflow_client_factory=FakeMlflowClient,
            )

            tok = caller_uc_token_var.set("obo-secret-token")
            try:
                async with Client(mcp) as client:
                    cats = await client.call_tool("uc_list_catalogs", {})
                    assert "unity" in str(cats)
                    auth_hdr = route_cats.calls[0].request.headers["Authorization"]
                    assert auth_hdr == "Bearer obo-secret-token"

                    schemas = await client.call_tool("uc_list_schemas", {"catalog_name": "unity"})
                    assert "default" in str(schemas)

                    tables = await client.call_tool(
                        "uc_list_tables", {"catalog_name": "unity", "schema_name": "default"}
                    )
                    assert "events" in str(tables)

                    vols = await client.call_tool(
                        "uc_list_volumes", {"catalog_name": "unity", "schema_name": "default"}
                    )
                    assert "artifacts" in str(vols)

                    lineage = await client.call_tool(
                        "uc_get_model_lineage",
                        {"full_name": "unity.default.clf", "version": 1},
                    )
                    payload = json.loads(lineage.content[0].text)
                    assert payload["mlflow_run"]["metrics"]["rmse"] == 0.12
                    assert payload["mlflow_traces"][0]["trace_id"] == "tr-1"
            finally:
                caller_uc_token_var.reset(tok)


async def test_unity_catalog_mutation_gating_and_dynamic_functions(make_settings) -> None:
    settings = make_settings()
    executed: list[tuple[str, dict]] = []

    def fake_exec(name: str, params: dict):
        executed.append((name, params))
        return {"function": name, "value": params.get("x", 0) * 2}

    with respx.mock(assert_all_called=False) as router:
        router.get("http://uc.test:8080/api/2.1/unity-catalog/functions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "functions": [
                        {
                            "full_name": "unity.default.double_val",
                            "comment": "Double an integer",
                            "input_params": {
                                "parameters": [
                                    {"name": "x", "type_name": "INT", "comment": "Input"}
                                ]
                            },
                        }
                    ]
                },
            )
        )

        async with httpx.AsyncClient() as http_cli:
            adapter = UCClientAdapter(settings, http_client=http_cli)
            mcp = create_unity_catalog_server(
                settings, adapter=adapter, function_executor=fake_exec
            )
            sync_out = await sync_uc_function_tools(
                mcp, adapter, settings, function_executor=fake_exec
            )
            assert "uc_fn_unity_default_double_val" in sync_out["registered"]

            async with Client(mcp) as client:
                # Mutation blocked by default
                with pytest.raises(ToolError, match="mutations are disabled"):
                    await client.call_tool("uc_create_catalog", {"name": "blocked_cat"})

                # Disallowed schema execution blocked
                with pytest.raises(ToolError, match="UC_FUNCTION_ALLOWLIST"):
                    await client.call_tool(
                        "uc_execute_function",
                        {"full_name": "other_cat.other_schema.fn", "parameters": {}},
                    )

                # Allowlisted execution succeeds
                res = await client.call_tool(
                    "uc_execute_function",
                    {"full_name": "unity.default.double_val", "parameters": {"x": 7}},
                )
                assert json.loads(res.content[0].text)["value"] == 14

                # Dynamic UC function tool works directly
                dyn_res = await client.call_tool("uc_fn_unity_default_double_val", {"x": 21})
                assert json.loads(dyn_res.content[0].text)["value"] == 42
