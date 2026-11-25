"""Unit tests for the MLflow 3.x MCP server and MCP Registry manifest sync."""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import UpstreamServerConfig
from mcp_stack.registry import sync_mcp_registry, sync_upstream_registry
from mcp_stack.servers.mlflow_server import create_mlflow_server

pytestmark = pytest.mark.unit


async def test_mlflow_server_tools_and_mutation_gating(make_settings) -> None:
    settings = make_settings()

    class FakeClient:
        def search_experiments(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    experiment_id="1",
                    name="mcp-workshop-servers",
                    lifecycle_stage="active",
                    artifact_location="/mlartifacts",
                )
            ]

        def search_logged_models(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    model_id="m-1",
                    name="router-v3",
                    experiment_id="1",
                    status="READY",
                    params={"temp": "0.1"},
                    metrics=[types.SimpleNamespace(key="accuracy", value=0.95)],
                )
            ]

        def get_model_version_by_alias(self, name: str, alias: str):
            return types.SimpleNamespace(
                name=name,
                version="3",
                aliases=[alias],
                run_id="run-99",
                source="mlflow-artifacts:/3/model",
                status="READY",
            )

        def set_registered_model_alias(self, name: str, alias: str, version: str):
            self.last_alias = (name, alias, version)

    class FakeGenAI:
        def search_prompts(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    name="support-prompt",
                    description="Support prompt",
                    tags={"team": "ai"},
                    creation_timestamp=12345,
                )
            ]

        def load_prompt(self, uri: str, version=None):
            return types.SimpleNamespace(
                name="support-prompt",
                version=version or 2,
                template="Hello {{name}}",
                commit_message="v2",
                tags={},
                uri=uri,
            )

        def search_datasets(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    dataset_id="ds-1",
                    name="qwen-eval",
                    experiment_ids=["1"],
                    tags={},
                )
            ]

    mcp = create_mlflow_server(
        settings, client_factory=FakeClient, genai_module=FakeGenAI()
    )

    async with Client(mcp) as client:
        tool_names = {t.name for t in await client.list_tools()}
        for removed in ("mlflow_list_experiments", "mlflow_search_runs", "mlflow_get_run"):
            assert removed not in tool_names

        logged = await client.call_tool(
            "mlflow_search_logged_models", {"experiment_ids": ["1"]}
        )
        assert json.loads(logged.content[0].text)[0]["model_id"] == "m-1"

        prompt = await client.call_tool(
            "mlflow_load_prompt", {"name": "support-prompt", "version_or_alias": "champion"}
        )
        assert json.loads(prompt.content[0].text)["template"] == "Hello {{name}}"

        mv = await client.call_tool(
            "mlflow_get_model_version_by_alias",
            {"name": "unity.default.clf", "alias": "champion"},
        )
        assert json.loads(mv.content[0].text)["version"] == "3"

        datasets = await client.call_tool("mlflow_list_eval_datasets", {})
        assert "qwen-eval" in str(datasets)

        # Mutations blocked by default
        with pytest.raises(ToolError, match="mutations are disabled"):
            await client.call_tool(
                "mlflow_register_prompt",
                {"name": "p", "template": "hi"},
            )
        with pytest.raises(ToolError, match="mutations are disabled"):
            await client.call_tool(
                "mlflow_set_model_alias",
                {"name": "m", "alias": "champion", "version": "1"},
            )


