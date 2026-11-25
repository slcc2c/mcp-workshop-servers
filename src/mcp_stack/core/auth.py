"""Pure ASGI gateway authentication, server allowlists, rate limiting, and UC OBO context."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextvars import ContextVar
from http.cookies import SimpleCookie
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack.core.config import ClientPolicy, MCPStackSettings
from mcp_stack.core.logging import get_logger

caller_uc_token_var: ContextVar[str | None] = ContextVar("caller_uc_token", default=None)
caller_client_id_var: ContextVar[str | None] = ContextVar("caller_client_id", default=None)
caller_client_policy_var: ContextVar[ClientPolicy | None] = ContextVar(
    "caller_client_policy", default=None
)
caller_session_id_var: ContextVar[str | None] = ContextVar("caller_session_id", default=None)
caller_profile_var: ContextVar[str | None] = ContextVar("caller_profile", default=None)
caller_auth_method_var: ContextVar[str | None] = ContextVar("caller_auth_method", default=None)

UI_SESSION_COOKIE = "mcp_ui_session"
_CSRF_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EXEMPT_PATHS = frozenset(
    {
        "/",
        "/health",
        "/ready",
        "/metrics",
        "/ui",
        "/ui/login",
        "/api/v1/auth/session",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
    }
)
_SERVER_PATH_RE = re.compile(r"^/servers/([^/]+)/")
_PROFILE_PATH_RE = re.compile(r"^/profiles/([^/]+)/")


def _ui_signing_key(settings: MCPStackSettings) -> bytes:
    """Return HMAC signing key for /ui cookies, derived deterministically if unconfigured."""
    if settings.gateway.ui_session_secret is not None:
        raw = settings.gateway.ui_session_secret.get_secret_value()
        if raw:
            return hashlib.sha256(f"mcp-ui-secret:{raw}".encode()).digest()
    tokens = sorted(settings.gateway.clients.keys())
    seed = "|".join(tokens) if tokens else f"{settings.gateway.host}:{settings.gateway.port}"
    return hashlib.sha256(f"mcp-ui-derived:{seed}".encode()).digest()


def sign_ui_session(
    client_id: str,
    settings: MCPStackSettings,
    *,
    ttl_s: int | None = None,
    now: float | None = None,
) -> str:
    """Create a signed HttpOnly UI session token (<client_id>:<exp>.<sig>)."""
    eff_ttl = max(60, int(ttl_s if ttl_s is not None else settings.gateway.ui_session_ttl_s))
    ts_now = time.time() if now is None else now
    exp = int(ts_now) + eff_ttl
    payload = f"{client_id}:{exp}".encode()
    sig = hmac.new(_ui_signing_key(settings), payload, hashlib.sha256).digest()
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def verify_ui_session(
    cookie_value: str | None,
    settings: MCPStackSettings,
    *,
    now: float | None = None,
) -> str | None:
    """Verify signed UI session cookie and return client_id if valid and unexpired."""
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        payload_b64, sig_b64 = cookie_value.split(".", 1)
        pad_p = payload_b64 + "=" * (-len(payload_b64) % 4)
        pad_s = sig_b64 + "=" * (-len(sig_b64) % 4)
        payload = base64.urlsafe_b64decode(pad_p.encode("ascii"))
        provided_sig = base64.urlsafe_b64decode(pad_s.encode("ascii"))
        expected_sig = hmac.new(_ui_signing_key(settings), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            return None
        decoded = payload.decode("utf-8")
        client_id, exp_str = decoded.rsplit(":", 1)
        exp = int(exp_str)
        ts_now = time.time() if now is None else now
        if exp < ts_now or not client_id:
            return None
        return client_id
    except Exception:
        return None


def find_client_by_id(settings: MCPStackSettings, client_id: str) -> ClientPolicy | None:
    """Look up a configured ClientPolicy by client_id."""
    for policy in settings.gateway.clients.values():
        if policy.client_id == client_id:
            return policy
    return None


def parse_ui_session_cookie(cookie_header: str) -> str | None:
    """Extract UI session cookie value from a raw Cookie header."""
    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    morsel = jar.get(UI_SESSION_COOKIE)
    return morsel.value if morsel is not None else None


class LoginNonceStore:
    """Thread-safe bounded store of single-use 60s UI login nonces."""

    def __init__(
        self,
        *,
        ttl_s: float = 60.0,
        max_entries: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_s = max(5.0, float(ttl_s))
        self._max_entries = max(4, int(max_entries))
        self._clock = clock
        self._lock = threading.Lock()
        self._nonces: dict[str, tuple[str, float]] = {}

    def _prune(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._nonces.items() if exp <= now]
        for k in expired:
            self._nonces.pop(k, None)
        while len(self._nonces) >= self._max_entries:
            oldest_key = next(iter(self._nonces))
            self._nonces.pop(oldest_key, None)

    def issue(self, client_id: str) -> str:
        """Mint a fresh single-use login nonce bound to client_id."""
        now = self._clock()
        nonce = secrets.token_urlsafe(24)
        with self._lock:
            self._prune(now)
            self._nonces[nonce] = (client_id, now + self._ttl_s)
        return nonce

    def consume(self, nonce: str | None) -> str | None:
        """Consume a single-use nonce once and return its client_id, or None if invalid/expired."""
        if not nonce:
            return None
        now = self._clock()
        with self._lock:
            entry = self._nonces.pop(nonce, None)
            if entry is None:
                return None
            client_id, exp = entry
            if exp <= now:
                return None
            return client_id


def is_server_allowed(policy: ClientPolicy | None, server_key_or_slug: str) -> bool:
    """Return True when the given ClientPolicy allows calling tools on the server."""
    if policy is None:
        return True
    allowed = policy.allowed_servers
    if "*" in allowed:
        return True
    norm = server_key_or_slug.strip().replace("-", "_")
    slug = norm.replace("_", "-")
    if norm == "mlflow_upstream":
        return any(k in allowed for k in ("mlflow", "mlflow_upstream", "mlflow-upstream"))
    return any(k in allowed for k in (server_key_or_slug, norm, slug))


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
        auth_method = "open"
        method = str(scope.get("method", "GET")).upper()
        if self._settings.gateway.effective_auth_enabled:
            if bearer_token:
                client_policy = self._settings.gateway.clients.get(bearer_token)
                if client_policy is None:
                    self._logger.warning("Gateway authentication failed", path=path)
                    await self._send_json(
                        send,
                        401,
                        {"error": {"code": "AUTH_FAILED", "message": "Invalid Bearer token"}},
                    )
                    return
                auth_method = "bearer"
            elif path.startswith("/api/v1/"):
                cookie_val = parse_ui_session_cookie(headers.get("cookie", ""))
                cookie_client_id = verify_ui_session(cookie_val, self._settings)
                if cookie_client_id:
                    client_policy = find_client_by_id(self._settings, cookie_client_id)
                if client_policy is None:
                    await self._send_json(
                        send,
                        401,
                        {"error": {"code": "AUTH_REQUIRED", "message": "Missing Bearer token"}},
                    )
                    return
                req_with = headers.get("x-requested-with", "").lower()
                if method in _CSRF_METHODS and req_with != "mcp-ui":
                    await self._send_json(
                        send,
                        403,
                        {
                            "error": {
                                "code": "CSRF_REQUIRED",
                                "message": (
                                    "Cookie-authenticated requests require X-Requested-With header"
                                ),
                            }
                        },
                    )
                    return
                auth_method = "cookie"
            else:
                await self._send_json(
                    send,
                    401,
                    {"error": {"code": "AUTH_REQUIRED", "message": "Missing Bearer token"}},
                )
                return

            server_match = _SERVER_PATH_RE.match(path)
            if server_match:
                slug = server_match.group(1)
                if not is_server_allowed(client_policy, slug):
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
                    disallowed = [
                        srv_key.replace("_", "-")
                        for srv_key in profile_servers
                        if not is_server_allowed(client_policy, srv_key)
                    ]
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

        session_id = headers.get("mcp-session-id", "").strip() or None
        route_profile: str | None = None
        if prof_m := _PROFILE_PATH_RE.match(path):
            route_profile = prof_m.group(1)
        elif srv_m := _SERVER_PATH_RE.match(path):
            route_profile = f"server:{srv_m.group(1)}"
        elif path.startswith("/mcp"):
            route_profile = "full"

        uc_tok = caller_uc_token_var.set(obo_token)
        client_tok = caller_client_id_var.set(
            client_policy.client_id if client_policy else "anonymous"
        )
        policy_tok = caller_client_policy_var.set(client_policy)
        session_tok = caller_session_id_var.set(session_id)
        profile_tok = caller_profile_var.set(route_profile)
        method_tok = caller_auth_method_var.set(auth_method)
        try:
            await self.app(scope, receive, send)
        finally:
            caller_uc_token_var.reset(uc_tok)
            caller_client_id_var.reset(client_tok)
            caller_client_policy_var.reset(policy_tok)
            caller_session_id_var.reset(session_tok)
            caller_profile_var.reset(profile_tok)
            caller_auth_method_var.reset(method_tok)

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
