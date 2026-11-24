"""Pure ASGI gateway authentication, server allowlists, rate limiting, and UC OBO context."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack.core.config import ClientPolicy, MCPStackSettings
from mcp_stack.core.logging import get_logger

caller_uc_token_var: ContextVar[str | None] = ContextVar("caller_uc_token", default=None)
caller_client_id_var: ContextVar[str | None] = ContextVar("caller_client_id", default=None)

_EXEMPT_PATHS = frozenset({"/", "/health", "/ready", "/metrics"})
_SERVER_PATH_RE = re.compile(r"^/servers/([^/]+)/")
_PROFILE_PATH_RE = re.compile(r"^/profiles/([^/]+)/")


class GatewayAuthMiddleware:
    """Streaming-safe pure ASGI middleware for Bearer auth, rate limits, and OBO UC tokens."""

    def __init__(
        self,
        app: ASGIApp,
        settings: MCPStackSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self._settings = settings
        self._clock = clock
        self._logger = get_logger("gateway.auth")
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        auth_header = headers.get("authorization", "")
        bearer_token = (
            auth_header[7:].strip()
            if auth_header.lower().startswith("bearer ")
            else ""
        )
        explicit_uc_token = headers.get("x-uc-token", "").strip()

        client_policy: ClientPolicy | None = None
        if self._settings.gateway.effective_auth_enabled:
            if not bearer_token:
                await self._send_json(
                    send,
                    401,
                    {"error": {"code": "AUTH_REQUIRED", "message": "Missing Bearer token"}},
                )
                return

            client_policy = self._settings.gateway.clients.get(bearer_token)
            if client_policy is None:
                self._logger.warning("Gateway authentication failed", path=path)
                await self._send_json(
                    send,
                    401,
                    {"error": {"code": "AUTH_FAILED", "message": "Invalid Bearer token"}},
                )
                return

            server_match = _SERVER_PATH_RE.match(path)
            if server_match:
                slug = server_match.group(1)
                normalized = slug.replace("-", "_")
                allowed = client_policy.allowed_servers
                if (
                    "*" not in allowed
                    and slug not in allowed
                    and normalized not in allowed
                ):
                    await self._send_json(
                        send,
                        403,
                        {
                            "error": {
                                "code": "FORBIDDEN",
                                "message": (
                                    f"Client '{client_policy.client_name}' is not allowed "
                                    f"to access server '{slug}'"
                                ),
                            }
                        },
                    )
                    return

            profile_match = _PROFILE_PATH_RE.match(path)
            if profile_match:
                profile_name = profile_match.group(1)
                profile_servers = self._settings.gateway.profiles.get(profile_name)
                if profile_servers is not None:
                    allowed = client_policy.allowed_servers
                    if "*" not in allowed:
                        disallowed: list[str] = []
                        for srv_key in profile_servers:
                            norm = srv_key.replace("-", "_")
                            slug_val = norm.replace("_", "-")
                            if norm == "mlflow_upstream":
                                ok = any(
                                    k in allowed
                                    for k in ("mlflow", "mlflow_upstream", "mlflow-upstream")
                                )
                            else:
                                ok = any(k in allowed for k in (srv_key, norm, slug_val))
                            if not ok:
                                disallowed.append(slug_val)
                        if disallowed:
                            await self._send_json(
                                send,
                                403,
                                {
                                    "error": {
                                        "code": "FORBIDDEN",
                                        "message": (
                                            f"Client '{client_policy.client_name}' is not allowed "
                                            f"to access profile '{profile_name}' "
                                            f"(disallowed servers: {', '.join(disallowed)})"
                                        ),
                                    }
                                },
                            )
                            return

            if not self._check_rate_limit(client_policy):
                await self._send_json(
                    send,
                    429,
                    {
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": f"Rate limit exceeded for '{client_policy.client_name}'",
                        }
                    },
                )
                return

        obo_token: str | None = None
        if explicit_uc_token:
            obo_token = explicit_uc_token
        elif (
            self._settings.unity_catalog.allow_obo_passthrough
            and not self._settings.gateway.effective_auth_enabled
            and bearer_token
        ):
            obo_token = bearer_token

        uc_tok = caller_uc_token_var.set(obo_token)
        client_tok = caller_client_id_var.set(
            client_policy.client_id if client_policy else "anonymous"
        )
        try:
            await self.app(scope, receive, send)
        finally:
            caller_uc_token_var.reset(uc_tok)
            caller_client_id_var.reset(client_tok)

    def _check_rate_limit(self, policy: ClientPolicy) -> bool:
        now = self._clock()
        window = self._windows[policy.client_id]
        cutoff = now - policy.rate_limit_window_s
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= policy.rate_limit_max:
            return False
        window.append(now)
        return True

    @staticmethod
    async def _send_json(send: Send, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
