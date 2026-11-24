"""Mocked unit tests for Tier-2 database MCP servers (PG, Redis, Mongo, Neo4j)."""

from __future__ import annotations

import json
import sys
import types

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_stack.servers.mongodb import create_mongodb_server
from mcp_stack.servers.neo4j_server import create_neo4j_server
from mcp_stack.servers.postgresql import create_postgresql_server
from mcp_stack.servers.redis_server import create_redis_server


async def test_postgresql_read_only_and_mutation_gating(make_settings) -> None:
    settings = make_settings()
    settings.postgresql.url = "postgresql://user:pass@localhost:5432/db"  # type: ignore[assignment]
    executed: list[tuple[str, tuple | None]] = []

    class FakeCursor:
        description = [("id",), ("name",)]
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            executed.append((sql, params))

        def fetchmany(self, n):
            return [(1, "alpha")][:n]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    srv = create_postgresql_server(settings, conn_factory=lambda _u: FakeConn())
    async with Client(srv) as client:
        res = await client.call_tool("postgres_select", {"table_name": "users", "where": {"id": 1}})
        payload = json.loads(res.content[0].text)
        assert payload["rows"] == [{"id": 1, "name": "alpha"}]
        assert any("SET TRANSACTION READ ONLY" in s for s, _ in executed)

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("postgres_insert", {"table_name": "users", "data": {"id": 2}})


async def test_postgresql_missing_url_raises_tool_error(make_settings) -> None:
    srv = create_postgresql_server(make_settings())
    async with Client(srv) as client:
        with pytest.raises(ToolError, match="POSTGRES_URL"):
            await client.call_tool("postgres_stats", {})


async def test_redis_read_scan_and_mutation_gating(make_settings) -> None:
    settings = make_settings()
    settings.redis.url = "redis://localhost:6379/0"  # type: ignore[assignment]

    class FakeRedis:
        def get(self, key):
            return f"val:{key}"

        def scan_iter(self, match="*", count=200):
            yield "k1"
            yield "k2"

    srv = create_redis_server(settings, client_factory=lambda _u: FakeRedis())
    async with Client(srv) as client:
        val = await client.call_tool("redis_get", {"key": "hello"})
        assert json.loads(val.content[0].text)["value"] == "val:hello"
        keys = await client.call_tool("redis_keys", {"pattern": "k*"})
        assert json.loads(keys.content[0].text)["keys"] == ["k1", "k2"]

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("redis_set", {"key": "x", "value": "1"})


async def test_mongodb_read_and_pipeline_write_gate(make_settings) -> None:
    settings = make_settings()
    settings.mongodb.uri = "mongodb://localhost:27017"  # type: ignore[assignment]

    class FakeCursor:
        def limit(self, _n):
            return [{"_id": "1", "name": "doc1"}]

    class FakeCollection:
        def find(self, filt, proj=None):
            return FakeCursor()

        def count_documents(self, filt):
            return 1

    class FakeDB:
        def __getitem__(self, _name):
            return FakeCollection()

        def list_collection_names(self):
            return ["items"]

    srv = create_mongodb_server(settings, db_factory=lambda _u, _d: FakeDB())
    async with Client(srv) as client:
        docs = await client.call_tool("mongodb_find", {"collection": "items"})
        assert json.loads(docs.content[0].text)["count"] == 1

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool(
                "mongodb_aggregate",
                {"collection": "items", "pipeline": [{"$out": "other"}]},
            )


async def test_neo4j_read_routing_and_mutation_gating(make_settings, monkeypatch) -> None:
    settings = make_settings()
    settings.neo4j.uri = "bolt://localhost:7687"
    seen_routing: list[object] = []

    fake_neo4j = types.SimpleNamespace(RoutingControl=types.SimpleNamespace(READ="READ"))
    monkeypatch.setitem(sys.modules, "neo4j", fake_neo4j)

    class FakeDriver:
        def execute_query(self, cypher, parameters_=None, **kwargs):
            seen_routing.append(kwargs.get("routing_"))
            return [{"cnt": 3}], None, ["cnt"]

        def close(self):
            pass

    srv = create_neo4j_server(settings, driver_factory=lambda _u, _user, _pw: FakeDriver())
    async with Client(srv) as client:
        res = await client.call_tool("neo4j_query", {"cypher": "MATCH (n) RETURN count(n) AS cnt"})
        assert json.loads(res.content[0].text)["records"] == [{"cnt": 3}]
        assert seen_routing == ["READ"]

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("neo4j_create_node", {"label": "Person"})
