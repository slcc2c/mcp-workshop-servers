"""Neo4j graph database FastMCP server with READ routing by default."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_label(name: str) -> str:
    cleaned = name.strip()
    if not _LABEL_RE.match(cleaned):
        raise ToolError(f"Invalid Neo4j label/type identifier '{name}'")
    return cleaned


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.neo4j.allow_mutations:
        raise ToolError(
            "Neo4j mutations are disabled by policy. "
            "Set NEO4J_ALLOW_MUTATIONS=true to enable graph writes/DDL."
        )


def create_neo4j_server(
    settings: MCPStackSettings,
    *,
    driver_factory: Callable[[str, str, str], Any] | None = None,
    secret_resolver: SecretResolver | None = None,
) -> FastMCP:
    """Create the Neo4j MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("neo4j")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "neo4j"))

    def _get_driver() -> Any:
        uri = settings.neo4j.uri or ""
        if not uri:
            raise ToolError("Neo4j URI is not configured. Set NEO4J_URI in .env.")
        pw = resolver.resolve(settings.neo4j.password) or ""
        if driver_factory is not None:
            return driver_factory(uri, settings.neo4j.user, pw)
        import neo4j

        try:
            return neo4j.GraphDatabase.driver(uri, auth=(settings.neo4j.user, pw))
        except Exception as exc:
            raise ToolError(f"Failed to create Neo4j driver: {exc}") from exc

    def _exec_cypher(
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        read_only: bool = True,
    ) -> dict[str, Any]:
        if not settings.neo4j.allow_mutations and not read_only:
            _require_mutations(settings)
        driver = _get_driver()
        try:
            kwargs: dict[str, Any] = {"database_": settings.neo4j.database}
            if read_only:
                import neo4j

                kwargs["routing_"] = neo4j.RoutingControl.READ
            records, summary, keys = driver.execute_query(
                cypher, parameters_=params or {}, **kwargs
            )
            cap = settings.neo4j.max_records
            rows = [dict(r) for r in list(records)[:cap]]
            counters = getattr(summary, "counters", None)
            return {
                "keys": list(keys),
                "records": rows,
                "count": len(rows),
                "nodesCreated": getattr(counters, "nodes_created", 0) if counters else 0,
            }
        finally:
            driver.close()

    @mcp.tool()
    async def neo4j_query(
        cypher: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a Cypher query (READ routing unless NEO4J_ALLOW_MUTATIONS=true enables writes)."""
        return await asyncio.to_thread(_exec_cypher, cypher, params, read_only=True)

    @mcp.tool()
    async def neo4j_create_node(
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a node with the given label and properties."""
        _require_mutations(settings)
        lbl = _safe_label(label)
        cypher = f"CREATE (n:{lbl} $props) RETURN n, elementId(n) AS id"
        return await asyncio.to_thread(
            _exec_cypher, cypher, {"props": properties or {}}, read_only=False
        )

    @mcp.tool()
    async def neo4j_create_relationship(
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relationship between two nodes identified by elementId."""
        _require_mutations(settings)
        rtype = _safe_label(rel_type)
        cypher = (
            f"MATCH (a), (b) WHERE elementId(a) = $from_id AND elementId(b) = $to_id "
            f"CREATE (a)-[r:{rtype} $props]->(b) RETURN r, elementId(r) AS id"
        )
        return await asyncio.to_thread(
            _exec_cypher,
            cypher,
            {"from_id": from_id, "to_id": to_id, "props": properties or {}},
            read_only=False,
        )

    @mcp.tool()
    async def neo4j_find_nodes(
        label: str | None = None,
        properties: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find nodes by optional label and property equality filters."""
        lbl = f":{_safe_label(label)}" if label else ""
        props = properties or {}
        where = (
            " WHERE " + " AND ".join(f"n.{_safe_label(k)} = ${k}" for k in props) if props else ""
        )
        cypher = f"MATCH (n{lbl}){where} RETURN n, elementId(n) AS id LIMIT $limit"
        return await asyncio.to_thread(
            _exec_cypher,
            cypher,
            {**props, "limit": min(limit, settings.neo4j.max_records)},
            read_only=True,
        )

    @mcp.tool()
    async def neo4j_find_path(
        from_id: str,
        to_id: str,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        """Find shortest paths between two nodes up to max_depth hops."""
        depth = max(1, min(max_depth, 8))
        cypher = (
            f"MATCH p = shortestPath((a)-[*..{depth}]-(b)) "
            "WHERE elementId(a) = $from_id AND elementId(b) = $to_id "
            "RETURN [n IN nodes(p) | elementId(n)] AS nodeIds, length(p) AS hops"
        )
        return await asyncio.to_thread(
            _exec_cypher, cypher, {"from_id": from_id, "to_id": to_id}, read_only=True
        )

    @mcp.tool()
    async def neo4j_update_node(
        node_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge properties onto an existing node by elementId."""
        _require_mutations(settings)
        cypher = "MATCH (n) WHERE elementId(n) = $node_id SET n += $props RETURN n"
        return await asyncio.to_thread(
            _exec_cypher, cypher, {"node_id": node_id, "props": properties}, read_only=False
        )

    @mcp.tool()
    async def neo4j_delete_node(node_id: str, detach: bool = True) -> dict[str, Any]:
        """Delete a node by elementId."""
        _require_mutations(settings)
        kw = "DETACH DELETE" if detach else "DELETE"
        cypher = f"MATCH (n) WHERE elementId(n) = $node_id {kw} n"
        return await asyncio.to_thread(_exec_cypher, cypher, {"node_id": node_id}, read_only=False)

    @mcp.tool()
    async def neo4j_create_index(
        label: str,
        property_name: str,
        index_type: Literal["range", "point", "fulltext"] = "range",
    ) -> dict[str, Any]:
        """Create a Neo4j property index."""
        _require_mutations(settings)
        lbl = _safe_label(label)
        prop = _safe_label(property_name)
        prefix = f"{index_type.upper()} " if index_type != "range" else ""
        if index_type == "fulltext":
            cypher = f"CREATE FULLTEXT INDEX IF NOT EXISTS FOR (n:{lbl}) ON EACH [n.{prop}]"
        else:
            cypher = f"CREATE {prefix}INDEX IF NOT EXISTS FOR (n:{lbl}) ON (n.{prop})"
        return await asyncio.to_thread(_exec_cypher, cypher, None, read_only=False)

    @mcp.tool()
    async def neo4j_create_constraint(
        label: str,
        property_name: str,
        constraint_type: Literal["unique", "exists", "key"] = "unique",
    ) -> dict[str, Any]:
        """Create a Neo4j schema constraint."""
        _require_mutations(settings)
        lbl = _safe_label(label)
        prop = _safe_label(property_name)
        if constraint_type == "unique":
            clause = "IS UNIQUE"
        elif constraint_type == "exists":
            clause = "IS NOT NULL"
        else:
            clause = "IS NODE KEY"
        cypher = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{lbl}) REQUIRE n.{prop} {clause}"
        return await asyncio.to_thread(_exec_cypher, cypher, None, read_only=False)

    @mcp.tool()
    async def neo4j_schema() -> dict[str, Any]:
        """Inspect node labels, relationship types, and property keys in Neo4j."""
        cypher = "CALL db.schema.visualization()"
        return await asyncio.to_thread(_exec_cypher, cypher, None, read_only=True)

    @mcp.tool()
    async def neo4j_stats() -> dict[str, Any]:
        """Return total node and relationship counts per label/type."""
        cypher = "MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r) AS rels"
        return await asyncio.to_thread(_exec_cypher, cypher, None, read_only=True)

    @mcp.tool()
    async def neo4j_algorithm(
        algorithm: Literal["pagerank", "centrality", "similarity"],
        label: str = "Entity",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Run a lightweight graph degree/centrality summary query without GDS dependency."""
        lbl = _safe_label(label)
        if algorithm in {"pagerank", "centrality"}:
            cypher = (
                f"MATCH (n:{lbl})-[r]-() "
                "RETURN elementId(n) AS id, count(r) AS degree ORDER BY degree DESC LIMIT $limit"
            )
        else:
            cypher = (
                f"MATCH (a:{lbl})--(common)--(b:{lbl}) WHERE elementId(a) < elementId(b) "
                "RETURN elementId(a) AS source, elementId(b) AS target, count(common) AS shared "
                "ORDER BY shared DESC LIMIT $limit"
            )
        res = await asyncio.to_thread(
            _exec_cypher, cypher, {"limit": limit}, read_only=True
        )
        return {"algorithm": algorithm, **res}

    return mcp
