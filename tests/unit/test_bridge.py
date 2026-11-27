"""Unit tests for the self-contained `mcp-stack bridge` stdio-to-HTTP module."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_stack.bridge import (
    build_target_url,
    load_gateway_token,
    parse_env_file,
    run_stdio_bridge,
)
from mcp_stack.cli import app


def test_parse_env_file_handles_quotes_comments_and_export(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "MCP_ANTIGRAVITY_AUTH_TOKEN='ag-token-123'",
                'export MCP_CLAUDE_AUTH_TOKEN="cl-token-456"',
                "MCP_CODEX_AUTH_TOKEN=cx-token-789",
                "MALFORMED_LINE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    parsed = parse_env_file(env_file)
    assert parsed == {
        "MCP_ANTIGRAVITY_AUTH_TOKEN": "ag-token-123",
        "MCP_CLAUDE_AUTH_TOKEN": "cl-token-456",
        "MCP_CODEX_AUTH_TOKEN": "cx-token-789",
    }


def test_build_target_url_variants() -> None:
    assert build_target_url() == "http://127.0.0.1:8090/profiles/core/mcp"
    assert build_target_url(profile="full") == "http://127.0.0.1:8090/mcp"
    assert build_target_url(server="printer") == "http://127.0.0.1:8090/servers/printer/mcp"
    assert (
        build_target_url(server="music_brain", base_url="http://127.0.0.1:8090/")
        == "http://127.0.0.1:8090/servers/music-brain/mcp"
    )
    assert (
        build_target_url(explicit_url="http://127.0.0.1:9000/custom/mcp", server="printer")
        == "http://127.0.0.1:9000/custom/mcp"
    )
    with pytest.raises(ValueError, match="Specify only one"):
        build_target_url(profile="core", server="printer")


def test_load_gateway_token_prefers_env_falls_back_to_dotenv_and_fails_closed(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MCP_ANTIGRAVITY_AUTH_TOKEN=from-dotenv\nMCP_DEFAULT_AUTH_TOKEN=restricted-default\n",
        encoding="utf-8",
    )

    assert (
        load_gateway_token(
            token_env_var="MCP_ANTIGRAVITY_AUTH_TOKEN",
            env_file=env_file,
            environ={"MCP_ANTIGRAVITY_AUTH_TOKEN": "from-environ"},
        )
        == "from-environ"
    )
    assert (
        load_gateway_token(
            token_env_var="MCP_ANTIGRAVITY_AUTH_TOKEN",
            env_file=env_file,
            environ={},
        )
        == "from-dotenv"
    )
    with pytest.raises(RuntimeError, match="MCP_CLAUDE_AUTH_TOKEN"):
        load_gateway_token(
            token_env_var="MCP_CLAUDE_AUTH_TOKEN",
            env_file=env_file,
            environ={},
        )


def test_run_stdio_bridge_wires_proxy_and_cli_fails_closed(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MCP_ANTIGRAVITY_AUTH_TOKEN=secret-ag\n", encoding="utf-8")

    mock_proxy = MagicMock()
    with (
        patch("mcp_stack.bridge.StreamableHttpTransport") as mock_transport_cls,
        patch("mcp_stack.bridge.create_proxy", return_value=mock_proxy) as mock_create_proxy,
        patch.dict("os.environ", {}, clear=True),
    ):
        run_stdio_bridge(
            server="omnigent",
            token_env_var="MCP_ANTIGRAVITY_AUTH_TOKEN",
            env_file=env_file,
        )

    mock_transport_cls.assert_called_once_with(
        url="http://127.0.0.1:8090/servers/omnigent/mcp",
        headers={"Authorization": "Bearer secret-ag"},
    )
    mock_create_proxy.assert_called_once_with(
        mock_transport_cls.return_value,
        name="mcp-workshop-gateway-omnigent",
    )
    mock_proxy.run.assert_called_once_with(transport="stdio", show_banner=False)

    runner = CliRunner()
    help_res = runner.invoke(
        app,
        ["bridge", "--help"],
        env={"NO_COLOR": "1", "TERM": "dumb"},
    )
    assert help_res.exit_code == 0
    plain_help = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", help_res.output)
    assert "--token-env-var" in plain_help

    missing_res = runner.invoke(
        app,
        [
            "bridge",
            "--profile",
            "core",
            "--token-env-var",
            "MCP_MISSING_TOKEN",
            "--env-file",
            str(env_file),
        ],
    )
    assert missing_res.exit_code == 2
    assert "MCP_MISSING_TOKEN" in missing_res.output
