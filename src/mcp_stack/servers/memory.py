"""SQLite + FTS5 persistent Memory MCP server with legacy JSON import & UC Volume export."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sqlite3
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.tracing import MLflowTracingMiddleware

MemoryType = Literal["fact", "preference", "experience", "goal", "context"]


class MemoryStore:
    """Thread-safe SQLite + FTS5 knowledge graph store for AI memory."""

    def __init__(self, db_path: Path, legacy_json_path: Path | None = None) -> None:
        self._db_path = db_path
        self._legacy_json_path = legacy_json_path
        self._logger = get_logger("memory.store")
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS entry_tags (
                    entry_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (entry_id, tag),
                    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);
                CREATE TABLE IF NOT EXISTS relationships (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id),
                    FOREIGN KEY (source_id) REFERENCES entries(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES entries(id) ON DELETE CASCADE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    entry_id UNINDEXED,
                    content,
                    tags
                );
                """
            )
            count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            if count == 0 and self._legacy_json_path and self._legacy_json_path.exists():
                self._import_legacy_json(conn, self._legacy_json_path)
            conn.commit()
        self._initialized = True

    def _import_legacy_json(self, conn: sqlite3.Connection, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._logger.warning(
                "Failed to parse legacy memory.json", path=str(path), error=str(exc)
            )
            return

        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            return

        inserted_ids: set[str] = set()
        pending_rels: list[tuple[str, list[str]]] = []

        for raw in entries:
            if not isinstance(raw, dict) or "id" not in raw or "content" not in raw:
                continue
            eid = str(raw["id"])
            content = str(raw["content"])
            mtype = str(raw.get("type") or "fact")
            ts = str(raw.get("timestamp") or datetime.now(UTC).isoformat())
            tags = [str(t) for t in (raw.get("tags") or [])]
            metadata = raw.get("metadata") or {}
            rels = [str(r) for r in (raw.get("relationships") or [])]

            conn.execute(
                "INSERT OR IGNORE INTO entries(id, content, type, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (eid, content, mtype, ts, json.dumps(metadata)),
            )
            for tag in tags:
                conn.execute(
                    "INSERT OR IGNORE INTO entry_tags(entry_id, tag) VALUES (?, ?)",
                    (eid, tag),
                )
            conn.execute(
                "INSERT INTO entries_fts(entry_id, content, tags) VALUES (?, ?, ?)",
                (eid, content, " ".join(tags)),
            )
            inserted_ids.add(eid)
            if rels:
                pending_rels.append((eid, rels))

        for src, targets in pending_rels:
            for tgt in targets:
                if tgt in inserted_ids and tgt != src:
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (src, tgt),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (tgt, src),
                    )

        self._logger.info("Imported legacy memory entries", count=len(inserted_ids))

    def _hydrate(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        eid = row["id"]
        tags = [
            r["tag"]
            for r in conn.execute(
                "SELECT tag FROM entry_tags WHERE entry_id = ? ORDER BY tag", (eid,)
            ).fetchall()
        ]
        rels = [
            r["target_id"]
            for r in conn.execute(
                "SELECT target_id FROM relationships WHERE source_id = ? ORDER BY target_id",
                (eid,),
            ).fetchall()
        ]
        return {
            "id": eid,
            "content": row["content"],
            "type": row["type"],
            "timestamp": row["timestamp"],
            "tags": tags,
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "relationships": rels,
        }

    def store(
        self,
        *,
        content: str,
        type: MemoryType,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        related_to: list[str] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        eid = f"mem_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        ts = datetime.now(UTC).isoformat()
        clean_tags = sorted({t.strip() for t in (tags or []) if t.strip()})
        meta = metadata or {}
        rels = related_to or []

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO entries(id, content, type, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (eid, content, type, ts, json.dumps(meta)),
            )
            for tag in clean_tags:
                conn.execute(
                    "INSERT OR IGNORE INTO entry_tags(entry_id, tag) VALUES (?, ?)",
                    (eid, tag),
                )
            conn.execute(
                "INSERT INTO entries_fts(entry_id, content, tags) VALUES (?, ?, ?)",
                (eid, content, " ".join(clean_tags)),
            )
            for rel_id in rels:
                if rel_id == eid:
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM entries WHERE id = ?", (rel_id,)
                ).fetchone()
                if exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (eid, rel_id),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (rel_id, eid),
                    )
            conn.commit()
        return {"id": eid, "stored": True, "timestamp": ts}

    def search(
        self,
        *,
        query: str,
        type: MemoryType | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        self.initialize()
        limit = max(1, min(limit, 100))
        q = query.strip()
        filter_tags = [t.strip() for t in (tags or []) if t.strip()]

        with self._connect() as conn:
            candidate_ids: list[str] | None = None
            if q:
                safe_fts = " ".join(
                    f'"{tok.replace(chr(34), "")}"'
                    for tok in q.split()
                    if tok.strip()
                )
                try:
                    if safe_fts:
                        rows = conn.execute(
                            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ? "
                            "ORDER BY bm25(entries_fts)",
                            (safe_fts,),
                        ).fetchall()
                        candidate_ids = [r["entry_id"] for r in rows]
                except sqlite3.OperationalError:
                    candidate_ids = None

                if candidate_ids is None or not candidate_ids:
                    like_q = f"%{q.lower()}%"
                    rows = conn.execute(
                        "SELECT DISTINCT e.id FROM entries e "
                        "LEFT JOIN entry_tags t ON e.id = t.entry_id "
                        "WHERE LOWER(e.content) LIKE ? OR LOWER(COALESCE(t.tag, '')) LIKE ?",
                        (like_q, like_q),
                    ).fetchall()
                    candidate_ids = [r["id"] for r in rows]

            sql = "SELECT * FROM entries WHERE 1=1"
            params: list[Any] = []
            if candidate_ids is not None:
                if not candidate_ids:
                    return {"query": query, "totalResults": 0, "results": []}
                placeholders = ",".join("?" for _ in candidate_ids)
                sql += f" AND id IN ({placeholders})"
                params.extend(candidate_ids)
            if type is not None:
                sql += " AND type = ?"
                params.append(type)
            if filter_tags:
                placeholders = ",".join("?" for _ in filter_tags)
                sql += (
                    " AND id IN (SELECT entry_id FROM entry_tags "
                    f"WHERE tag IN ({placeholders}))"
                )
                params.extend(filter_tags)

            sql += " ORDER BY timestamp DESC"
            rows = conn.execute(sql, params).fetchall()
            hydrated = [self._hydrate(conn, r) for r in rows]

        return {
            "query": query,
            "totalResults": len(hydrated),
            "results": hydrated[:limit],
        }

    def get(self, entry_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise ToolError(f"Memory entry not found: {entry_id}")
            return self._hydrate(conn, row)

    def update(
        self,
        *,
        id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        add_relations: list[str] | None = None,
        remove_relations: list[str] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (id,)).fetchone()
            if row is None:
                raise ToolError(f"Memory entry not found: {id}")

            new_content = content if content is not None else row["content"]
            existing_meta = json.loads(row["metadata_json"] or "{}")
            if metadata is not None:
                existing_meta.update(metadata)

            conn.execute(
                "UPDATE entries SET content = ?, metadata_json = ? WHERE id = ?",
                (new_content, json.dumps(existing_meta), id),
            )

            if tags is not None:
                clean_tags = sorted({t.strip() for t in tags if t.strip()})
                conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (id,))
                for tag in clean_tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO entry_tags(entry_id, tag) VALUES (?, ?)",
                        (id, tag),
                    )
            else:
                clean_tags = [
                    r["tag"]
                    for r in conn.execute(
                        "SELECT tag FROM entry_tags WHERE entry_id = ?", (id,)
                    ).fetchall()
                ]

            conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (id,))
            conn.execute(
                "INSERT INTO entries_fts(entry_id, content, tags) VALUES (?, ?, ?)",
                (id, new_content, " ".join(clean_tags)),
            )

            for rel_id in add_relations or []:
                if rel_id == id:
                    continue
                exists = conn.execute("SELECT 1 FROM entries WHERE id = ?", (rel_id,)).fetchone()
                if exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (id, rel_id),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships(source_id, target_id) VALUES (?, ?)",
                        (rel_id, id),
                    )

            for rel_id in remove_relations or []:
                conn.execute(
                    "DELETE FROM relationships WHERE source_id = ? AND target_id = ?",
                    (id, rel_id),
                )
                conn.execute(
                    "DELETE FROM relationships WHERE source_id = ? AND target_id = ?",
                    (rel_id, id),
                )

            conn.commit()
            updated = conn.execute("SELECT * FROM entries WHERE id = ?", (id,)).fetchone()
            assert updated is not None
            return self._hydrate(conn, updated)

    def delete(self, entry_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise ToolError(f"Memory entry not found: {entry_id}")
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
            conn.commit()
        return {"id": entry_id, "deleted": True}

    def list_tags(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tag, COUNT(*) AS cnt FROM entry_tags GROUP BY tag ORDER BY cnt DESC, tag"
            ).fetchall()
            return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]

    def get_related(self, entry_id: str, depth: int = 1) -> dict[str, Any]:
        self.initialize()
        depth = max(1, min(depth, 3))
        with self._connect() as conn:
            root = conn.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if root is None:
                raise ToolError(f"Memory entry not found: {entry_id}")

            visited: set[str] = {entry_id}
            queue: deque[tuple[str, int]] = deque([(entry_id, 0)])
            related_ids: list[str] = []

            while queue:
                current, cur_depth = queue.popleft()
                if cur_depth >= depth:
                    continue
                neighbors = conn.execute(
                    "SELECT target_id FROM relationships WHERE source_id = ?", (current,)
                ).fetchall()
                for nb in neighbors:
                    nid = nb["target_id"]
                    if nid not in visited:
                        visited.add(nid)
                        related_ids.append(nid)
                        queue.append((nid, cur_depth + 1))

            related_entries = []
            for rid in related_ids:
                row = conn.execute("SELECT * FROM entries WHERE id = ?", (rid,)).fetchone()
                if row is not None:
                    related_entries.append(self._hydrate(conn, row))

        return {"id": entry_id, "depth": depth, "relatedEntries": related_entries}

    def export(
        self,
        *,
        format: Literal["json", "csv"] = "json",
        uc_volume_path: str | None = None,
        default_volume: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM entries ORDER BY timestamp DESC").fetchall()
            entries = [self._hydrate(conn, r) for r in rows]
            tag_count = conn.execute("SELECT COUNT(DISTINCT tag) FROM entry_tags").fetchone()[0]
            rel_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]

        if format == "json":
            payload: dict[str, Any] = {
                "format": "json",
                "data": {
                    "entries": entries,
                    "stats": {
                        "totalEntries": len(entries),
                        "totalTags": tag_count,
                        "totalRelationships": rel_count,
                    },
                },
            }
            serialized = json.dumps(payload["data"], indent=2)
            ext = "json"
        else:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["id", "content", "type", "timestamp", "tags", "relationships"])
            for entry in entries:
                writer.writerow(
                    [
                        entry["id"],
                        entry["content"],
                        entry["type"],
                        entry["timestamp"],
                        ";".join(entry["tags"]),
                        ";".join(entry["relationships"]),
                    ]
                )
            serialized = buf.getvalue()
            payload = {
                "format": "csv",
                "headers": ["id", "content", "type", "timestamp", "tags", "relationships"],
                "csv": serialized,
                "rowCount": len(entries),
            }
            ext = "csv"

        target_dir = uc_volume_path or default_volume
        if target_dir:
            target = Path(target_dir).resolve()
            if target.is_dir() or not target.suffix:
                target.mkdir(parents=True, exist_ok=True)
                out_file = target / f"memory-export-{int(time.time())}.{ext}"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                out_file = target
            out_file.write_text(serialized, encoding="utf-8")
            payload["exportedFile"] = str(out_file)

        return payload

    def import_snapshot(
        self,
        *,
        source_path: str | None = None,
        volume_dir: Path | None = None,
        filename: str | None = None,
        merge_mode: Literal["upsert", "skip_existing"] = "upsert",
    ) -> dict[str, Any]:
        """Import a JSON memory snapshot into SQLite + FTS5."""
        self.initialize()
        if source_path:
            target = Path(source_path).resolve()
        elif volume_dir is not None:
            base = volume_dir.resolve()
            if filename:
                target = (base / filename).resolve()
                if not target.is_relative_to(base):
                    raise ToolError(f"Snapshot filename '{filename}' escapes volume directory")
            else:
                candidates = sorted(
                    base.glob("memory-export-*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if not candidates:
                    raise ToolError(f"No memory-export-*.json snapshots found in {base}")
                target = candidates[0]
        else:
            raise ToolError("Provide either source_path or uc_volume_name")

        if not target.exists():
            raise ToolError(f"Snapshot file not found: {target}")

        raw = json.loads(target.read_text(encoding="utf-8"))
        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            raise ToolError(f"Invalid snapshot payload in {target}: missing 'entries' list")

        imported = 0
        skipped = 0
        pending_rels: list[tuple[str, list[str]]] = []

        with self._connect() as conn:
            known_ids = {
                str(r[0]) for r in conn.execute("SELECT id FROM entries").fetchall()
            }
            for item in entries:
                if not isinstance(item, dict) or "id" not in item or "content" not in item:
                    continue
                eid = str(item["id"])
                content = str(item["content"])
                mtype = str(item.get("type") or "fact")
                ts = str(item.get("timestamp") or datetime.now(UTC).isoformat())
                tags = [str(t) for t in (item.get("tags") or [])]
                metadata = item.get("metadata") or {}
                rels = [str(r) for r in (item.get("relationships") or [])]

                if eid in known_ids and merge_mode == "skip_existing":
                    skipped += 1
                    continue

                if eid in known_ids:
                    conn.execute(
                        "UPDATE entries SET content=?, type=?, timestamp=?, metadata_json=? "
                        "WHERE id=?",
                        (content, mtype, ts, json.dumps(metadata), eid),
                    )
                    conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (eid,))
                    conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (eid,))
                else:
                    conn.execute(
                        "INSERT INTO entries(id, content, type, timestamp, metadata_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (eid, content, mtype, ts, json.dumps(metadata)),
                    )
                    known_ids.add(eid)

                for tag in tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO entry_tags(entry_id, tag) VALUES (?, ?)",
                        (eid, tag),
                    )
                conn.execute(
                    "INSERT INTO entries_fts(entry_id, content, tags) VALUES (?, ?, ?)",
                    (eid, content, " ".join(tags)),
                )
                imported += 1
                if rels:
                    pending_rels.append((eid, rels))

            for src, targets in pending_rels:
                for tgt in targets:
                    if tgt in known_ids and tgt != src:
                        conn.execute(
                            "INSERT OR IGNORE INTO relationships(source_id, target_id) "
                            "VALUES (?, ?)",
                            (src, tgt),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO relationships(source_id, target_id) "
                            "VALUES (?, ?)",
                            (tgt, src),
                        )
            conn.commit()

        return {
            "importedFile": str(target),
            "importedCount": imported,
            "skippedCount": skipped,
            "mergeMode": merge_mode,
        }


