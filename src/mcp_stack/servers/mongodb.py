"""MongoDB FastMCP server with read-only defaults and document serialization."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.mongodb.allow_mutations:
        raise ToolError(
            "MongoDB mutations are disabled by policy. "
            "Set MONGODB_ALLOW_MUTATIONS=true to enable writes or collection DDL."
        )


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def create_mongodb_server(
    settings: MCPStackSettings,
    *,
    db_factory: Callable[[str, str], Any] | None = None,
    secret_resolver: SecretResolver | None = None,
) -> FastMCP:
    """Create the MongoDB MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("mongodb")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "mongodb"))

    def _get_db() -> Any:
        resolved_uri = resolver.resolve(settings.mongodb.uri)
        if not resolved_uri:
            raise ToolError("MongoDB URI is not configured. Set MONGODB_URI in .env.")
        if db_factory is not None:
            return db_factory(resolved_uri, settings.mongodb.database)
        from pymongo import MongoClient

        try:
            client: Any = MongoClient(
                resolved_uri,
                serverSelectionTimeoutMS=int(settings.mongodb.timeout_seconds * 1000),
            )
            return client[settings.mongodb.database]
        except Exception as exc:
            raise ToolError(f"Failed to connect to MongoDB: {exc}") from exc

    @mcp.tool()
    async def mongodb_find(
        collection: str,
        filter: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query documents in a MongoDB collection."""
        cap = min(limit, settings.mongodb.max_docs)

        def _run() -> list[Any]:
            cursor = _get_db()[collection].find(filter or {}, projection).limit(cap)
            return _json_safe(list(cursor))

        docs = await asyncio.to_thread(_run)
        return {"collection": collection, "documents": docs, "count": len(docs)}

    @mcp.tool()
    async def mongodb_find_one(
        collection: str,
        filter: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Find a single matching document in a MongoDB collection."""
        doc = await asyncio.to_thread(
            lambda: _json_safe(_get_db()[collection].find_one(filter or {}, projection))
        )
        return {"collection": collection, "document": doc}

    @mcp.tool()
    async def mongodb_insert_one(collection: str, document: dict[str, Any]) -> dict[str, Any]:
        """Insert a document into a MongoDB collection."""
        _require_mutations(settings)
        res = await asyncio.to_thread(lambda: _get_db()[collection].insert_one(document))
        return {"collection": collection, "insertedId": str(res.inserted_id)}

    @mcp.tool()
    async def mongodb_insert_many(
        collection: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Insert multiple documents into a MongoDB collection."""
        _require_mutations(settings)
        res = await asyncio.to_thread(lambda: _get_db()[collection].insert_many(documents))
        return {"collection": collection, "insertedIds": [str(i) for i in res.inserted_ids]}

    @mcp.tool()
    async def mongodb_update_one(
        collection: str,
        filter: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> dict[str, Any]:
        """Update one document in a MongoDB collection."""
        _require_mutations(settings)
        res = await asyncio.to_thread(
            lambda: _get_db()[collection].update_one(filter, update, upsert=upsert)
        )
        return {"matched": int(res.matched_count), "modified": int(res.modified_count)}

    @mcp.tool()
    async def mongodb_update_many(
        collection: str,
        filter: dict[str, Any],
        update: dict[str, Any],
    ) -> dict[str, Any]:
        """Update multiple documents in a MongoDB collection."""
        _require_mutations(settings)
        res = await asyncio.to_thread(lambda: _get_db()[collection].update_many(filter, update))
        return {"matched": int(res.matched_count), "modified": int(res.modified_count)}

    @mcp.tool()
    async def mongodb_delete_one(collection: str, filter: dict[str, Any]) -> dict[str, Any]:
        """Delete one matching document from a MongoDB collection."""
        _require_mutations(settings)
        res = await asyncio.to_thread(lambda: _get_db()[collection].delete_one(filter))
        return {"deleted": int(res.deleted_count)}

    @mcp.tool()
    async def mongodb_delete_many(collection: str, filter: dict[str, Any]) -> dict[str, Any]:
        """Delete multiple matching documents from a MongoDB collection."""
        _require_mutations(settings)
        if not filter:
            raise ToolError("Non-empty filter is required for mongodb_delete_many")
        res = await asyncio.to_thread(lambda: _get_db()[collection].delete_many(filter))
        return {"deleted": int(res.deleted_count)}

    @mcp.tool()
    async def mongodb_aggregate(
        collection: str,
        pipeline: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run an aggregation pipeline (blocks $out/$merge when read-only)."""
        if not settings.mongodb.allow_mutations:
            for stage in pipeline:
                if "$out" in stage or "$merge" in stage:
                    _require_mutations(settings)
        docs = await asyncio.to_thread(
            lambda: _json_safe(list(_get_db()[collection].aggregate(pipeline)))
        )
        return {"collection": collection, "results": docs, "count": len(docs)}

    @mcp.tool()
    async def mongodb_create_index(
        collection: str,
        keys: dict[str, int],
        unique: bool = False,
    ) -> dict[str, Any]:
        """Create an index on a MongoDB collection."""
        _require_mutations(settings)
        name = await asyncio.to_thread(
            lambda: _get_db()[collection].create_index(list(keys.items()), unique=unique)
        )
        return {"collection": collection, "indexName": name}

    @mcp.tool()
    async def mongodb_list_indexes(collection: str) -> dict[str, Any]:
        """List indexes defined on a MongoDB collection."""
        idxs = await asyncio.to_thread(
            lambda: _json_safe(list(_get_db()[collection].list_indexes()))
        )
        return {"collection": collection, "indexes": idxs}

    @mcp.tool()
    async def mongodb_list_collections() -> dict[str, Any]:
        """List collection names in the configured MongoDB database."""
        cols = await asyncio.to_thread(lambda: sorted(_get_db().list_collection_names()))
        return {"database": settings.mongodb.database, "collections": cols}

    @mcp.tool()
    async def mongodb_create_collection(collection: str) -> dict[str, Any]:
        """Create a MongoDB collection."""
        _require_mutations(settings)
        await asyncio.to_thread(lambda: _get_db().create_collection(collection))
        return {"collection": collection, "created": True}

    @mcp.tool()
    async def mongodb_drop_collection(collection: str) -> dict[str, Any]:
        """Drop a MongoDB collection."""
        _require_mutations(settings)
        await asyncio.to_thread(lambda: _get_db().drop_collection(collection))
        return {"collection": collection, "dropped": True}

    @mcp.tool()
    async def mongodb_stats(collection: str | None = None) -> dict[str, Any]:
        """Return MongoDB database or collection statistics."""
        cmd = {"collStats": collection} if collection else {"dbStats": 1}
        stats = await asyncio.to_thread(lambda: _json_safe(_get_db().command(cmd)))
        return {"stats": stats}

    @mcp.tool()
    async def mongodb_count(
        collection: str,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Count matching documents in a MongoDB collection."""
        cnt = await asyncio.to_thread(
            lambda: int(_get_db()[collection].count_documents(filter or {}))
        )
        return {"collection": collection, "count": cnt}

    @mcp.tool()
    async def mongodb_distinct(
        collection: str,
        field: str,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List distinct values for a field in a MongoDB collection."""
        vals = await asyncio.to_thread(
            lambda: _json_safe(list(_get_db()[collection].distinct(field, filter or {})))
        )
        return {"collection": collection, "field": field, "values": vals}

    return mcp
