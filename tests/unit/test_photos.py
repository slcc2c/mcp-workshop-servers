"""Unit tests for the macOS Photos MCP server (sandbox, JXA runner, schemas)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.photos import create_photos_server
from mcp_stack.servers.photos_jxa import (
    PHOTOS_JXA_SCRIPT,
    OsaExecResult,
    OsaScriptPhotosRunner,
    PhotosOperation,
    PhotosScriptError,
)

pytestmark = pytest.mark.unit


class ExportCaptureRunner:
    def __init__(self) -> None:
        self.operation: PhotosOperation | None = None
        self.args: dict[str, Any] | None = None

    async def run_operation(self, operation: PhotosOperation, args: dict[str, Any]) -> Any:
        self.operation = operation
        self.args = args
        if operation == "list_albums":
            return {
                "total": 1,
                "albums": [
                    {"id": "a1", "name": "Favorites", "isSmart": True, "assetCount": 3}
                ],
            }
        dest = args.get("destinationPath", "")
        return {
            "destinationPath": str(dest),
            "exported": [{"assetId": "asset-1", "filePath": f"{dest}/img.jpg"}],
            "failed": [],
        }


async def test_photos_export_sandbox_invariants(
    make_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings()
    settings.photos.export_root = None
    monkeypatch.delenv("PHOTOS_EXPORT_ROOT", raising=False)

    mcp_no_root = create_photos_server(settings, runner=ExportCaptureRunner())
    async with Client(mcp_no_root) as client:
        with pytest.raises(ToolError, match="PHOTOS_EXPORT_ROOT_REQUIRED"):
            await client.call_tool("photos_export_assets", {"asset_ids": ["asset-1"]})

    export_root = tmp_path / "export_root"
    export_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, export_root / "escape-link")
    leaked_nested = outside / "nested"

    monkeypatch.setenv("PHOTOS_EXPORT_ROOT", str(export_root))
    runner = ExportCaptureRunner()
    mcp = create_photos_server(settings, runner=runner)

    async with Client(mcp) as client:
        # Traversal rejected
        with pytest.raises(ToolError, match="PHOTOS_EXPORT_PATH_DENIED"):
            await client.call_tool(
                "photos_export_assets",
                {"asset_ids": ["asset-1"], "destination_subdir": "../outside"},
            )

        # Symlink escape rejected AND must never create nested dirs outside root
        with pytest.raises(ToolError, match="PHOTOS_EXPORT_PATH_DENIED"):
            await client.call_tool(
                "photos_export_assets",
                {"asset_ids": ["asset-1"], "destination_subdir": "escape-link/nested"},
            )
        assert not leaked_nested.exists()

        # Valid relative path succeeds
        ok = await client.call_tool(
            "photos_export_assets",
            {"asset_ids": ["asset-1"], "destination_subdir": "safe/session"},
        )
        payload = json.loads(ok.content[0].text)
        assert payload["destinationPath"] == os.path.join(
            os.path.realpath(export_root), "safe/session"
        )
        assert runner.operation == "export_assets"


async def test_photos_osascript_runner_parses_payload_and_maps_errors() -> None:
    async def ok_exec(args, env, _timeout):
        assert args[:3] == ["osascript", "-l", "JavaScript"]
        assert env["MCP_PHOTOS_OPERATION"] == "list_albums"
        return OsaExecResult(stdout='{"ok": true, "result": {"total": 0, "albums": []}}', stderr="")

    runner = OsaScriptPhotosRunner(executor=ok_exec)
    res = await runner.run_operation("list_albums", {"includeSmart": True})
    assert res == {"total": 0, "albums": []}

    async def denied_exec(_args, _env, _timeout):
        raise RuntimeError("Not authorized to send Apple events to Photos.")

    denied_runner = OsaScriptPhotosRunner(executor=denied_exec)
    with pytest.raises(PhotosScriptError) as exc_info:
        await denied_runner.run_operation("list_albums", {})
    assert exc_info.value.photos_code == "PHOTOS_AUTOMATION_DENIED"


def test_photos_jxa_script_preserves_js_escapes_and_compiles(tmp_path: Path) -> None:
    assert "application can\\'t be found" in PHOTOS_JXA_SCRIPT
    if sys.platform == "darwin" and shutil.which("osacompile"):
        out_scpt = tmp_path / "photos_check.scpt"
        proc = subprocess.run(
            ["osacompile", "-l", "JavaScript", "-o", str(out_scpt), "-"],
            input=PHOTOS_JXA_SCRIPT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
