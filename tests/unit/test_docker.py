"""Unit tests for the Docker MCP server."""

from __future__ import annotations

import json
import types

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.docker_server import create_docker_server

pytestmark = pytest.mark.unit


async def test_docker_server_allowlist_limits_and_daemon_unavailable(make_settings) -> None:
    settings = make_settings()

    def down_client():
        raise ConnectionError("Cannot connect to Docker daemon")

    down_mcp = create_docker_server(settings, client_factory=down_client)
    async with Client(down_mcp) as client:
        with pytest.raises(ToolError, match="Docker daemon is unavailable"):
            await client.call_tool("docker_list_containers", {})

    created_kwargs: list[dict] = []

    class FakeContainers:
        def list(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    short_id="abc123",
                    name="web",
                    status="running",
                    image=types.SimpleNamespace(tags=["nginx:latest"]),
                )
            ]

        def run(self, **kwargs):
            created_kwargs.append(kwargs)
            return types.SimpleNamespace(short_id="new999", name="py-job", status="running")

    class FakeDocker:
        containers = FakeContainers()

        def ping(self):
            return True

    up_mcp = create_docker_server(settings, client_factory=FakeDocker)
    async with Client(up_mcp) as client:
        listed = await client.call_tool("docker_list_containers", {})
        assert json.loads(listed.content[0].text)[0]["name"] == "web"

        with pytest.raises(ToolError, match="DOCKER_ALLOWED_IMAGES"):
            await client.call_tool(
                "docker_create_container", {"image": "untrusted/miner:latest"}
            )

        res = await client.call_tool(
            "docker_create_container", {"image": "python:3.12-slim", "name": "py-job"}
        )
        payload = json.loads(res.content[0].text)
        assert payload["memLimit"] == "2g"
        assert payload["cpus"] == 1.0
        assert created_kwargs[0]["mem_limit"] == "2g"
        assert created_kwargs[0]["nano_cpus"] == 1_000_000_000
