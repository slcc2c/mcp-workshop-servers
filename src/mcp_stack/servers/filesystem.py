"""Sandboxed Filesystem MCP server with strict Path.is_relative_to validation."""

from __future__ import annotations

import asyncio
import base64
import fnmatch
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware


def resolve_safe_path(
    input_path: str,
    allowed_paths: list[Path],
    blocked_paths: list[str],
) -> Path:
    """Resolve and validate a path against allowed_paths and blocked_paths."""
    if not allowed_paths:
        raise ToolError("No allowed_paths configured for filesystem server")

    raw = Path(input_path)
    if not raw.is_absolute():
        base = allowed_paths[0].resolve()
        candidate = (base / raw).resolve()
    else:
        candidate = raw.resolve()

    resolved_allowed = [p.resolve() for p in allowed_paths]
    if not any(candidate.is_relative_to(root) for root in resolved_allowed):
        raise ToolError(
            f"Permission denied: '{input_path}' resolves outside allowed directories"
        )

    for blocked in blocked_paths:
        blocked_resolved = Path(blocked).resolve()
        if any(root.is_relative_to(blocked_resolved) for root in resolved_allowed):
            continue
        if candidate.is_relative_to(blocked_resolved):
            raise ToolError(
                f"Permission denied: '{input_path}' targets blocked path '{blocked}'"
            )

    return candidate


def _ensure_no_symlink_target(input_path: str, allowed_paths: list[Path]) -> None:
    """Ensure raw path components within allowed roots do not traverse symlinks escaping roots."""
    raw = Path(input_path)
    base = allowed_paths[0].resolve() if not raw.is_absolute() else raw.anchor
    target = (Path(base) / raw) if not raw.is_absolute() else raw
    # Check existing ancestors up to the path itself
    for part in [target, *target.parents]:
        if os.path.islink(part):
            resolved_link = part.resolve()
            resolved_allowed = [p.resolve() for p in allowed_paths]
            if not any(resolved_link.is_relative_to(root) for root in resolved_allowed):
                raise ToolError(f"Permission denied: symlink '{part}' escapes sandbox")


