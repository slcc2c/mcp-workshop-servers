"""Unit tests for the FastMCP Mac mini SSH delegation server."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MacMiniSettings
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.servers.mac_mini import create_mac_mini_server

pytestmark = pytest.mark.unit


def _asgi_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        kwargs["follow_redirects"] = False
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


def _write_fake_ssh(tmp_path: Path, capture_path: Path) -> Path:
    fake_ssh = tmp_path / "fake-ssh"
    fake_ssh.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys

capture = {str(capture_path)!r}
stdin_data = sys.stdin.read()
with open(capture, "w", encoding="utf-8") as fh:
    json.dump({{"argv": sys.argv[1:], "stdin": stdin_data}}, fh)

if os.environ.get("FAKE_MINI_FAIL") == "1":
    print(json.dumps({{"error": "boom from runner"}}))
    sys.exit(1)

print(json.dumps({{"ok": True, "argv": sys.argv[1:], "stdin": stdin_data, "jobs": []}}))
""",
        encoding="utf-8",
    )
    fake_ssh.chmod(fake_ssh.stat().st_mode | stat.S_IXUSR)
    return fake_ssh


async def test_mac_mini_mcp_tools_end_to_end(make_settings, tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    fake_ssh = _write_fake_ssh(tmp_path, capture)
    settings = make_settings()
    settings.mac_mini = MacMiniSettings(
        ssh_host="spencers-mac-mini",
        ssh_bin=str(fake_ssh),
        remote_bin="mini-agy-runner",
        ssh_timeout_s=10.0,
        allow_mutations=True,
    )

    srv = create_mac_mini_server(settings)
    async with Client(srv) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == {
            "mini_doctor",
            "mini_list_jobs",
            "mini_job_status",
            "mini_start_job",
            "mini_resume_job",
            "mini_cancel_job",
            "mini_cleanup_job",
        }

        doc = await client.call_tool("mini_doctor", {})
        assert doc.data["ok"] is True

        prompt = "Line 1 with 'single' & \"double\"\n$(whoami)"
        await client.call_tool(
            "mini_start_job",
            {
                "repo": "atelier",
                "prompt": prompt,
                "runtime": "agy",
                "branch": "agy/test'branch",
                "mode": "plan",
                "effort": "high",
                "sandbox": True,
            },
        )
        captured = json.loads(capture.read_text(encoding="utf-8"))
        assert captured["stdin"] == prompt
        assert captured["argv"][:-1] == [
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "spencers-mac-mini",
        ]
        remote_cmd = captured["argv"][-1]
        assert "--runtime agy" in remote_cmd
        assert "--prompt-file -" in remote_cmd
        assert "--sandbox" in remote_cmd
        assert "'agy/test'\"'\"'branch'" in remote_cmd

        await client.call_tool("mini_resume_job", {"job_id": "abc", "prompt": "follow up"})
        resumed = json.loads(capture.read_text(encoding="utf-8"))
        assert resumed["stdin"] == "follow up"
        assert "resume --prompt-file - abc" in resumed["argv"][-1]

        await client.call_tool(
            "mini_cleanup_job", {"job_id": "abc", "delete_branch": True, "force": True}
        )
        cleaned = json.loads(capture.read_text(encoding="utf-8"))
        assert "cleanup --delete-branch --force abc" in cleaned["argv"][-1]


async def test_mac_mini_mutation_guard_and_gateway_mount(
    make_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture.json"
    fake_ssh = _write_fake_ssh(tmp_path, capture)
    settings = make_settings()
    settings.gateway.enabled_servers = ["mac_mini"]
    settings.gateway.profiles = {"core": ["mac_mini"], "ops": ["mac_mini"]}
    settings.mac_mini = MacMiniSettings(
        ssh_host="spencers-mac-mini",
        ssh_bin=str(fake_ssh),
        allow_mutations=False,
    )

    gw_app = build_gateway_app(settings, compose_upstream_on_startup=False)
    transport = StreamableHttpTransport(
        "http://testserver/servers/mac-mini/mcp",
        httpx_client_factory=_asgi_factory(gw_app),
    )
    async with gw_app.router.lifespan_context(gw_app), Client(transport) as client:
        listed = await client.call_tool("mini_list_jobs", {"active": True, "limit": 5})
        assert listed.data["jobs"] == []

        with pytest.raises(ToolError, match="MAC_MINI_ALLOW_MUTATIONS=false"):
            await client.call_tool("mini_start_job", {"repo": "atelier", "prompt": "hi"})

    monkeypatch.setenv("FAKE_MINI_FAIL", "1")
    srv = create_mac_mini_server(settings)
    async with Client(srv) as client:
        with pytest.raises(ToolError, match="boom from runner"):
            await client.call_tool("mini_doctor", {})
