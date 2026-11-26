"""Thread-safe sanitized gateway activity ring buffer and SSE pub/sub stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from mcp_stack.core.tracing import redact_payload


class ActivityBus:
    """In-memory ring buffer and async subscriber fan-out for live gateway events."""

    def __init__(self, *, maxlen: int = 200) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = (
            set()
        )
        self._seq = 0

    def record(
        self,
        event_type: str,
        *,
        status: str = "ok",
        server: str | None = None,
        tool: str | None = None,
        duration_ms: float | None = None,
        trace_id: str | None = None,
        summary: str = "",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_detail = redact_payload(detail or {}) if detail else {}
        with self._lock:
            self._seq += 1
            entry: dict[str, Any] = {
                "id": self._seq,
                "timestamp": datetime.now(UTC).isoformat(),
                "epochMs": int(time.time() * 1000),
                "type": event_type,
                "status": status,
                "server": server,
                "tool": tool,
                "durationMs": round(float(duration_ms), 2) if duration_ms is not None else None,
                "traceId": trace_id,
                "summary": summary[:240],
                "detail": clean_detail,
            }
            self._events.append(entry)
            subs = list(self._subscribers)

        for loop, queue in subs:
            if loop.is_closed():
                continue
            loop.call_soon_threadsafe(self._push_nonblocking, queue, entry)
        return entry

    @staticmethod
    def _push_nonblocking(queue: asyncio.Queue[dict[str, Any]], entry: dict[str, Any]) -> None:
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(entry)

    def recent(self, *, limit: int = 50, event_type: str | None = None) -> list[dict[str, Any]]:
        clamped = max(1, min(limit, 200))
        with self._lock:
            items = list(self._events)
        if event_type:
            items = [e for e in items if e.get("type") == event_type]
        return list(reversed(items[-clamped:]))

    def metrics_series(
        self,
        *,
        bucket_seconds: int = 300,
        buckets: int = 12,
    ) -> list[dict[str, Any]]:
        """Aggregate recent recorded calls into time buckets with p50/p95 and error rates."""
        now_ms = int(time.time() * 1000)
        bucket_ms = max(30, bucket_seconds) * 1000
        start_ms = now_ms - buckets * bucket_ms
        with self._lock:
            snapshot = [e for e in self._events if (e.get("epochMs") or 0) >= start_ms]

        grouped: list[list[dict[str, Any]]] = [[] for _ in range(buckets)]
        for ev in snapshot:
            idx = int(((ev.get("epochMs") or start_ms) - start_ms) // bucket_ms)
            if 0 <= idx < buckets:
                grouped[idx].append(ev)

        series: list[dict[str, Any]] = []
        for idx, items in enumerate(grouped):
            bucket_ts = start_ms + (idx + 1) * bucket_ms
            durations = sorted(
                float(i["durationMs"])
                for i in items
                if isinstance(i.get("durationMs"), (int, float))
            )
            errors = sum(1 for i in items if i.get("status") not in {"ok", "policy_refusal"})
            p50 = durations[len(durations) // 2] if durations else 0.0
            p95_idx = min(len(durations) - 1, int(len(durations) * 0.95)) if durations else 0
            p95 = durations[p95_idx] if durations else 0.0
            series.append(
                {
                    "timestampMs": bucket_ts,
                    "label": datetime.fromtimestamp(bucket_ts / 1000, tz=UTC).strftime("%H:%M"),
                    "count": len(items),
                    "errorCount": errors,
                    "errorRate": round(errors / len(items), 4) if items else 0.0,
                    "p50Ms": round(p50, 1),
                    "p95Ms": round(p95, 1),
                }
            )
        return series

    async def stream_sse(
        self,
        *,
        replay_limit: int = 25,
        keepalive_s: float = 15.0,
    ) -> AsyncIterator[str]:
        """Yield Server-Sent Events frames starting with a backlog snapshot."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        sub = (loop, queue)
        with self._lock:
            backlog = list(self._events)[-replay_limit:]
            self._subscribers.add(sub)

        try:
            init_payload = json.dumps({"type": "snapshot", "events": backlog})
            yield f"event: snapshot\ndata: {init_payload}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
                    yield f"event: activity\ndata: {json.dumps(item)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(sub)
