"""Unit tests for Omnigent unified memory backend in Memory MCP server."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.servers.memory import OmnigentMemoryAdapter, create_memory_server

pytestmark = pytest.mark.unit


def test_omnigent_memory_adapter_crud_and_unreachable_error() -> None:
    entries: dict[str, dict[str, Any]] = {
        "/feedback/workflow-rules": {
            "path": "/feedback/workflow-rules",
            "content": "Never commit without permission.",
            "description": "Workflow rules",
            "created_at": 100,
            "updated_at": 100,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path == "/v1/memory/entries" and request.method == "GET":
            assert "path_prefix" not in request.url.params
            prefix = request.url.params.get("prefix", "")
            matched = [
                {**v, "content": ""}
                for k, v in sorted(entries.items())
                if not prefix or k.startswith(prefix)
            ]
            return httpx.Response(200, json={"entries": matched, "next_page_token": None})
        if url_path == "/v1/memory/entry" and request.method == "GET":
            p = request.url.params.get("path", "")
            if p not in entries:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=entries[p])
        if url_path == "/v1/memory/entry" and request.method == "PUT":
            assert request.headers.get("Origin") == "http://omni.test"
            body = json.loads(request.content)
            p = body["path"]
            entries[p] = {
                "path": p,
                "content": body["content"],
                "description": body.get("description"),
                "created_at": 101,
                "updated_at": 102,
            }
            return httpx.Response(200, json=entries[p])
        if url_path == "/v1/memory/entry" and request.method == "DELETE":
            assert request.headers.get("Origin") == "http://omni.test"
            p = request.url.params.get("path", "")
            existed = entries.pop(p, None) is not None
            return httpx.Response(200, json={"deleted": existed})
        if url_path == "/v1/memory/search" and request.method == "POST":
            body = json.loads(request.content)
            q = body["query"].lower()
            hits = [
                {"entry": v, "score": 0.9}
                for v in entries.values()
                if q in v["content"].lower() or q in v["path"].lower()
            ]
            return httpx.Response(200, json={"hits": hits})
        return httpx.Response(404, json={"detail": "unknown"})

    settings = MCPStackSettings.model_validate(
        {
            "memory": {"backend": "omnigent"},
            "omnigent": {"base_url": "http://omni.test", "allow_mutations": True},
        }
    )
    adapter = OmnigentMemoryAdapter(settings, transport=httpx.MockTransport(handler))

    stored = adapter.store(
        "Use :8090 for MCP.",
        metadata={"path": "/projects/printer/notes", "description": "Printer note"},
    )
    assert stored["path"] == "/projects/printer/notes"
    assert stored["backend"] == "omnigent"

    searched = adapter.search("8090")
    assert searched["count"] == 1
    assert searched["entries"][0]["path"] == "/projects/printer/notes"

    fetched = adapter.get("feedback/workflow-rules")
    assert fetched["path"] == "/feedback/workflow-rules"
    assert "Never commit" in fetched["content"]

    tags = adapter.list_tags()
    assert {"tag": "/feedback/workflow-rules", "count": 1} in tags
    assert {"tag": "/projects/printer", "count": 1} in tags

    updated = adapter.update("/projects/printer/notes", content="Updated printer note")
    assert updated["updated"] is True
    assert adapter.get("/projects/printer/notes")["content"] == "Updated printer note"

    deleted = adapter.delete("/projects/printer/notes")
    assert deleted["deleted"] is True

    # Unreachable Omnigent must raise ToolError instead of falling back silently
    def fail_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    broken = OmnigentMemoryAdapter(settings, transport=httpx.MockTransport(fail_handler))
    with pytest.raises(ToolError, match="OMNIGENT_MEMORY_UNAVAILABLE"):
        broken.search("workflow")

    # Factory honors MEMORY_BACKEND=omnigent cleanly
    srv = create_memory_server(settings)
    assert srv is not None


def test_omnigent_memory_adapter_falls_back_to_client_scan_on_404() -> None:
    entries: dict[str, dict[str, Any]] = {
        "/projects/Music-brain/notes": {
            "path": "/projects/Music-brain/notes",
            "content": "MIDI bridge and stems live in Music-brain.",
            "description": "Music-brain project notes",
            "created_at": 100,
            "updated_at": 100,
        },
        "/feedback/workflow-rules": {
            "path": "/feedback/workflow-rules",
            "content": "Route MCP servers through :8090.",
            "description": "Workstation workflow rules",
            "created_at": 100,
            "updated_at": 100,
        },
    }

    def handler_404_search(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/memory/search" and request.method == "POST":
            return httpx.Response(
                404,
                json={"error": {"code": "not_found", "message": "Memory search is not available"}},
            )
        if request.url.path == "/v1/memory/entries" and request.method == "GET":
            assert "path_prefix" not in request.url.params
            prefix = request.url.params.get("prefix", "")
            matched = [
                {**v, "content": ""}
                for k, v in sorted(entries.items())
                if not prefix or k.startswith(prefix)
            ]
            return httpx.Response(200, json={"entries": matched, "next_page_token": None})
        if request.url.path == "/v1/memory/entry" and request.method == "GET":
            p = request.url.params.get("path", "")
            return httpx.Response(200, json=entries[p])
        return httpx.Response(404)

    settings = MCPStackSettings.model_validate(
        {"memory": {"backend": "omnigent"}, "omnigent": {"base_url": "http://omni.test"}}
    )
    adapter = OmnigentMemoryAdapter(settings, transport=httpx.MockTransport(handler_404_search))
    res = adapter.search("Music-brain")
    assert res["backend"] == "omnigent"
    assert res["searchMode"] == "client_scan"
    assert res["count"] == 1
    assert res["entries"][0]["path"] == "/projects/Music-brain/notes"
    assert "MIDI bridge" in res["entries"][0]["content"]
