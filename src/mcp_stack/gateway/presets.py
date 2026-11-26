"""Gateway-persisted Playground tool presets shared between /ui and gateway://presets."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

DEFAULT_PRESETS_PATH = (
    Path.home() / ".local" / "share" / "mcp-workshop-stack" / "presets.json"
)
_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_server_slug(server: str) -> str:
    return server.strip().replace("_", "-").lower()


def _make_preset_id(name: str, server: str) -> str:
    stem = _SLUG_RE.sub("-", f"{server}-{name}".lower()).strip("-")[:36] or "preset"
    return f"{stem}-{uuid.uuid4().hex[:6]}"


class PlaygroundPreset(BaseModel):
    """Saved Playground invocation preset persisted on the gateway host."""

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    server: str = Field(min_length=1, max_length=80)
    tool: str = Field(min_length=1, max_length=140)
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    pinned: bool = False
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)

    @field_validator("name", "tool")
    @classmethod
    def _strip_required(cls, val: str) -> str:
        cleaned = val.strip()
        if not cleaned:
            raise ValueError("Value must be non-empty")
        return cleaned

    @field_validator("server")
    @classmethod
    def _clean_server(cls, val: str) -> str:
        cleaned = _normalize_server_slug(val)
        if not cleaned:
            raise ValueError("Server slug must be non-empty")
        return cleaned

    @field_validator("arguments", mode="before")
    @classmethod
    def _ensure_dict_args(cls, val: Any) -> dict[str, Any]:
        if val is None:
            return {}
        if not isinstance(val, dict):
            raise ValueError("Preset arguments must be a JSON object")
        return dict(val)


class PresetStore:
    """Thread-safe atomic JSON file store for Playground presets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else DEFAULT_PRESETS_PATH
        self._lock = threading.Lock()

    def _read_unlocked(self) -> list[PlaygroundPreset]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items = raw.get("presets", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        out: list[PlaygroundPreset] = []
        for entry in items:
            if isinstance(entry, dict):
                try:
                    out.append(PlaygroundPreset.model_validate(entry))
                except Exception:
                    continue
        return out

    def _write_unlocked(self, presets: list[PlaygroundPreset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updatedAt": _now_iso(),
            "presets": [p.model_dump(mode="json") for p in presets],
        }
        tmp_path = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.path)

    @staticmethod
    def _sorted(presets: list[PlaygroundPreset]) -> list[PlaygroundPreset]:
        return sorted(
            presets,
            key=lambda p: (not p.pinned, p.updatedAt or ""),
            reverse=False,
        )

    def list_presets(self) -> list[PlaygroundPreset]:
        """Return presets sorted with pinned items first, then newest updated."""
        with self._lock:
            items = self._read_unlocked()
        pinned = sorted(
            (p for p in items if p.pinned),
            key=lambda p: p.updatedAt,
            reverse=True,
        )
        unpinned = sorted(
            (p for p in items if not p.pinned),
            key=lambda p: p.updatedAt,
            reverse=True,
        )
        return [*pinned, *unpinned]

    def get_preset(self, preset_id: str) -> PlaygroundPreset | None:
        clean_id = preset_id.strip()
        with self._lock:
            for item in self._read_unlocked():
                if item.id == clean_id:
                    return item
        return None

    def create_preset(
        self,
        *,
        name: str,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
        description: str = "",
        pinned: bool = False,
        preset_id: str | None = None,
    ) -> PlaygroundPreset:
        """Create or replace a preset and persist atomically."""
        now = _now_iso()
        clean_server = _normalize_server_slug(server)
        pid = (preset_id or "").strip() or _make_preset_id(name, clean_server)
        preset = PlaygroundPreset(
            id=pid,
            name=name,
            server=clean_server,
            tool=tool,
            arguments=arguments if arguments is not None else {},
            description=str(description or "").strip(),
            pinned=bool(pinned),
            createdAt=now,
            updatedAt=now,
        )
        with self._lock:
            items = [p for p in self._read_unlocked() if p.id != pid]
            items.append(preset)
            self._write_unlocked(items)
        return preset

    def update_preset(self, preset_id: str, updates: dict[str, Any]) -> PlaygroundPreset | None:
        """Apply partial updates to an existing preset and persist atomically."""
        clean_id = preset_id.strip()
        with self._lock:
            items = self._read_unlocked()
            for idx, existing in enumerate(items):
                if existing.id != clean_id:
                    continue
                patch: dict[str, Any] = {"updatedAt": _now_iso()}
                for field in ("name", "server", "tool", "arguments", "description", "pinned"):
                    if field in updates and updates[field] is not None:
                        patch[field] = updates[field]
                updated = PlaygroundPreset.model_validate({**existing.model_dump(), **patch})
                items[idx] = updated
                self._write_unlocked(items)
                return updated
        return None

    def delete_preset(self, preset_id: str) -> bool:
        """Delete a preset by ID; returns True when removed."""
        clean_id = preset_id.strip()
        with self._lock:
            items = self._read_unlocked()
            remaining = [p for p in items if p.id != clean_id]
            if len(remaining) == len(items):
                return False
            self._write_unlocked(remaining)
            return True
