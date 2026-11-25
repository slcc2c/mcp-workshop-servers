"""Mocked unit tests for Kubernetes, Jupyter, and Xcode Tier-2 MCP servers."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.servers.jupyter_server import create_jupyter_server
from mcp_stack.servers.kubernetes_server import create_kubernetes_server
from mcp_stack.servers.xcodebuild import create_xcodebuild_server


async def test_kubernetes_namespace_allowlist_and_read_only_gate(make_settings) -> None:
    settings = make_settings()
    settings.kubernetes.allowed_namespaces = ["default"]

    pod = types.SimpleNamespace(
        metadata=types.SimpleNamespace(name="api-0"),
        status=types.SimpleNamespace(phase="Running"),
        spec=types.SimpleNamespace(node_name="node-a"),
    )

    class FakeCore:
        def list_namespaced_pod(self, ns, **_kwargs):
            return types.SimpleNamespace(items=[pod])

    srv = create_kubernetes_server(settings, api_factory=lambda: {"core": FakeCore()})
    async with Client(srv) as client:
        pods = await client.call_tool("k8s_list_pods", {"namespace": "default"})
        assert json.loads(pods.content[0].text)["pods"][0]["name"] == "api-0"

        with pytest.raises(ToolError, match="K8S_ALLOWED_NAMESPACES"):
            await client.call_tool("k8s_list_pods", {"namespace": "kube-system"})

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("k8s_delete_pod", {"name": "api-0", "namespace": "default"})


async def test_jupyter_read_export_and_execution_gate(make_settings, tmp_path: Path) -> None:
    import nbformat

    settings = make_settings()
    nb_dir = tmp_path / "notebooks"
    nb_dir.mkdir(parents=True)
    settings.jupyter.notebook_dir = nb_dir

    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x = 1 + 1")])
    nb_file = nb_dir / "demo.ipynb"
    nbformat.write(nb, str(nb_file))

    srv = create_jupyter_server(settings)
    async with Client(srv) as client:
        opened = await client.call_tool("jupyter_open_notebook", {"path": "demo.ipynb"})
        assert json.loads(opened.content[0].text)["cells"][0]["source"] == "x = 1 + 1"

        exported = await client.call_tool(
            "jupyter_export", {"path": "demo.ipynb", "format": "python"}
        )
        assert "x = 1 + 1" in json.loads(exported.content[0].text)["content"]

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("jupyter_execute_cell", {"code": "print(1)"})

        with pytest.raises(ToolError, match="escapes allowed roots"):
            await client.call_tool("jupyter_open_notebook", {"path": "/etc/passwd"})


async def test_xcodebuild_sandbox_and_runner_on_macos(
    make_settings, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    settings = make_settings()
    ws = tmp_path / "ios_app"
    (ws / "Demo.xcodeproj").mkdir(parents=True)
    settings.xcode.allowed_roots = [ws]

    async def fake_runner(argv: list[str], cwd: Path | None, timeout_s: float):
        if "simctl" in argv:
            return 0, json.dumps({"devices": {}}), ""
        return 0, json.dumps({"project": {"schemes": ["Demo"]}}), ""

    srv = create_xcodebuild_server(settings, cmd_runner=fake_runner)
    async with Client(srv) as client:
        found = await client.call_tool("xcode_discover_projects", {"root_path": str(ws)})
        assert len(json.loads(found.content[0].text)["projects"]) == 1

        sims = await client.call_tool("simulator_list", {})
        assert "devices" in json.loads(sims.content[0].text)

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool(
                "xcode_build_project",
                {"project_path": str(ws / "Demo.xcodeproj"), "scheme": "Demo"},
            )


async def test_gateway_composes_all_tier2_servers(make_settings, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    settings = make_settings()
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False
    app = build_gateway_app(settings)
    slugs = [r.path for r in app.routes if hasattr(r, "path")]
    for expected in (
        "/servers/postgresql/mcp",
        "/servers/redis/mcp",
        "/servers/mongodb/mcp",
        "/servers/neo4j/mcp",
        "/servers/kubernetes/mcp",
        "/servers/jupyter/mcp",
        "/servers/xcodebuild/mcp",
    ):
        assert expected in slugs
