"""Unit tests for the async GitHub REST v3 MCP server."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

from mcp_stack.servers.github import create_github_server

pytestmark = pytest.mark.unit


async def test_github_missing_token_raises_actionable_error(make_settings) -> None:
    settings = make_settings()
    mcp = create_github_server(settings)

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="GitHub token is not configured"):
            await client.call_tool("github_get_user", {})


async def test_github_tools_with_mocked_rest_api(make_settings) -> None:
    settings = make_settings()
    settings.github.token = SecretStr("ghp_test_token")

    with respx.mock(assert_all_called=False) as router:
        router.get("https://api.github.test/user").mock(
            return_value=httpx.Response(
                200, json={"login": "slcc2c", "name": "Spencer", "public_repos": 12}
            )
        )
        router.get("https://api.github.test/repos/slcc2c/mcp-server").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "mcp-server",
                    "full_name": "slcc2c/mcp-server",
                    "stargazers_count": 5,
                    "forks_count": 1,
                    "default_branch": "main",
                    "html_url": "https://github.com/slcc2c/mcp-server",
                },
            )
        )
        router.post("https://api.github.test/repos/slcc2c/mcp-server/issues").mock(
            return_value=httpx.Response(
                201,
                json={
                    "number": 42,
                    "title": "Port complete",
                    "state": "open",
                    "html_url": "https://github.com/slcc2c/mcp-server/issues/42",
                },
            )
        )
        router.get("https://api.github.test/search/code").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "items": [
                        {
                            "name": "unity_catalog.py",
                            "path": "src/mcp_stack/servers/unity_catalog.py",
                            "repository": {"full_name": "slcc2c/mcp-server"},
                            "html_url": "https://github.com/slcc2c/mcp-server/blob/main/unity_catalog.py",
                        }
                    ],
                },
            )
        )

        async with httpx.AsyncClient() as http_cli:
            mcp = create_github_server(settings, http_client=http_cli)
            async with Client(mcp) as client:
                user = await client.call_tool("github_get_user", {})
                assert json.loads(user.content[0].text)["login"] == "slcc2c"

                repo = await client.call_tool(
                    "github_get_repo", {"owner": "slcc2c", "repo": "mcp-server"}
                )
                assert json.loads(repo.content[0].text)["defaultBranch"] == "main"

                issue = await client.call_tool(
                    "github_create_issue",
                    {"owner": "slcc2c", "repo": "mcp-server", "title": "Port complete"},
                )
                assert json.loads(issue.content[0].text)["number"] == 42

                code = await client.call_tool(
                    "github_search_code", {"query": "unity_catalog"}
                )
                assert json.loads(code.content[0].text)["totalCount"] == 1
