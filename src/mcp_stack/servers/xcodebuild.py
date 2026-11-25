"""macOS host-only Xcode / Swift / Simulator FastMCP server with argv-only execution."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware

CmdRunner = Callable[[list[str], Path | None, float], Awaitable[tuple[int, str, str]]]


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise ToolError("Xcode MCP server is supported only on macOS (darwin).")


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.xcode.allow_mutations:
        raise ToolError(
            "Xcode build/simulator mutations are disabled by policy. "
            "Set XCODE_ALLOW_MUTATIONS=true to enable builds, boots, installs, or launches."
        )


def _sandbox_path(settings: MCPStackSettings, path: str) -> Path:
    roots = (
        [r.resolve() for r in settings.xcode.allowed_roots]
        if settings.xcode.allowed_roots
        else [p.resolve() for p in settings.filesystem.allowed_paths]
    )
    resolved = Path(path).resolve()
    if not any(resolved.is_relative_to(r) for r in roots):
        raise ToolError(f"Path '{path}' is outside allowed Xcode workspace roots.")
    return resolved


async def _default_runner(
    argv: list[str], cwd: Path | None, timeout_s: float
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ToolError(f"Command timed out after {timeout_s}s: {argv[0]}") from exc
    return proc.returncode or 0, stdout_b.decode("utf-8", errors="replace"), stderr_b.decode(
        "utf-8", errors="replace"
    )


def create_xcodebuild_server(
    settings: MCPStackSettings,
    *,
    cmd_runner: CmdRunner | None = None,
) -> FastMCP:
    """Create the macOS host-only Xcode / Swift / Simulator MCP server."""
    runner = cmd_runner or _default_runner
    mcp = FastMCP("xcodebuild")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "xcodebuild"))

    async def _exec(argv: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
        _require_macos()
        code, out, err = await runner(argv, cwd, settings.xcode.timeout_seconds)
        if code != 0:
            raise ToolError(f"{argv[0]} failed (exit {code}): {(err or out)[:500]}")
        return {"command": argv[0], "stdout": out, "stderr": err}

    @mcp.tool()
    async def xcode_discover_projects(root_path: str) -> dict[str, Any]:
        """Discover .xcodeproj, .xcworkspace, and Package.swift files under an allowed root."""
        root = _sandbox_path(settings, root_path)

        def _scan() -> dict[str, list[str]]:
            projects = [str(p) for p in root.rglob("*.xcodeproj")][:50]
            workspaces = [str(p) for p in root.rglob("*.xcworkspace")][:50]
            swift_pkgs = [str(p) for p in root.rglob("Package.swift")][:50]
            return {
                "projects": projects,
                "workspaces": workspaces,
                "swiftPackages": swift_pkgs,
            }

        return await asyncio.to_thread(_scan)

    @mcp.tool()
    async def xcode_build_project(
        project_path: str,
        scheme: str,
        configuration: str = "Debug",
        destination: str | None = None,
    ) -> dict[str, Any]:
        """Build an Xcode project/workspace with xcodebuild."""
        _require_mutations(settings)
        proj = _sandbox_path(settings, project_path)
        flag = "-workspace" if proj.suffix == ".xcworkspace" else "-project"
        argv = ["xcodebuild", flag, str(proj), "-scheme", scheme, "-configuration", configuration]
        if destination:
            argv.extend(["-destination", destination])
        argv.append("build")
        return await _exec(argv, cwd=proj.parent)

    @mcp.tool()
    async def xcode_show_build_settings(
        project_path: str,
        scheme: str | None = None,
    ) -> dict[str, Any]:
        """Inspect resolved xcodebuild settings in JSON format."""
        proj = _sandbox_path(settings, project_path)
        flag = "-workspace" if proj.suffix == ".xcworkspace" else "-project"
        argv = ["xcodebuild", flag, str(proj)]
        if scheme:
            argv.extend(["-scheme", scheme])
        argv.extend(["-showBuildSettings", "-json"])
        res = await _exec(argv, cwd=proj.parent)
        try:
            return {"settings": json.loads(res["stdout"])}
        except Exception:
            return res

    @mcp.tool()
    async def xcode_list_schemes(project_path: str) -> dict[str, Any]:
        """List Xcode schemes and configurations for a project or workspace."""
        proj = _sandbox_path(settings, project_path)
        flag = "-workspace" if proj.suffix == ".xcworkspace" else "-project"
        res = await _exec(["xcodebuild", flag, str(proj), "-list", "-json"], cwd=proj.parent)
        try:
            return dict(json.loads(res["stdout"]))
        except Exception:
            return res

    @mcp.tool()
    async def xcode_clean_project(project_path: str, scheme: str) -> dict[str, Any]:
        """Clean Xcode build products."""
        _require_mutations(settings)
        proj = _sandbox_path(settings, project_path)
        flag = "-workspace" if proj.suffix == ".xcworkspace" else "-project"
        return await _exec(["xcodebuild", flag, str(proj), "-scheme", scheme, "clean"])

    @mcp.tool()
    async def swift_build_package(
        package_path: str,
        configuration: str = "debug",
    ) -> dict[str, Any]:
        """Build a Swift Package Manager package."""
        _require_mutations(settings)
        pkg = _sandbox_path(settings, package_path)
        return await _exec(["swift", "build", "-c", configuration], cwd=pkg)

    @mcp.tool()
    async def swift_test_package(package_path: str) -> dict[str, Any]:
        """Run swift test for a Swift package."""
        _require_mutations(settings)
        pkg = _sandbox_path(settings, package_path)
        return await _exec(["swift", "test"], cwd=pkg)

    @mcp.tool()
    async def swift_run_executable(
        package_path: str,
        target: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a Swift package executable target."""
        _require_mutations(settings)
        pkg = _sandbox_path(settings, package_path)
        return await _exec(["swift", "run", target, *(args or [])], cwd=pkg)

    @mcp.tool()
    async def simulator_list() -> dict[str, Any]:
        """List available CoreSimulator runtimes and devices."""
        res = await _exec(["xcrun", "simctl", "list", "--json"])
        try:
            return dict(json.loads(res["stdout"]))
        except Exception:
            return res

    @mcp.tool()
    async def simulator_boot(udid: str) -> dict[str, Any]:
        """Boot an iOS/tvOS/watchOS simulator by UDID."""
        _require_mutations(settings)
        return await _exec(["xcrun", "simctl", "boot", udid])

    @mcp.tool()
    async def simulator_install_app(udid: str, app_path: str) -> dict[str, Any]:
        """Install an .app bundle into a booted simulator."""
        _require_mutations(settings)
        app = _sandbox_path(settings, app_path)
        return await _exec(["xcrun", "simctl", "install", udid, str(app)])

    @mcp.tool()
    async def simulator_launch_app(udid: str, bundle_id: str) -> dict[str, Any]:
        """Launch an installed app inside a simulator by bundle identifier."""
        _require_mutations(settings)
        return await _exec(["xcrun", "simctl", "launch", udid, bundle_id])

    @mcp.tool()
    async def simulator_screenshot(udid: str, output_path: str) -> dict[str, Any]:
        """Capture a simulator screenshot into an allowed workspace path."""
        _require_mutations(settings)
        dest = _sandbox_path(settings, output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        res = await _exec(["xcrun", "simctl", "io", udid, "screenshot", str(dest)])
        return {"outputPath": str(dest), **res}

    @mcp.tool()
    async def device_list() -> dict[str, Any]:
        """List connected physical Apple devices via devicectl."""
        return await _exec(["xcrun", "devicectl", "list", "devices"])

    @mcp.tool()
    async def device_install_app(device_id: str, app_path: str) -> dict[str, Any]:
        """Install an app bundle onto a connected physical device."""
        _require_mutations(settings)
        app = _sandbox_path(settings, app_path)
        return await _exec(
            ["xcrun", "devicectl", "device", "install", "app", "--device", device_id, str(app)]
        )

    @mcp.tool()
    async def device_launch_app(device_id: str, bundle_id: str) -> dict[str, Any]:
        """Launch an app on a connected physical device."""
        _require_mutations(settings)
        return await _exec(
            ["xcrun", "devicectl", "device", "process", "launch", "--device", device_id, bundle_id]
        )

    @mcp.tool()
    async def app_get_bundle_id(app_path: str) -> dict[str, Any]:
        """Read CFBundleIdentifier from an .app bundle's Info.plist."""
        app = _sandbox_path(settings, app_path)
        plist_path = app / "Info.plist"
        res = await _exec(
            ["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleIdentifier", str(plist_path)]
        )
        return {"appPath": str(app), "bundleId": res["stdout"].strip()}

    @mcp.tool()
    async def xcode_create_project(directory: str, name: str) -> dict[str, Any]:
        """Initialize a new Swift package scaffold inside an allowed directory."""
        _require_mutations(settings)
        dest = _sandbox_path(settings, directory) / name
        dest.mkdir(parents=True, exist_ok=True)
        return await _exec(["swift", "package", "init", "--name", name], cwd=dest)

    @mcp.tool()
    async def process_list(pattern: str = "xcodebuild") -> dict[str, Any]:
        """List running Xcode/Simulator related processes cleanly via pgrep."""
        _require_macos()
        code, out, err = await runner(["pgrep", "-fl", pattern], None, 10.0)
        lines = [ln for ln in out.splitlines() if ln.strip()] if code == 0 else []
        return {"pattern": pattern, "processes": lines, "detail": err.strip()}

    @mcp.tool()
    async def process_stop(pid: int) -> dict[str, Any]:
        """Terminate a process by numeric PID (requires XCODE_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        return await _exec(["kill", "-TERM", str(pid)])

    return mcp
