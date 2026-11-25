"""Unit tests for the SQLite + FTS5 Memory MCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client

from mcp_stack.servers.memory import MemoryStore, create_memory_server

pytestmark = pytest.mark.unit


async def test_memory_crud_fts_relationships_and_legacy_import(
    make_settings, tmp_path: Path
) -> None:
    settings = make_settings()
    legacy_json = settings.memory.legacy_json_path
    legacy_json.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "entries": [
                    {
                        "id": "mem_legacy_1",
                        "content": "Atelier MLflow runs on port 5002",
                        "type": "fact",
                        "timestamp": "2026-05-31T17:26:32.509Z",
                        "tags": ["mlflow", "atelier"],
                        "metadata": {"source": "legacy"},
                        "relationships": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = MemoryStore(settings.memory.db_path, legacy_json)
    mcp = create_memory_server(settings, store=store)

    async with Client(mcp) as client:
        # Legacy entry auto-imported
        got_legacy = await client.call_tool("memory_get", {"id": "mem_legacy_1"})
        assert "5002" in str(got_legacy)

        # Store related entry
        s1 = await client.call_tool(
            "memory_store",
            {
                "content": "Unity Catalog REST API runs on port 8080",
                "type": "fact",
                "tags": ["unity-catalog", "governance"],
                "related_to": ["mem_legacy_1"],
            },
        )
        new_id = json.loads(s1.content[0].text)["id"]

        # FTS search
        search_res = await client.call_tool(
            "memory_search", {"query": "Unity Catalog", "tags": ["governance"]}
        )
        parsed_search = json.loads(search_res.content[0].text)
        assert parsed_search["totalResults"] == 1
        assert parsed_search["results"][0]["id"] == new_id

        # Bidirectional graph traversal
        related = await client.call_tool(
            "memory_get_related", {"id": "mem_legacy_1", "depth": 1}
        )
        assert json.loads(related.content[0].text)["relatedEntries"][0]["id"] == new_id

        # Export to UC volume directory
        export_dir = tmp_path / "uc_vol"
        exp = await client.call_tool(
            "memory_export",
            {"format": "json", "uc_volume_path": str(export_dir)},
        )
        exp_payload = json.loads(exp.content[0].text)
        assert Path(exp_payload["exportedFile"]).exists()

        # Update & delete
        upd = await client.call_tool(
            "memory_update",
            {"id": new_id, "content": "Updated UC fact", "tags": ["updated"]},
        )
        assert json.loads(upd.content[0].text)["content"] == "Updated UC fact"

        tags = await client.call_tool("memory_list_tags", {})
        assert "updated" in str(tags)

        deleted = await client.call_tool("memory_delete", {"id": new_id})
        assert json.loads(deleted.content[0].text)["deleted"] is True
