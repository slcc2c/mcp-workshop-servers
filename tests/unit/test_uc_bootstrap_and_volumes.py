"""Unit tests for OSS UC bootstrap and bidirectional Memory <-> UC Volume sync."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.memory import create_memory_server
from mcp_stack.servers.unity_catalog import UCClientAdapter
from mcp_stack.uc_bootstrap import bootstrap_oss_unity_catalog


async def test_uc_bootstrap_idempotent_with_mocked_transport(make_settings) -> None:
    calls: list[tuple[str, str]] = []
    existing_catalog = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal existing_catalog
        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path.endswith("/catalogs/workshop"):
            if existing_catalog:
                return httpx.Response(200, json={"name": "workshop"})
            return httpx.Response(404, json={"message": "Not found"})
        if request.method == "POST" and request.url.path.endswith("/catalogs"):
            existing_catalog = True
            return httpx.Response(200, json={"name": "workshop"})
        if request.method == "GET" and request.url.path.endswith("/schemas/workshop.default"):
            return httpx.Response(404, json={"message": "Not found"})
        if request.method == "POST" and request.url.path.endswith("/schemas"):
            return httpx.Response(200, json={"full_name": "workshop.default"})
        vol_path = "volumes/workshop.default.memory_snapshots"
        if request.method == "GET" and vol_path in request.url.path:
            return httpx.Response(404, json={"message": "Not found"})
        if request.method == "POST" and request.url.path.endswith("/volumes"):
            return httpx.Response(200, json={"full_name": "workshop.default.memory_snapshots"})
        return httpx.Response(200, json={})

    settings = make_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_cli:
        adapter = UCClientAdapter(settings, http_client=http_cli)

        async def fake_fn_reg(fn, cat: str, sch: str) -> str:
            return "registered"

        first = await bootstrap_oss_unity_catalog(
            settings, adapter=adapter, uc_fn_client_factory=fake_fn_reg
        )
        assert first["catalog"]["status"] == "created"
        assert first["volume"]["status"] == "created"
        assert first["functions"]["workshop.default.add_numbers"] == "registered"

        second = await bootstrap_oss_unity_catalog(
            settings, adapter=adapter, uc_fn_client_factory=fake_fn_reg
        )
        assert second["catalog"]["status"] == "exists"


async def test_memory_uc_volume_export_and_import_roundtrip(make_settings, tmp_path: Path) -> None:
    vol_root = tmp_path / "uc_volumes"
    snap_dir = vol_root / "memory_snapshots"
    snap_dir.mkdir(parents=True)

    settings = make_settings()
    settings.unity_catalog.volume_local_prefix_map = {
        "file:///home/unitycatalog/etc/data/external/workshop": str(vol_root),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/volumes/workshop.default.memory_snapshots"):
            return httpx.Response(
                200,
                json={
                    "full_name": "workshop.default.memory_snapshots",
                    "storage_location": (
                        "file:///home/unitycatalog/etc/data/external/workshop/memory_snapshots"
                    ),
                },
            )
        return httpx.Response(404, json={"message": "Not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_cli:
        adapter = UCClientAdapter(settings, http_client=http_cli)
        srv = create_memory_server(settings, uc_adapter=adapter)
        async with Client(srv) as client:
            stored = await client.call_tool(
                "memory_store",
                {"content": "UC Volume persisted note", "tags": ["uc", "volume"]},
            )
            entry_id = json.loads(stored.content[0].text)["id"]

            exported = await client.call_tool(
                "memory_export",
                {"format": "json", "uc_volume_name": "workshop.default.memory_snapshots"},
            )
            exp_payload = json.loads(exported.content[0].text)
            assert exp_payload["ucVolume"] == "workshop.default.memory_snapshots"
            snap_file = Path(exp_payload["exportedFile"])
            assert snap_file.exists() and snap_file.is_relative_to(snap_dir)

            await client.call_tool("memory_delete", {"id": entry_id})

            with pytest.raises(ToolError, match="escapes"):
                await client.call_tool(
                    "memory_import",
                    {
                        "uc_volume_name": "workshop.default.memory_snapshots",
                        "filename": "../../etc/passwd",
                    },
                )

            imported = await client.call_tool(
                "memory_import",
                {"uc_volume_name": "workshop.default.memory_snapshots"},
            )
            imp_payload = json.loads(imported.content[0].text)
            assert imp_payload["importedCount"] == 1

            restored = await client.call_tool("memory_get", {"id": entry_id})
            assert "UC Volume persisted note" in restored.content[0].text