def create_filesystem_server(settings: MCPStackSettings) -> FastMCP:
    """Create the sandboxed Filesystem MCP server."""
    fs_cfg = settings.filesystem
    mcp = FastMCP("filesystem")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "filesystem"))

    def _safe(path_str: str) -> Path:
        _ensure_no_symlink_target(path_str, fs_cfg.allowed_paths)
        return resolve_safe_path(path_str, fs_cfg.allowed_paths, fs_cfg.blocked_paths)

    @mcp.tool()
    async def fs_read_file(
        path: str,
        encoding: Literal["utf-8", "utf8", "base64"] = "utf-8",
        offset: int | None = None,
        length: int | None = None,
    ) -> dict[str, Any]:
        """Read contents of a file inside allowed directories."""
        target = _safe(path)

        def _read() -> dict[str, Any]:
            if not target.exists():
                raise ToolError(f"File not found: {path}")
            if not target.is_file():
                raise ToolError(f"Path is not a file: {path}")
            size = target.stat().st_size
            if offset is None and length is None and size > fs_cfg.max_file_size:
                raise ToolError(
                    f"File too large: {size} bytes (max: {fs_cfg.max_file_size})"
                )
            with target.open("rb") as fh:
                if offset is not None and offset > 0:
                    fh.seek(offset)
                read_len = length if length is not None else fs_cfg.max_file_size
                if read_len > fs_cfg.max_file_size:
                    raise ToolError(
                        f"Requested read length {read_len} exceeds max_file_size "
                        f"({fs_cfg.max_file_size})"
                    )
                raw = fh.read(read_len)

            if encoding == "base64":
                content = base64.b64encode(raw).decode("ascii")
            else:
                content = raw.decode("utf-8", errors="replace")

            return {
                "path": str(target),
                "content": content,
                "size": len(raw),
                "encoding": encoding,
            }

        return await asyncio.to_thread(_read)

    @mcp.tool()
    async def fs_write_file(
        path: str,
        content: str,
        encoding: Literal["utf-8", "utf8", "base64"] = "utf-8",
        create_dirs: bool = True,
    ) -> dict[str, Any]:
        """Write content to a file inside allowed directories."""
        target = _safe(path)

        def _write() -> dict[str, Any]:
            if encoding == "base64":
                raw = base64.b64decode(content.encode("ascii"))
            else:
                raw = content.encode("utf-8")
            if len(raw) > fs_cfg.max_file_size:
                raise ToolError(
                    f"Content too large: {len(raw)} bytes (max: {fs_cfg.max_file_size})"
                )
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"path": str(target), "bytesWritten": len(raw), "success": True}

        return await asyncio.to_thread(_write)

    @mcp.tool()
    async def fs_delete_file(path: str) -> dict[str, Any]:
        """Delete a file inside allowed directories."""
        target = _safe(path)

        def _delete() -> dict[str, Any]:
            if not target.exists():
                raise ToolError(f"File not found: {path}")
            if not target.is_file() and not target.is_symlink():
                raise ToolError(f"Path is not a file: {path}")
            target.unlink()
            return {"path": str(target), "deleted": True}

        return await asyncio.to_thread(_delete)

    @mcp.tool()
    async def fs_copy_file(
        source: str,
        destination: str,
        overwrite: bool = False,
        create_dirs: bool = True,
    ) -> dict[str, Any]:
        """Copy a file within allowed directories."""
        src = _safe(source)
        dst = _safe(destination)

        def _copy() -> dict[str, Any]:
            if not src.is_file():
                raise ToolError(f"Source file not found: {source}")
            if dst.exists() and not overwrite:
                raise ToolError(f"Destination already exists: {destination}")
            if create_dirs:
                dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return {"source": str(src), "destination": str(dst), "copied": True}

        return await asyncio.to_thread(_copy)

    @mcp.tool()
    async def fs_move_file(
        source: str,
        destination: str,
        overwrite: bool = False,
        create_dirs: bool = True,
    ) -> dict[str, Any]:
        """Move or rename a file within allowed directories."""
        src = _safe(source)
        dst = _safe(destination)

        def _move() -> dict[str, Any]:
            if not src.exists():
                raise ToolError(f"Source not found: {source}")
            if dst.exists() and not overwrite:
                raise ToolError(f"Destination already exists: {destination}")
            if create_dirs:
                dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return {"source": str(src), "destination": str(dst), "moved": True}

        return await asyncio.to_thread(_move)

    @mcp.tool()
    async def fs_list_directory(
        path: str = ".",
        recursive: bool = False,
        include_hidden: bool = False,
        pattern: str | None = None,
        details: bool = False,
    ) -> dict[str, Any]:
        """List directory contents inside allowed directories."""
        target = _safe(path)

        def _list() -> dict[str, Any]:
            if not target.is_dir():
                raise ToolError(f"Directory not found: {path}")

            items: list[dict[str, Any]] = []
            iterator = target.rglob("*") if recursive else target.iterdir()
            for entry in iterator:
                rel = entry.relative_to(target)
                if not include_hidden and any(part.startswith(".") for part in rel.parts):
                    continue
                if pattern and not fnmatch.fnmatch(entry.name, pattern):
                    continue
                item: dict[str, Any] = {
                    "name": entry.name,
                    "path": str(rel),
                    "type": "directory" if entry.is_dir() else "file",
                }
                if details:
                    st = entry.stat()
                    item["size"] = st.st_size
                    item["modifiedAt"] = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()
                items.append(item)
                if len(items) >= 1000:
                    break

            items.sort(key=lambda x: (x["type"] != "directory", x["path"]))
            return {"path": str(target), "count": len(items), "items": items}

        return await asyncio.to_thread(_list)

    @mcp.tool()
    async def fs_create_directory(path: str, recursive: bool = True) -> dict[str, Any]:
        """Create a directory inside allowed directories."""
        target = _safe(path)

        def _mkdir() -> dict[str, Any]:
            target.mkdir(parents=recursive, exist_ok=True)
            return {"path": str(target), "created": True}

        return await asyncio.to_thread(_mkdir)

    @mcp.tool()
    async def fs_delete_directory(path: str, recursive: bool = False) -> dict[str, Any]:
        """Delete a directory inside allowed directories."""
        target = _safe(path)

        def _rmdir() -> dict[str, Any]:
            if not target.is_dir():
                raise ToolError(f"Directory not found: {path}")
            if target in [p.resolve() for p in fs_cfg.allowed_paths]:
                raise ToolError("Cannot delete a configured allowed root directory")
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
            return {"path": str(target), "deleted": True}

        return await asyncio.to_thread(_rmdir)

    @mcp.tool()
    async def fs_get_stats(path: str) -> dict[str, Any]:
        """Get file or directory metadata."""
        target = _safe(path)

        def _stats() -> dict[str, Any]:
            if not target.exists():
                raise ToolError(f"Path not found: {path}")
            st = target.stat()
            return {
                "path": str(target),
                "isFile": target.is_file(),
                "isDirectory": target.is_dir(),
                "size": st.st_size,
                "modifiedAt": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
            }

        return await asyncio.to_thread(_stats)

    @mcp.tool()
    async def fs_exists(path: str) -> dict[str, Any]:
        """Check whether a path exists inside allowed directories."""
        target = _safe(path)
        return {"path": str(target), "exists": target.exists()}

    @mcp.tool()
    async def fs_search_files(
        path: str = ".",
        query: str = "",
        file_pattern: str | None = None,
        search_content: bool = True,
        search_names: bool = True,
        case_sensitive: bool = False,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Search files by filename and/or text content inside allowed directories."""
        target = _safe(path)

        def _search() -> dict[str, Any]:
            if not target.is_dir():
                raise ToolError(f"Directory not found: {path}")
            needle = query if case_sensitive else query.lower()
            matches: list[dict[str, Any]] = []

            for entry in target.rglob("*"):
                if not entry.is_file():
                    continue
                if file_pattern and not fnmatch.fnmatch(entry.name, file_pattern):
                    continue
                name_cmp = entry.name if case_sensitive else entry.name.lower()
                matched_name = bool(needle and search_names and needle in name_cmp)
                matched_content = False
                if (
                    needle
                    and search_content
                    and not matched_name
                    and entry.stat().st_size <= fs_cfg.max_file_size
                ):
                    try:
                        text = entry.read_text(encoding="utf-8", errors="ignore")
                        hay = text if case_sensitive else text.lower()
                        matched_content = needle in hay
                    except Exception:
                        matched_content = False

                if not needle or matched_name or matched_content:
                    matches.append(
                        {
                            "path": str(entry),
                            "name": entry.name,
                            "matchedBy": (
                                "name"
                                if matched_name
                                else ("content" if matched_content else "pattern")
                            ),
                        }
                    )
                    if len(matches) >= max_results:
                        break

            return {"query": query, "count": len(matches), "matches": matches}

        return await asyncio.to_thread(_search)

    @mcp.tool()
    async def fs_get_working_directory() -> dict[str, Any]:
        """Return current working directory and configured sandbox roots."""
        return {
            "cwd": str(Path.cwd()),
            "allowed": [str(p.resolve()) for p in fs_cfg.allowed_paths],
        }

    return mcp
