"""Unit tests for the sandboxed Filesystem MCP server."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.filesystem import create_filesystem_server

pytestmark = pytest.mark.unit


async def test_filesystem_crud_and_strict_sandbox(make_settings, tmp_path: Path) -> None:
    settings = make_settings()
    allowed_root = settings.filesystem.allowed_paths[0]

    # Sibling directory sharing prefix (would have bypassed legacy startsWith!)
    evil_sibling = Path(f"{allowed_root}-evil")
    evil_sibling.mkdir(parents=True, exist_ok=True)
    (evil_sibling / "secret.txt").write_text("nope", encoding="utf-8")

    # Symlink escaping sandbox
    escape_link = allowed_root / "escape"
    os.symlink(evil_sibling, escape_link)

    mcp = create_filesystem_server(settings)

    async with Client(mcp) as client:
        # Prefix bypass rejected
        with pytest.raises(ToolError, match="outside allowed directories"):
            await client.call_tool("fs_read_file", {"path": str(evil_sibling / "secret.txt")})

        # Traversal rejected
        with pytest.raises(ToolError, match="outside allowed directories"):
            await client.call_tool("fs_read_file", {"path": "../outside.txt"})

        # Symlink escape rejected
        with pytest.raises(ToolError, match="escapes sandbox"):
            await client.call_tool("fs_read_file", {"path": "escape/secret.txt"})

        # Normal write, read, copy, move, search, delete
        await client.call_tool(
            "fs_write_file",
            {"path": "notes/hello.txt", "content": "hello modern stack"},
        )
        read_res = await client.call_tool("fs_read_file", {"path": "notes/hello.txt"})
        assert json.loads(read_res.content[0].text)["content"] == "hello modern stack"

        await client.call_tool(
            "fs_copy_file",
            {"source": "notes/hello.txt", "destination": "notes/copy.txt"},
        )
        await client.call_tool(
            "fs_move_file",
            {"source": "notes/copy.txt", "destination": "notes/moved.txt"},
        )
        search_res = await client.call_tool(
            "fs_search_files", {"path": "notes", "query": "modern stack"}
        )
        assert json.loads(search_res.content[0].text)["count"] == 2

        listed = await client.call_tool("fs_list_directory", {"path": "notes"})
        assert json.loads(listed.content[0].text)["count"] == 2

        await client.call_tool("fs_delete_file", {"path": "notes/moved.txt"})
        exists = await client.call_tool("fs_exists", {"path": "notes/moved.txt"})
        assert json.loads(exists.content[0].text)["exists"] is False
