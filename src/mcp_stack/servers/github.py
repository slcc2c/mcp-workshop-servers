"""GitHub REST API v3 MCP server."""

from __future__ import annotations

import contextlib
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack import __version__
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware


def create_github_server(
    settings: MCPStackSettings,
    *,
    secret_resolver: SecretResolver | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastMCP:
    """Create the async GitHub REST v3 MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("github")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "github"))

    def _get_token() -> str:
        resolved = resolver.resolve(settings.github.token)
        if not resolved:
            raise ToolError(
                "GitHub token is not configured. Set GITHUB_PERSONAL_ACCESS_TOKEN or GITHUB_TOKEN."
            )
        return resolved

    async def _gh_request(
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token = _get_token()
        url = f"{settings.github.api_url.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"mcp-workshop-stack/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        if http_client is not None:
            resp = await http_client.request(
                method, url, params=clean_params, json=json_body, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.request(
                    method, url, params=clean_params, json=json_body, headers=headers
                )

        if resp.status_code >= 400:
            detail = resp.text[:400]
            with contextlib.suppress(Exception):
                detail = resp.json().get("message") or detail
            raise ToolError(f"GitHub API {method} {path} failed ({resp.status_code}): {detail}")
        return resp.json() if resp.content else {}

    @mcp.tool()
    async def github_get_repo(owner: str, repo: str) -> dict[str, Any]:
        """Get repository metadata."""
        data = await _gh_request("GET", f"/repos/{owner}/{repo}")
        return {
            "name": data.get("name"),
            "fullName": data.get("full_name"),
            "description": data.get("description"),
            "private": data.get("private"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "language": data.get("language"),
            "defaultBranch": data.get("default_branch"),
            "url": data.get("html_url"),
            "cloneUrl": data.get("clone_url"),
        }

    @mcp.tool()
    async def github_list_repos(
        type: Literal["all", "owner", "member"] = "owner",
        sort: Literal["created", "updated", "pushed", "full_name"] = "updated",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repositories for the authenticated GitHub user."""
        data = await _gh_request(
            "GET",
            "/user/repos",
            params={"type": type, "sort": sort, "per_page": min(max(1, per_page), 100)},
        )
        return [
            {
                "name": r.get("name"),
                "fullName": r.get("full_name"),
                "description": r.get("description"),
                "private": r.get("private"),
                "url": r.get("html_url"),
                "updatedAt": r.get("updated_at"),
            }
            for r in data
        ]

    @mcp.tool()
    async def github_create_repo(
        name: str,
        description: str | None = None,
        private: bool = False,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        """Create a repository for the authenticated user."""
        body: dict[str, Any] = {
            "name": name,
            "private": private,
            "auto_init": auto_init,
        }
        if description is not None:
            body["description"] = description
        data = await _gh_request("POST", "/user/repos", json_body=body)
        return {
            "name": data.get("name"),
            "fullName": data.get("full_name"),
            "url": data.get("html_url"),
            "cloneUrl": data.get("clone_url"),
        }

    @mcp.tool()
    async def github_list_issues(
        owner: str,
        repo: str,
        state: Literal["open", "closed", "all"] = "open",
        labels: str | None = None,
        sort: Literal["created", "updated", "comments"] = "created",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List issues in a GitHub repository."""
        data = await _gh_request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={
                "state": state,
                "labels": labels,
                "sort": sort,
                "per_page": min(max(1, per_page), 100),
            },
        )
        return [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "url": item.get("html_url"),
                "author": (item.get("user") or {}).get("login"),
                "createdAt": item.get("created_at"),
                "labels": [
                    lbl.get("name") if isinstance(lbl, dict) else lbl
                    for lbl in (item.get("labels") or [])
                ],
            }
            for item in data
        ]

    @mcp.tool()
    async def github_create_issue(
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue in a repository."""
        payload: dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        data = await _gh_request("POST", f"/repos/{owner}/{repo}/issues", json_body=payload)
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "url": data.get("html_url"),
            "state": data.get("state"),
        }

    @mcp.tool()
    async def github_create_pr(
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str | None = None,
    ) -> dict[str, Any]:
        """Create a pull request."""
        payload: dict[str, Any] = {"title": title, "head": head, "base": base}
        if body is not None:
            payload["body"] = body
        data = await _gh_request("POST", f"/repos/{owner}/{repo}/pulls", json_body=payload)
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "url": data.get("html_url"),
            "state": data.get("state"),
            "draft": data.get("draft"),
        }

    @mcp.tool()
    async def github_list_branches(owner: str, repo: str) -> list[dict[str, Any]]:
        """List repository branches."""
        data = await _gh_request(
            "GET", f"/repos/{owner}/{repo}/branches", params={"per_page": 100}
        )
        return [
            {
                "name": b.get("name"),
                "protected": b.get("protected"),
                "commit": (b.get("commit") or {}).get("sha"),
            }
            for b in data
        ]

    @mcp.tool()
    async def github_create_branch(
        owner: str,
        repo: str,
        branch: str,
        from_ref: str = "main",
    ) -> dict[str, Any]:
        """Create a branch from a source branch name."""
        ref_data = await _gh_request(
            "GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_ref}"
        )
        sha = (ref_data.get("object") or {}).get("sha")
        if not sha:
            raise ToolError(f"Could not resolve SHA for branch '{from_ref}'")
        created = await _gh_request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json_body={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        return {
            "branch": branch,
            "sha": (created.get("object") or {}).get("sha"),
            "url": created.get("url"),
        }

    @mcp.tool()
    async def github_list_commits(
        owner: str,
        repo: str,
        sha: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository commits."""
        data = await _gh_request(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params={"sha": sha, "per_page": min(max(1, per_page), 100)},
        )
        return [
            {
                "sha": c.get("sha"),
                "message": (c.get("commit") or {}).get("message"),
                "author": ((c.get("commit") or {}).get("author") or {}).get("name"),
                "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
                "url": c.get("html_url"),
            }
            for c in data
        ]

    @mcp.tool()
    async def github_list_workflow_runs(
        owner: str,
        repo: str,
        status: str | None = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """List GitHub Actions workflow runs for a repository."""
        data = await _gh_request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs",
            params={"status": status, "per_page": min(max(1, per_page), 100)},
        )
        return [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "createdAt": run.get("created_at"),
                "url": run.get("html_url"),
            }
            for run in (data.get("workflow_runs") or [])
        ]

    @mcp.tool()
    async def github_search_code(query: str, per_page: int = 30) -> dict[str, Any]:
        """Search code across GitHub."""
        data = await _gh_request(
            "GET",
            "/search/code",
            params={"q": query, "per_page": min(max(1, per_page), 100)},
        )
        return {
            "totalCount": data.get("total_count", 0),
            "items": [
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "repository": (item.get("repository") or {}).get("full_name"),
                    "url": item.get("html_url"),
                }
                for item in (data.get("items") or [])
            ],
        }

    @mcp.tool()
    async def github_search_issues(query: str, per_page: int = 30) -> dict[str, Any]:
        """Search issues and pull requests across GitHub."""
        data = await _gh_request(
            "GET",
            "/search/issues",
            params={"q": query, "per_page": min(max(1, per_page), 100)},
        )
        return {
            "totalCount": data.get("total_count", 0),
            "items": [
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "url": item.get("html_url"),
                    "repository": "/".join(
                        str(item.get("repository_url", "")).split("/")[-2:]
                    ),
                }
                for item in (data.get("items") or [])
            ],
        }

    @mcp.tool()
    async def github_get_user() -> dict[str, Any]:
        """Get the authenticated GitHub user profile."""
        data = await _gh_request("GET", "/user")
        return {
            "login": data.get("login"),
            "name": data.get("name"),
            "email": data.get("email"),
            "publicRepos": data.get("public_repos"),
            "privateRepos": data.get("total_private_repos"),
            "followers": data.get("followers"),
            "following": data.get("following"),
        }

    return mcp
