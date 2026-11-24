"""Subprocess stdio compliance tests verifying stdout is 100% pure JSON-RPC."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


async def test_stdio_subprocess_stdout_is_pure_json_rpc(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["MEMORY_DB_PATH"] = str(tmp_path / "stdio-memory.db")
    env["MEMORY_LEGACY_JSON_PATH"] = str(tmp_path / "missing.json")
    env["MLFLOW_TRACING_ENABLED"] = "false"
    env["MCP_LOG_LEVEL"] = "INFO"

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "mcp_stack.cli",
        "serve",
        "memory",
        "--transport",
        "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-test", "version": "1.0"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "memory_store",
                    "arguments": {"content": "clean stdio", "type": "fact"},
                },
            },
        ]

        responses: dict[int, dict] = {}

        async def _send(msg: dict) -> None:
            proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))  # type: ignore[union-attr]
            await proc.stdin.drain()  # type: ignore[union-attr]

        await _send(messages[0])
        line1 = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        parsed1 = json.loads(line1.decode("utf-8"))
        assert parsed1["jsonrpc"] == "2.0"
        responses[parsed1["id"]] = parsed1

        await _send(messages[1])
        await _send(messages[2])
        line2 = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        parsed2 = json.loads(line2.decode("utf-8"))
        assert parsed2["jsonrpc"] == "2.0"
        responses[parsed2["id"]] = parsed2

        await _send(messages[3])
        line3 = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        parsed3 = json.loads(line3.decode("utf-8"))
        assert parsed3["jsonrpc"] == "2.0"
        responses[parsed3["id"]] = parsed3

        assert "serverInfo" in responses[1]["result"]
        tool_names = {t["name"] for t in responses[2]["result"]["tools"]}
        assert "memory_store" in tool_names
        assert "stored" in str(responses[3]["result"])
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)
