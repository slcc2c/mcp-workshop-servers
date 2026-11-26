"""Async FastMCP server delegating headless Antigravity jobs to spencers-mac-mini."""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware


def create_mac_mini_server(settings: MCPStackSettings) -> FastMCP:
    """Create the async Mac mini SSH delegation MCP server."""
    mcp = FastMCP("mac_mini")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "mac_mini"))

    def _require_mutations(action: str) -> None:
        if not settings.mac_mini.allow_mutations:
            raise ToolError(
                "Mac mini mutations are disabled (MAC_MINI_ALLOW_MUTATIONS=false); "
                f"cannot {action}."
            )

    def _require_nonempty(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ToolError(f"Missing or empty required parameter '{field}'.")
        return value

    async def _run_runner(
        runner_args: list[str],
        *,
        stdin_text: str | None = None,
    ) -> dict[str, Any]:
        cfg = settings.mac_mini
        ssh_argv = [
            cfg.ssh_bin,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            cfg.ssh_host,
            shlex.join([cfg.remote_bin, *runner_args]),
        ]
        try:
            stdin_mode = (
                asyncio.subprocess.PIPE
                if stdin_text is not None
                else asyncio.subprocess.DEVNULL
            )
            proc = await asyncio.create_subprocess_exec(
                *ssh_argv,
                stdin=stdin_mode,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdin_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=cfg.ssh_timeout_s,
            )
        except TimeoutError as exc:
            with_kill = locals().get("proc")
            if with_kill is not None and with_kill.returncode is None:
                with_kill.kill()
                await with_kill.wait()
            raise ToolError(
                f"SSH command to '{cfg.ssh_host}' timed out after {cfg.ssh_timeout_s}s."
            ) from exc
        except OSError as exc:
            raise ToolError(f"Failed to execute '{cfg.ssh_bin}': {exc}") from exc

        stdout = stdout_b.decode("utf-8", errors="replace").strip()
        stderr = stderr_b.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            detail_parts = [f"mini-agy-runner exited {proc.returncode}"]
            if stdout:
                try:
                    parsed_err = json.loads(stdout)
                    if isinstance(parsed_err, dict) and parsed_err.get("error"):
                        detail_parts.append(str(parsed_err["error"]))
                    else:
                        detail_parts.append(stdout)
                except json.JSONDecodeError:
                    detail_parts.append(stdout)
            if stderr:
                detail_parts.append(stderr)
            raise ToolError("; ".join(detail_parts))

        if not stdout:
            return {"ok": True}
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ToolError(f"Invalid JSON from mini-agy-runner: {exc}: {stdout[:200]}") from exc
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}

    @mcp.tool()
    async def mini_doctor() -> dict[str, Any]:
        """Check mini-agy-runner, agy CLI, Remote Control, git, Python, and dirs on Mac mini."""
        return await _run_runner(["doctor"])

    @mcp.tool()
    async def mini_list_jobs(
        active: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List delegated mini-agy-runner jobs on Mac mini, newest first."""
        argv = ["list"]
        if active:
            argv.append("--active")
        if limit is not None:
            if limit < 0:
                raise ToolError("'limit' must be non-negative.")
            argv.extend(["--limit", str(limit)])
        return await _run_runner(argv)

    @mcp.tool()
    async def mini_job_status(
        job_id: str,
        tail: int = 20,
    ) -> dict[str, Any]:
        """Get live status, PID health, conversation_id, git status, and events for a job."""
        clean_id = _require_nonempty(job_id, "job_id")
        if tail < 0:
            raise ToolError("'tail' must be non-negative.")
        return await _run_runner(["status", "--tail", str(tail), clean_id])

    @mcp.tool()
    async def mini_start_job(
        repo: str,
        prompt: str,
        runtime: Literal["agy"] = "agy",
        branch: str | None = None,
        base_ref: str | None = None,
        mode: Literal["auto", "accept-edits", "plan"] | None = None,
        model: str | None = None,
        effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None,
        sandbox: bool = True,
        timeout: str | None = None,
        no_worktree: bool = False,
    ) -> dict[str, Any]:
        """Start an async headless worker job in an isolated git worktree on Mac mini."""
        _require_mutations("start a delegated Mac mini job")
        clean_repo = _require_nonempty(repo, "repo")
        clean_prompt = _require_nonempty(prompt, "prompt")
        argv = ["start", "--repo", clean_repo, "--runtime", runtime]
        for flag, value in (
            ("--branch", branch),
            ("--base-ref", base_ref),
            ("--mode", mode),
            ("--model", model),
            ("--effort", effort),
            ("--timeout", timeout),
        ):
            if isinstance(value, str) and value:
                argv.extend([flag, value])
        if sandbox:
            argv.append("--sandbox")
        if no_worktree:
            argv.append("--no-worktree")
        argv.extend(["--prompt-file", "-"])
        return await _run_runner(argv, stdin_text=clean_prompt)

    @mcp.tool()
    async def mini_resume_job(
        job_id: str,
        prompt: str,
        mode: Literal["auto", "accept-edits", "plan"] | None = None,
        model: str | None = None,
        effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None,
    ) -> dict[str, Any]:
        """Send a follow-up prompt to a finished Mac mini job using its conversation_id."""
        _require_mutations("resume a delegated Mac mini job")
        clean_id = _require_nonempty(job_id, "job_id")
        clean_prompt = _require_nonempty(prompt, "prompt")
        argv = ["resume", "--prompt-file", "-"]
        for flag, value in (("--mode", mode), ("--model", model), ("--effort", effort)):
            if isinstance(value, str) and value:
                argv.extend([flag, value])
        argv.append(clean_id)
        return await _run_runner(argv, stdin_text=clean_prompt)

    @mcp.tool()
    async def mini_cancel_job(job_id: str) -> dict[str, Any]:
        """Terminate a running delegated job on Mac mini."""
        _require_mutations("cancel a delegated Mac mini job")
        clean_id = _require_nonempty(job_id, "job_id")
        return await _run_runner(["cancel", clean_id])

    @mcp.tool()
    async def mini_cleanup_job(
        job_id: str,
        delete_branch: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Remove the isolated git worktree for a finished Mac mini job."""
        _require_mutations("clean up a delegated Mac mini job")
        clean_id = _require_nonempty(job_id, "job_id")
        argv = ["cleanup"]
        if delete_branch:
            argv.append("--delete-branch")
        if force:
            argv.append("--force")
        argv.append(clean_id)
        return await _run_runner(argv)

    return mcp
