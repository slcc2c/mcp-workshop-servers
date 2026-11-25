"""Live integration tests against --profile tier2 Docker databases."""

from __future__ import annotations

import json
import os

import psycopg
import pymongo
import pytest
import redis
from fastmcp import Client
from fastmcp.exceptions import ToolError
from neo4j import GraphDatabase

from mcp_stack.core.config import (
    MCPStackSettings,
    MongoDBSettings,
    Neo4jSettings,
    PostgreSQLSettings,
    RedisSettings,
)
from mcp_stack.servers.mongodb import create_mongodb_server
from mcp_stack.servers.neo4j_server import create_neo4j_server
from mcp_stack.servers.postgresql import create_postgresql_server
from mcp_stack.servers.redis_server import create_redis_server

pytestmark = pytest.mark.tier2


def _tier2_settings(tmp_path) -> MCPStackSettings:
    pg_port = int(os.getenv("TIER2_POSTGRES_PORT", "15432"))
    redis_port = int(os.getenv("TIER2_REDIS_PORT", "16379"))
    mongo_port = int(os.getenv("TIER2_MONGODB_PORT", "27018"))
    neo4j_bolt = int(os.getenv("TIER2_NEO4J_BOLT_PORT", "17687"))

    return MCPStackSettings(
        _env_file=None,
        postgresql=PostgreSQLSettings(
            url=f"postgresql://postgres:postgres@127.0.0.1:{pg_port}/mcp_workshop",  # type: ignore[arg-type]
            allow_mutations=False,
        ),
        redis=RedisSettings(
            url=f"redis://127.0.0.1:{redis_port}/0",  # type: ignore[arg-type]
            allow_mutations=False,
        ),
        mongodb=MongoDBSettings(
            uri=f"mongodb://127.0.0.1:{mongo_port}",  # type: ignore[arg-type]
            database="mcp_workshop_tier2",
            allow_mutations=False,
        ),
        neo4j=Neo4jSettings(
            uri=f"bolt://127.0.0.1:{neo4j_bolt}",
            user="neo4j",
            password="mcpworkshop123",  # type: ignore[arg-type]
            database="neo4j",
            allow_mutations=False,
        ),
    )


async def test_tier2_postgresql_live_reads_and_readonly_guard(tmp_path) -> None:
    settings = _tier2_settings(tmp_path)
    pg_url = settings.postgresql.url.get_secret_value()  # type: ignore[union-attr]
    with psycopg.connect(pg_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tier2_items (id INT PRIMARY KEY, label TEXT NOT NULL)"
        )
        cur.execute(
            "INSERT INTO tier2_items (id, label) VALUES (1, 'pg-live-ok') "
            "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label"
        )

    srv = create_postgresql_server(settings)
    async with Client(srv) as client:
        tables = await client.call_tool("postgres_list_tables", {})
        assert "tier2_items" in tables.content[0].text
        rows = await client.call_tool(
            "postgres_select",
            {"table_name": "tier2_items", "where": {"id": 1}},
        )
        payload = json.loads(rows.content[0].text)
        assert payload["rows"][0]["label"] == "pg-live-ok"

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool(
                "postgres_insert",
                {"table_name": "tier2_items", "data": {"id": 99, "label": "blocked"}},
            )


async def test_tier2_redis_live_reads_and_readonly_guard(tmp_path) -> None:
    settings = _tier2_settings(tmp_path)
    rcli = redis.Redis.from_url(
        settings.redis.url.get_secret_value(), decode_responses=True  # type: ignore[union-attr]
    )
    rcli.set("tier2:probe", "redis-live-ok", ex=120)
    rcli.close()

    srv = create_redis_server(settings)
    async with Client(srv) as client:
        val = await client.call_tool("redis_get", {"key": "tier2:probe"})
        assert json.loads(val.content[0].text)["value"] == "redis-live-ok"

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("redis_set", {"key": "tier2:blocked", "value": "no"})


async def test_tier2_mongodb_live_reads_and_readonly_guard(tmp_path) -> None:
    settings = _tier2_settings(tmp_path)
    mcli = pymongo.MongoClient(
        settings.mongodb.uri.get_secret_value(),  # type: ignore[union-attr]
        serverSelectionTimeoutMS=5000,
    )
    db = mcli[settings.mongodb.database]
    db["tier2_docs"].delete_many({"_id": "t2-1"})
    db["tier2_docs"].insert_one({"_id": "t2-1", "status": "mongo-live-ok"})
    mcli.close()

    srv = create_mongodb_server(settings)
    async with Client(srv) as client:
        found = await client.call_tool(
            "mongodb_find",
            {"collection": "tier2_docs", "filter": {"_id": "t2-1"}},
        )
        payload = json.loads(found.content[0].text)
        assert payload["count"] == 1
        assert payload["documents"][0]["status"] == "mongo-live-ok"

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool(
                "mongodb_insert_one",
                {"collection": "tier2_docs", "document": {"_id": "blocked"}},
            )


async def test_tier2_neo4j_live_reads_and_readonly_guard(tmp_path) -> None:
    settings = _tier2_settings(tmp_path)
    pw = settings.neo4j.password.get_secret_value()  # type: ignore[union-attr]
    driver = GraphDatabase.driver(settings.neo4j.uri, auth=(settings.neo4j.user, pw))
    driver.execute_query(
        "MERGE (:Tier2Probe {name: 'neo4j-live-ok'})",
        database_=settings.neo4j.database,
    )
    driver.close()

    srv = create_neo4j_server(settings)
    async with Client(srv) as client:
        res = await client.call_tool(
            "neo4j_query",
            {"cypher": "MATCH (n:Tier2Probe) RETURN n.name AS name LIMIT 1"},
        )
        payload = json.loads(res.content[0].text)
        assert payload["records"][0]["name"] == "neo4j-live-ok"

        with pytest.raises(ToolError, match="disabled by policy"):
            await client.call_tool("neo4j_create_node", {"label": "BlockedNode"})