def create_memory_server(
    settings: MCPStackSettings,
    *,
    store: MemoryStore | None = None,
    uc_adapter: Any = None,
) -> FastMCP:
    """Create the SQLite + FTS5 Memory MCP server."""
    mem_store = store or MemoryStore(
        db_path=settings.memory.db_path,
        legacy_json_path=settings.memory.legacy_json_path,
    )
    mem_store.initialize()

    mcp = FastMCP("memory")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "memory"))

    @mcp.tool()
    async def memory_store(
        content: str,
        type: MemoryType = "fact",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        related_to: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store a new memory entry in the persistent knowledge graph."""
        return await asyncio.to_thread(
            mem_store.store,
            content=content,
            type=type,
            tags=tags,
            metadata=metadata,
            related_to=related_to,
        )

    @mcp.tool()
    async def memory_search(
        query: str = "",
        type: MemoryType | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search memory entries using FTS5 full-text search and optional filters."""
        return await asyncio.to_thread(
            mem_store.search,
            query=query,
            type=type,
            tags=tags,
            limit=limit,
        )

    @mcp.tool()
    async def memory_get(id: str) -> dict[str, Any]:
        """Get a specific memory entry by ID."""
        return await asyncio.to_thread(mem_store.get, id)

    @mcp.tool()
    async def memory_update(
        id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        add_relations: list[str] | None = None,
        remove_relations: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing memory entry."""
        return await asyncio.to_thread(
            mem_store.update,
            id=id,
            content=content,
            tags=tags,
            metadata=metadata,
            add_relations=add_relations,
            remove_relations=remove_relations,
        )

    @mcp.tool()
    async def memory_delete(id: str) -> dict[str, Any]:
        """Delete a memory entry by ID."""
        return await asyncio.to_thread(mem_store.delete, id)

    @mcp.tool()
    async def memory_list_tags() -> list[dict[str, Any]]:
        """List all memory tags with entry counts."""
        return await asyncio.to_thread(mem_store.list_tags)

    @mcp.tool()
    async def memory_get_related(id: str, depth: int = 1) -> dict[str, Any]:
        """Traverse related memory entries up to depth 3."""
        return await asyncio.to_thread(mem_store.get_related, id, depth)

    @mcp.tool()
    async def memory_export(
        format: Literal["json", "csv"] = "json",
        uc_volume_path: str | None = None,
        uc_volume_name: str | None = None,
    ) -> dict[str, Any]:
        """Export memory graph as JSON or CSV (local path or catalog.schema.volume)."""
        resolved_path = uc_volume_path
        if uc_volume_name:
            from mcp_stack.servers.unity_catalog import (
                UCClientAdapter,
                resolve_volume_local_dir,
            )

            adapter = uc_adapter or UCClientAdapter(settings)
            vol_dir = await resolve_volume_local_dir(adapter, settings, uc_volume_name)
            resolved_path = str(vol_dir)

        result = await asyncio.to_thread(
            mem_store.export,
            format=format,
            uc_volume_path=resolved_path,
            default_volume=settings.memory.uc_export_volume,
        )
        if uc_volume_name:
            result["ucVolume"] = uc_volume_name
        return result

    @mcp.tool()
    async def memory_import(
        source_path: str | None = None,
        uc_volume_name: str | None = None,
        filename: str | None = None,
        merge_mode: Literal["upsert", "skip_existing"] = "upsert",
    ) -> dict[str, Any]:
        """Import a memory JSON snapshot from a local path or UC Volume into SQLite."""
        volume_dir: Path | None = None
        if uc_volume_name:
            from mcp_stack.servers.unity_catalog import (
                UCClientAdapter,
                resolve_volume_local_dir,
            )

            adapter = uc_adapter or UCClientAdapter(settings)
            volume_dir = await resolve_volume_local_dir(adapter, settings, uc_volume_name)

        result = await asyncio.to_thread(
            mem_store.import_snapshot,
            source_path=source_path,
            volume_dir=volume_dir,
            filename=filename,
            merge_mode=merge_mode,
        )
        if uc_volume_name:
            result["ucVolume"] = uc_volume_name
        return result

    return mcp
