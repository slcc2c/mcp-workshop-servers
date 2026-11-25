"""macOS Apple Photos MCP server with sandboxed export path validation."""

from __future__ import annotations

import os
import posixpath
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field, field_validator

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware
from mcp_stack.servers.photos_jxa import (
    OsaScriptPhotosRunner,
    PhotosOperation,
    PhotosScriptError,
    PhotosScriptRunner,
)


class PhotosMCPError(ToolError):
    """Structured error carrying a PHOTOS_* code."""

    def __init__(self, photos_code: str, message: str) -> None:
        self.photos_code = photos_code
        super().__init__(f"[{photos_code}] {message}")


def _validate_iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError("Expected a non-empty ISO date string")
    normalized = value.replace("Z", "+00:00")
    datetime.fromisoformat(normalized)
    return value


class ListAlbumsInput(BaseModel):
    include_smart: bool = True
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SearchAssetsInput(BaseModel):
    query: str | None = None
    album_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    is_favorite: bool | None = None
    is_hidden: bool | None = None
    media_type: Literal["image", "video", "any"] = "any"
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort: Literal["created_desc", "created_asc"] = "created_desc"

    @field_validator("date_from", "date_to")
    @classmethod
    def _check_iso(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


class ExportAssetsInput(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    destination_subdir: str = "exports"
    overwrite: bool = False
    export_variant: Literal["original", "current"] = "current"


def resolve_photos_export_path(
    destination_subdir: str,
    export_root: Path | str | None,
) -> tuple[str, str]:
    """Resolve destinationSubdir strictly inside PHOTOS_EXPORT_ROOT without symlink escapes."""
    root_str = str(export_root).strip() if export_root is not None else ""
    if not root_str:
        raise PhotosMCPError(
            "PHOTOS_EXPORT_ROOT_REQUIRED",
            "PHOTOS_EXPORT_ROOT must be set before using photos_export_assets",
        )

    normalized_subdir = destination_subdir.replace("\\", "/").strip()
    if os.path.isabs(normalized_subdir) or normalized_subdir.startswith("/"):
        raise PhotosMCPError(
            "PHOTOS_EXPORT_PATH_DENIED",
            "destination_subdir must be relative to PHOTOS_EXPORT_ROOT",
        )

    safe_subdir = normalized_subdir if normalized_subdir else "exports"
    posix_norm = posixpath.normpath(safe_subdir)
    if posix_norm == ".." or posix_norm.startswith("../"):
        raise PhotosMCPError(
            "PHOTOS_EXPORT_PATH_DENIED",
            "destination_subdir cannot traverse outside PHOTOS_EXPORT_ROOT",
        )

    resolved_root = Path(root_str).resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    real_root = os.path.realpath(resolved_root)

    segments = [seg for seg in posix_norm.split("/") if seg and seg != "."]
    current_path = real_root
    for segment in segments:
        next_path = os.path.join(current_path, segment)
        try:
            st = os.lstat(next_path)
            if stat.S_ISLNK(st.st_mode):
                raise PhotosMCPError(
                    "PHOTOS_EXPORT_PATH_DENIED",
                    "destination_subdir contains a symbolic link path segment",
                )
            if not stat.S_ISDIR(st.st_mode):
                raise PhotosMCPError(
                    "PHOTOS_EXPORT_PATH_DENIED",
                    "destination_subdir collides with a non-directory path",
                )
        except FileNotFoundError:
            os.mkdir(next_path)
        current_path = next_path

    real_candidate = os.path.realpath(current_path)
    if os.path.commonpath([real_root, real_candidate]) != real_root:
        raise PhotosMCPError(
            "PHOTOS_EXPORT_PATH_DENIED",
            "destination_subdir resolved outside PHOTOS_EXPORT_ROOT",
        )

    return real_root, real_candidate


def create_photos_server(
    settings: MCPStackSettings,
    *,
    runner: PhotosScriptRunner | None = None,
) -> FastMCP:
    """Create the macOS Apple Photos MCP server."""
    script_runner: PhotosScriptRunner = runner or OsaScriptPhotosRunner(
        timeout_seconds=settings.photos.timeout_seconds
    )
    mcp = FastMCP("photos")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "photos"))

    async def _run_op(operation: PhotosOperation, args: dict[str, Any]) -> Any:
        try:
            return await script_runner.run_operation(operation, args)
        except PhotosScriptError as exc:
            raise PhotosMCPError(exc.photos_code, str(exc)) from exc
        except PhotosMCPError:
            raise
        except Exception as exc:
            raise PhotosMCPError("PHOTOS_INTERNAL_ERROR", str(exc)) from exc

    @mcp.tool()
    async def photos_list_albums(
        include_smart: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> Any:
        """List albums in the local macOS Photos library."""
        validated = ListAlbumsInput(
            include_smart=include_smart, limit=limit, offset=offset
        )
        return await _run_op(
            "list_albums",
            {
                "includeSmart": validated.include_smart,
                "limit": validated.limit,
                "offset": validated.offset,
            },
        )

    @mcp.tool()
    async def photos_search_assets(
        query: str | None = None,
        album_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        is_favorite: bool | None = None,
        is_hidden: bool | None = None,
        media_type: Literal["image", "video", "any"] = "any",
        limit: int = 100,
        offset: int = 0,
        sort: Literal["created_desc", "created_asc"] = "created_desc",
    ) -> Any:
        """Search macOS Photos assets with text and metadata filters."""
        validated = SearchAssetsInput(
            query=query,
            album_id=album_id,
            date_from=date_from,
            date_to=date_to,
            is_favorite=is_favorite,
            is_hidden=is_hidden,
            media_type=media_type,
            limit=limit,
            offset=offset,
            sort=sort,
        )
        payload = {
            "query": validated.query,
            "albumId": validated.album_id,
            "dateFrom": validated.date_from,
            "dateTo": validated.date_to,
            "isFavorite": validated.is_favorite,
            "isHidden": validated.is_hidden,
            "mediaType": validated.media_type,
            "limit": validated.limit,
            "offset": validated.offset,
            "sort": validated.sort,
        }
        return await _run_op("search_assets", {k: v for k, v in payload.items() if v is not None})

    @mcp.tool()
    async def photos_get_asset(asset_id: str) -> Any:
        """Get detailed metadata for a single macOS Photos asset."""
        if not asset_id.strip():
            raise PhotosMCPError("PHOTOS_INVALID_FILTER", "asset_id must not be empty")
        return await _run_op("get_asset", {"assetId": asset_id})

    @mcp.tool()
    async def photos_export_assets(
        asset_ids: list[str],
        destination_subdir: str = "exports",
        overwrite: bool = False,
        export_variant: Literal["original", "current"] = "current",
    ) -> dict[str, Any]:
        """Export selected macOS Photos assets into a sandboxed PHOTOS_EXPORT_ROOT subdirectory."""
        validated = ExportAssetsInput(
            asset_ids=asset_ids,
            destination_subdir=destination_subdir,
            overwrite=overwrite,
            export_variant=export_variant,
        )
        export_root = os.getenv("PHOTOS_EXPORT_ROOT") or (
            str(settings.photos.export_root) if settings.photos.export_root else None
        )
        real_root, dest_path = resolve_photos_export_path(
            validated.destination_subdir,
            export_root,
        )
        script_result = await _run_op(
            "export_assets",
            {
                "assetIds": validated.asset_ids,
                "destinationPath": dest_path,
                "overwrite": validated.overwrite,
                "exportVariant": validated.export_variant,
            },
        )
        return {
            "destinationRoot": real_root,
            "destinationPath": dest_path,
            "exported": script_result.get("exported", []),
            "failed": script_result.get("failed", []),
        }

    return mcp
