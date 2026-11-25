"""Redis FastMCP server with read-only defaults and SCAN cursor key listing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.redis.allow_mutations:
        raise ToolError(
            "Redis mutations are disabled by policy. "
            "Set REDIS_ALLOW_MUTATIONS=true to enable key writes, deletes, or pubsub."
        )


def create_redis_server(
    settings: MCPStackSettings,
    *,
    client_factory: Callable[[str], Any] | None = None,
    secret_resolver: SecretResolver | None = None,
) -> FastMCP:
    """Create the Redis MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("redis")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "redis"))

    def _client() -> Any:
        resolved_url = resolver.resolve(settings.redis.url)
        if not resolved_url:
            raise ToolError("Redis URL is not configured. Set REDIS_URL in .env.")
        if client_factory is not None:
            return client_factory(resolved_url)
        import redis

        try:
            return redis.Redis.from_url(
                resolved_url,
                decode_responses=True,
                socket_timeout=settings.redis.timeout_seconds,
            )
        except Exception as exc:
            raise ToolError(f"Failed to connect to Redis: {exc}") from exc

    @mcp.tool()
    async def redis_set(key: str, value: str, ex: int | None = None) -> dict[str, Any]:
        """Set a Redis string key with optional expiration seconds."""
        _require_mutations(settings)
        ok = await asyncio.to_thread(lambda: _client().set(key, value, ex=ex))
        return {"key": key, "ok": bool(ok)}

    @mcp.tool()
    async def redis_get(key: str) -> dict[str, Any]:
        """Get a Redis string value by key."""
        val = await asyncio.to_thread(lambda: _client().get(key))
        return {"key": key, "value": val}

    @mcp.tool()
    async def redis_delete(keys: list[str]) -> dict[str, Any]:
        """Delete one or more Redis keys."""
        _require_mutations(settings)
        deleted = await asyncio.to_thread(lambda: _client().delete(*keys) if keys else 0)
        return {"deleted": int(deleted)}

    @mcp.tool()
    async def redis_exists(keys: list[str]) -> dict[str, Any]:
        """Count how many of the given Redis keys exist."""
        count = await asyncio.to_thread(lambda: _client().exists(*keys) if keys else 0)
        return {"exists": int(count)}

    @mcp.tool()
    async def redis_keys(pattern: str = "*", limit: int | None = None) -> dict[str, Any]:
        """Scan Redis keys matching a glob pattern without blocking KEYS."""
        cap = min(limit or settings.redis.max_keys, settings.redis.max_keys)

        def _scan() -> list[str]:
            cli = _client()
            found: list[str] = []
            for key in cli.scan_iter(match=pattern, count=min(cap, 200)):
                found.append(str(key))
                if len(found) >= cap:
                    break
            return found

        found_keys = await asyncio.to_thread(_scan)
        return {"pattern": pattern, "keys": found_keys, "count": len(found_keys)}

    @mcp.tool()
    async def redis_hset(key: str, mapping: dict[str, Any]) -> dict[str, Any]:
        """Set fields inside a Redis hash."""
        _require_mutations(settings)
        count = await asyncio.to_thread(lambda: _client().hset(key, mapping=mapping))
        return {"key": key, "added": int(count)}

    @mcp.tool()
    async def redis_hget(key: str, field: str | None = None) -> dict[str, Any]:
        """Get one field or all fields from a Redis hash."""
        if field is not None:
            val = await asyncio.to_thread(lambda: _client().hget(key, field))
            return {"key": key, "field": field, "value": val}
        vals = await asyncio.to_thread(lambda: _client().hgetall(key))
        return {"key": key, "fields": dict(vals)}

    @mcp.tool()
    async def redis_list_push(
        key: str,
        values: list[str],
        direction: Literal["left", "right"] = "right",
    ) -> dict[str, Any]:
        """Push items onto a Redis list."""
        _require_mutations(settings)

        def _push() -> int:
            cli = _client()
            return int(cli.lpush(key, *values) if direction == "left" else cli.rpush(key, *values))

        length = await asyncio.to_thread(_push)
        return {"key": key, "length": length}

    @mcp.tool()
    async def redis_list_range(key: str, start: int = 0, stop: int = -1) -> dict[str, Any]:
        """Read a slice of elements from a Redis list."""
        items = await asyncio.to_thread(lambda: list(_client().lrange(key, start, stop)))
        return {"key": key, "items": items}

    @mcp.tool()
    async def redis_set_add(key: str, members: list[str]) -> dict[str, Any]:
        """Add members to a Redis set."""
        _require_mutations(settings)
        added = await asyncio.to_thread(lambda: _client().sadd(key, *members) if members else 0)
        return {"key": key, "added": int(added)}

    @mcp.tool()
    async def redis_set_members(key: str) -> dict[str, Any]:
        """Return all members of a Redis set."""
        members = await asyncio.to_thread(lambda: sorted(str(x) for x in _client().smembers(key)))
        return {"key": key, "members": members}

    @mcp.tool()
    async def redis_set_operations(
        operation: Literal["union", "intersect", "diff"],
        keys: list[str],
    ) -> dict[str, Any]:
        """Compute union, intersection, or difference across Redis sets."""
        if not keys:
            raise ToolError("At least one key is required")

        def _op() -> list[str]:
            cli = _client()
            if operation == "union":
                raw = cli.sunion(keys)
            elif operation == "intersect":
                raw = cli.sinter(keys)
            else:
                raw = cli.sdiff(keys)
            return sorted(str(x) for x in raw)

        return {"operation": operation, "members": await asyncio.to_thread(_op)}

    @mcp.tool()
    async def redis_zadd(key: str, mapping: dict[str, float]) -> dict[str, Any]:
        """Add scored members to a Redis sorted set."""
        _require_mutations(settings)
        added = await asyncio.to_thread(lambda: _client().zadd(key, mapping))
        return {"key": key, "added": int(added)}

    @mcp.tool()
    async def redis_zrange(
        key: str,
        start: int = 0,
        stop: int = -1,
        withscores: bool = False,
    ) -> dict[str, Any]:
        """Read a range from a Redis sorted set."""
        items = await asyncio.to_thread(
            lambda: list(_client().zrange(key, start, stop, withscores=withscores))
        )
        return {"key": key, "items": items}

    @mcp.tool()
    async def redis_publish(channel: str, message: str) -> dict[str, Any]:
        """Publish a message to a Redis pub/sub channel."""
        _require_mutations(settings)
        receivers = await asyncio.to_thread(lambda: _client().publish(channel, message))
        return {"channel": channel, "receivers": int(receivers)}

    @mcp.tool()
    async def redis_subscribe(
        channels: list[str],
        max_messages: int = 5,
        timeout_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """Poll messages from Redis pub/sub channels cleanly within timeout."""
        _require_mutations(settings)

        def _poll() -> list[dict[str, Any]]:
            pubsub = _client().pubsub()
            pubsub.subscribe(*channels)
            captured: list[dict[str, Any]] = []
            try:
                while len(captured) < max_messages:
                    msg = pubsub.get_message(timeout=timeout_seconds)
                    if msg is None:
                        break
                    if msg.get("type") == "message":
                        captured.append(dict(msg))
            finally:
                pubsub.close()
            return captured

        msgs = await asyncio.to_thread(_poll)
        return {"channels": channels, "messages": msgs}

    @mcp.tool()
    async def redis_expire(key: str, seconds: int) -> dict[str, Any]:
        """Set a TTL expiration in seconds on a Redis key."""
        _require_mutations(settings)
        ok = await asyncio.to_thread(lambda: _client().expire(key, seconds))
        return {"key": key, "ok": bool(ok)}

    @mcp.tool()
    async def redis_ttl(key: str) -> dict[str, Any]:
        """Inspect remaining TTL in seconds for a Redis key."""
        ttl_val = await asyncio.to_thread(lambda: _client().ttl(key))
        return {"key": key, "ttl": int(ttl_val)}

    @mcp.tool()
    async def redis_info(section: str | None = None) -> dict[str, Any]:
        """Return Redis server INFO diagnostics."""
        info = await asyncio.to_thread(
            lambda: _client().info(section) if section else _client().info()
        )
        return {"section": section or "default", "info": dict(info)}

    @mcp.tool()
    async def redis_pipeline(commands: list[list[Any]]) -> dict[str, Any]:
        """Execute batched Redis commands via pipeline (requires REDIS_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)

        def _exec() -> list[Any]:
            pipe = _client().pipeline()
            for cmd in commands:
                if not cmd:
                    continue
                pipe.execute_command(*cmd)
            return list(pipe.execute())

        results = await asyncio.to_thread(_exec)
        return {"results": results}

    return mcp