def test_registry_sync_dry_run_and_mlflow_versions(make_settings, tmp_path: Path) -> None:
    settings = make_settings()
    out_dir = tmp_path / "manifests"

    dry = sync_mcp_registry(settings, dry_run=True, output_dir=out_dir)
    assert dry["dry_run"] is True
    assert (out_dir / "gateway.server.json").exists()
    assert (out_dir / "unity-catalog.server.json").exists()

    # Older MLflow (< 3.15) without register_mcp_server skips gracefully
    legacy_genai = types.SimpleNamespace()
    skipped = sync_mcp_registry(
        settings, dry_run=False, output_dir=out_dir, genai_module=legacy_genai
    )
    assert skipped["results"]["gateway"]["status"] == "skipped_unsupported_mlflow"

    # MLflow >= 3.15 registers all manifests and sets production aliases & tags
    registered_calls: list[dict] = []
    alias_calls: list[tuple[str, str, str]] = []
    tag_calls: list[tuple[str, str, str]] = []

    class ModernGenAI:
        @staticmethod
        def register_mcp_server(**kwargs):
            registered_calls.append(kwargs)
            return types.SimpleNamespace(version="2.0.0")

        @staticmethod
        def set_mcp_server_alias(*, name: str, alias: str, version: str):
            alias_calls.append((name, alias, version))

        @staticmethod
        def set_mcp_server_tag(*, name: str, key: str, value: str):
            tag_calls.append((name, key, value))

    synced = sync_mcp_registry(
        settings, dry_run=False, output_dir=out_dir, genai_module=ModernGenAI()
    )
    assert synced["results"]["gateway"]["status"] == "registered"
    assert synced["results"]["gateway"]["alias"] == "production"
    assert synced["results"]["gateway"]["tags"]["scope"] == "gateway"
    assert len(registered_calls) == len(synced["results"])
    assert len(alias_calls) == len(synced["results"])
    assert tag_calls

    # Configured gateway token is forwarded on register + refresh
    from mcp_stack.core.config import ClientPolicy

    authed_settings = make_settings()
    authed_settings.gateway.clients = {
        "tok-claude-test": ClientPolicy(client_id="claude", client_name="Claude"),
    }
    refresh_calls: list[dict] = []

    class ExistingGenAI:
        @staticmethod
        def register_mcp_server(**kwargs):
            raise RuntimeError("Server already exists")

        @staticmethod
        def refresh_mcp_server_version_tools(**kwargs):
            refresh_calls.append(kwargs)
            return types.SimpleNamespace(version="2.0.0")

    refreshed = sync_mcp_registry(
        authed_settings, dry_run=False, output_dir=out_dir, genai_module=ExistingGenAI()
    )
    assert refreshed["results"]["gateway"]["status"] == "already_exists_refreshed"
    assert refresh_calls
    assert refresh_calls[0]["mcp_server_access_headers"] == {
        "Authorization": "Bearer tok-claude-test"
    }


def test_sync_upstream_registry_repairs_tags_and_aliases(make_settings) -> None:
    settings = make_settings()
    settings.gateway.upstream_servers = {
        "printer": UpstreamServerConfig(
            transport="http",
            url="https://studio.example.invalid/mcp",
            registry_name="io.github.slcc2c/printer",
            governance="preview-before-print",
        ),
        "music-brain": UpstreamServerConfig(
            transport="stdio",
            command="echo",
            registry_name="io.github.spencer-cook/music-brain-private",
            governance="read-only-default",
        ),
        "tonverk-studio": UpstreamServerConfig(
            transport="stdio",
            command="echo",
            registry_name="io.github.slcc2c/tonverk-studio",
            governance="external-proxy",
        ),
    }

    aliases_set: list[tuple[str, str, str]] = []
    tags_set: list[tuple[str, str, str]] = []
    registered: list[str] = []

    class FakeTrackingClient:
        @staticmethod
        def search_mcp_servers(**_kw):
            return [
                types.SimpleNamespace(
                    name="io.github.slcc2c/printer",
                    aliases={"production": "1.20261015.323+92595bfe1"},
                ),
                types.SimpleNamespace(
                    name="io.github.spencer-cook/music-brain-private",
                    aliases={"observed-local": "0.1.2+private.abc"},
                ),
            ]

    class FakeGenAI:
        @staticmethod
        def register_mcp_server(*, server_json, **_kw):
            registered.append(server_json["name"])
            return types.SimpleNamespace(version=server_json["version"])

        @staticmethod
        def set_mcp_server_alias(*, name: str, alias: str, version: str):
            aliases_set.append((name, alias, version))

        @staticmethod
        def set_mcp_server_tag(*, name: str, key: str, value: str):
            tags_set.append((name, key, value))

    res = sync_upstream_registry(
        settings, genai_module=FakeGenAI(), tracking_client=FakeTrackingClient()
    )
    assert res["printer"]["status"] == "updated_existing"
    assert res["printer"]["version"] == "1.20261015.323+92595bfe1"
    assert (
        "io.github.spencer-cook/music-brain-private",
        "production",
        "0.1.2+private.abc",
    ) in aliases_set
    assert "io.github.slcc2c/tonverk-studio" in registered
    assert (
        "io.github.slcc2c/printer",
        "gateway_route",
        "http://127.0.0.1:8090/servers/printer/mcp",
    ) in tags_set
