"""PostgreSQL FastMCP server with read-only default transactions and safe row caps."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    cleaned = name.strip()
    if not _IDENT_RE.match(cleaned):
        raise ToolError(f"Invalid SQL identifier '{name}'")
    return f'"{cleaned}"'


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.postgresql.allow_mutations:
        raise ToolError(
            "PostgreSQL mutations are disabled by policy. "
            "Set POSTGRES_ALLOW_MUTATIONS=true to enable write queries/DDL."
        )


def create_postgresql_server(
    settings: MCPStackSettings,
    *,
    conn_factory: Callable[[str], Any] | None = None,
    secret_resolver: SecretResolver | None = None,
) -> FastMCP:
    """Create the PostgreSQL MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("postgresql")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "postgresql"))

    def _connect() -> Any:
        resolved_url = resolver.resolve(settings.postgresql.url)
        if not resolved_url:
            raise ToolError(
                "PostgreSQL URL is not configured. Set POSTGRES_URL in .env."
            )
        if conn_factory is not None:
            return conn_factory(resolved_url)
        import psycopg

        try:
            return psycopg.connect(
                resolved_url,
                connect_timeout=int(settings.postgresql.timeout_seconds),
            )
        except Exception as exc:
            raise ToolError(f"Failed to connect to PostgreSQL: {exc}") from exc

    def _run_sql(
        query: str,
        params: list[Any] | None = None,
        *,
        read_only: bool = True,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        if not settings.postgresql.allow_mutations and not read_only:
            _require_mutations(settings)
        cap = min(max_rows or settings.postgresql.max_rows, settings.postgresql.max_rows)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                if read_only and settings.postgresql.allow_mutations is False:
                    cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(query, tuple(params) if params else None)
                if cur.description is not None:
                    cols = [desc[0] for desc in cur.description]
                    fetched = cur.fetchmany(cap)
                    rows = [dict(zip(cols, row, strict=False)) for row in fetched]
                    return {"columns": cols, "rows": rows, "rowCount": len(rows)}
                return {"rowcount": getattr(cur, "rowcount", 0)}
        finally:
            if not read_only:
                conn.commit()
            else:
                conn.rollback()
            conn.close()

    @mcp.tool()
    async def postgres_query(
        query: str,
        params: list[Any] | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Execute a read-only SQL query (READ ONLY tx unless mutations are enabled)."""
        return await asyncio.to_thread(
            _run_sql,
            query,
            params,
            read_only=True,
            max_rows=max_rows,
        )

    @mcp.tool()
    async def postgres_transaction(queries: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute multiple parameterized SQL statements in an atomic transaction."""
        _require_mutations(settings)

        def _exec() -> dict[str, Any]:
            conn = _connect()
            results: list[dict[str, Any]] = []
            try:
                with conn.cursor() as cur:
                    for stmt in queries:
                        sql_text = str(stmt.get("query", ""))
                        p = stmt.get("params") or []
                        cur.execute(sql_text, tuple(p))
                        results.append({"rowcount": getattr(cur, "rowcount", 0)})
                conn.commit()
                return {"committed": True, "statements": len(results), "results": results}
            except Exception as exc:
                conn.rollback()
                raise ToolError(f"PostgreSQL transaction failed: {exc}") from exc
            finally:
                conn.close()

        return await asyncio.to_thread(_exec)

    @mcp.tool()
    async def postgres_list_tables(schema_name: str = "public") -> dict[str, Any]:
        """List tables and views inside a PostgreSQL schema."""
        sql_text = (
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name"
        )
        return await asyncio.to_thread(_run_sql, sql_text, [schema_name], read_only=True)

    @mcp.tool()
    async def postgres_table_info(
        table_name: str,
        schema_name: str = "public",
    ) -> dict[str, Any]:
        """Describe columns, types, and nullability for a PostgreSQL table."""
        sql_text = (
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position"
        )
        return await asyncio.to_thread(
            _run_sql, sql_text, [schema_name, table_name], read_only=True
        )

    @mcp.tool()
    async def postgres_create_table(
        table_name: str,
        columns: dict[str, str],
        if_not_exists: bool = True,
    ) -> dict[str, Any]:
        """Create a PostgreSQL table (requires POSTGRES_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        if not columns:
            raise ToolError("columns mapping cannot be empty")
        col_defs = ", ".join(f"{_safe_ident(k)} {v}" for k, v in columns.items())
        clause = "IF NOT EXISTS " if if_not_exists else ""
        sql_text = f"CREATE TABLE {clause}{_safe_ident(table_name)} ({col_defs})"
        res = await asyncio.to_thread(_run_sql, sql_text, None, read_only=False)
        return {"table": table_name, "created": True, **res}

    @mcp.tool()
    async def postgres_insert(
        table_name: str,
        data: dict[str, Any],
        returning: list[str] | None = None,
    ) -> dict[str, Any]:
        """Insert a row into a PostgreSQL table (requires POSTGRES_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        if not data:
            raise ToolError("data dictionary cannot be empty")
        cols = ", ".join(_safe_ident(c) for c in data)
        placeholders = ", ".join(["%s"] * len(data))
        ret = (
            f" RETURNING {', '.join(_safe_ident(c) for c in returning)}"
            if returning
            else ""
        )
        sql_text = (
            f"INSERT INTO {_safe_ident(table_name)} ({cols}) VALUES ({placeholders}){ret}"
        )
        return await asyncio.to_thread(
            _run_sql, sql_text, list(data.values()), read_only=False
        )

    @mcp.tool()
    async def postgres_update(
        table_name: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> dict[str, Any]:
        """Update rows matching equality predicates (requires POSTGRES_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        if not data or not where:
            raise ToolError("Both data and where clauses are required")
        set_clause = ", ".join(f"{_safe_ident(k)} = %s" for k in data)
        where_clause = " AND ".join(f"{_safe_ident(k)} = %s" for k in where)
        sql_text = f"UPDATE {_safe_ident(table_name)} SET {set_clause} WHERE {where_clause}"
        params = [*data.values(), *where.values()]
        return await asyncio.to_thread(_run_sql, sql_text, params, read_only=False)

    @mcp.tool()
    async def postgres_delete(
        table_name: str,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        """Delete rows matching equality predicates (requires POSTGRES_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        if not where:
            raise ToolError("where clause is required to prevent accidental full-table delete")
        where_clause = " AND ".join(f"{_safe_ident(k)} = %s" for k in where)
        sql_text = f"DELETE FROM {_safe_ident(table_name)} WHERE {where_clause}"
        return await asyncio.to_thread(
            _run_sql, sql_text, list(where.values()), read_only=False
        )

    @mcp.tool()
    async def postgres_select(
        table_name: str,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Select rows from a PostgreSQL table using parameterized equality filters."""
        col_sql = ", ".join(_safe_ident(c) for c in columns) if columns else "*"
        params: list[Any] = []
        where_sql = ""
        if where:
            where_sql = " WHERE " + " AND ".join(f"{_safe_ident(k)} = %s" for k in where)
            params.extend(where.values())
        capped = min(limit, settings.postgresql.max_rows)
        sql_text = f"SELECT {col_sql} FROM {_safe_ident(table_name)}{where_sql} LIMIT %s"
        params.append(capped)
        return await asyncio.to_thread(
            _run_sql, sql_text, params, read_only=True, max_rows=capped
        )

    @mcp.tool()
    async def postgres_stats() -> dict[str, Any]:
        """Return PostgreSQL database size and active connection summary."""
        sql_text = (
            "SELECT current_database() AS database, pg_database_size(current_database()) AS bytes, "
            "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS conns"
        )
        return await asyncio.to_thread(_run_sql, sql_text, None, read_only=True)

    return mcp
