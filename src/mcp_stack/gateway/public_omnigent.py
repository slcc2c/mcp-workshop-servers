"""Hardened public Google OAuth 2.1 HTTPS connector for the 12 Omnigent MCP tools."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastmcp.server.auth.providers.google import GoogleProvider
from mcp.server.auth.provider import AccessToken, RegistrationError
from mcp.shared.auth import OAuthClientInformationFull
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.servers.omnigent import create_omnigent_server

DEFAULT_PUBLIC_URL = "https://omnigent-mcp.slcc2c.com"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8768
DEFAULT_ENV_FILE = Path("/Users/spencer/.config/mcp-stack/omnigent-public.env")
DEFAULT_OFF_FILE = Path("/Users/spencer/.local/share/mcp-stack/omnigent-public/OFF")
DEFAULT_REFUSAL_LOG = Path("/Users/spencer/Library/Logs/mcp-stack/omnigent-public-refusals.jsonl")

CLAUDE_CALLBACK_URIS = frozenset(
    {
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
    }
)
CHATGPT_EXACT_CALLBACK_URIS = frozenset(
    {
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://platform.openai.com/apps-manage/oauth",
    }
)
ALLOWED_CLIENT_ORIGINS = frozenset(
    {
        "https://claude.ai",
        "https://claude.com",
        "https://chatgpt.com",
        "https://chat.openai.com",
        "https://platform.openai.com",
    }
)
QUIET_404_PATHS = frozenset({"/", "/favicon.ico", "/robots.txt"})
AUTH_RATE_LIMIT_PREFIXES = ("/authorize", "/register", "/token", "/auth/")
GOOGLE_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
_EMAIL_RE = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")

LOG = get_logger("gateway.public_omnigent")


@dataclass(frozen=True)
class PublicOmnigentConfig:
    """Validated fail-closed configuration for omnigent-public-mcp."""

    google_client_id: str
    google_client_secret: str
    public_url: str
    allowed_emails: frozenset[str]
    host: str = DEFAULT_BIND_HOST
    port: int = DEFAULT_PORT
    jwt_signing_key: str | None = None
    off_file: Path = field(default_factory=lambda: DEFAULT_OFF_FILE)
    refusal_log: Path = field(default_factory=lambda: DEFAULT_REFUSAL_LOG)
    mcp_per_ip_per_min: int = 120
    auth_per_ip_per_min: int = 15
    lockout_after: int = 15
    lockout_window_s: int = 600
    lockout_s: int = 900

    @property
    def public_host(self) -> str:
        return (urlsplit(self.public_url).hostname or "").lower()

    @property
    def effective_jwt_signing_key(self) -> str:
        if self.jwt_signing_key:
            return self.jwt_signing_key
        digest = hashlib.sha256(
            f"omnigent-public-jwt:{self.public_url}:{self.google_client_secret}".encode("utf-8")
        ).hexdigest()
        return digest


def _validate_public_https_url(raw: str) -> str:
    val = raw.strip().rstrip("/")
    parsed = urlsplit(val)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"OMNIGENT_PUBLIC_MCP_URL must be a bare https:// origin URL, got {raw!r}"
        )
    return f"https://{parsed.netloc.lower()}"


def _is_loopback_ip(raw_ip: str) -> bool:
    try:
        return ipaddress.ip_address(raw_ip.strip()).is_loopback
    except ValueError:
        return False


def load_public_omnigent_config(env: dict[str, str] | None = None) -> PublicOmnigentConfig:
    """Load and fail-closed validate public Google OAuth Omnigent MCP settings."""
    src = os.environ if env is None else env

    client_id = (src.get("OMNIGENT_PUBLIC_GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (src.get("OMNIGENT_PUBLIC_GOOGLE_CLIENT_SECRET") or "").strip()
    raw_url = (src.get("OMNIGENT_PUBLIC_MCP_URL") or DEFAULT_PUBLIC_URL).strip()
    raw_emails = (src.get("OMNIGENT_PUBLIC_ALLOWED_EMAILS") or "").strip()

    missing = [
        name
        for name, val in (
            ("OMNIGENT_PUBLIC_GOOGLE_CLIENT_ID", client_id),
            ("OMNIGENT_PUBLIC_GOOGLE_CLIENT_SECRET", client_secret),
            ("OMNIGENT_PUBLIC_ALLOWED_EMAILS", raw_emails),
        )
        if not val
    ]
    if missing:
        raise ValueError(f"Missing required public Omnigent config: {', '.join(missing)}")

    public_url = _validate_public_https_url(raw_url)
    emails = frozenset(
        part.strip().lower() for part in raw_emails.split(",") if part.strip()
    )
    if not emails or not all(_EMAIL_RE.match(e) for e in emails):
        raise ValueError("OMNIGENT_PUBLIC_ALLOWED_EMAILS must contain valid email addresses")

    host = (src.get("OMNIGENT_PUBLIC_HOST") or DEFAULT_BIND_HOST).strip() or DEFAULT_BIND_HOST
    if not _is_loopback_ip(host) and host.lower() != "localhost":
        raise ValueError(f"OMNIGENT_PUBLIC_HOST must stay loopback, got {host!r}")

    port = int(src.get("OMNIGENT_PUBLIC_PORT") or DEFAULT_PORT)
    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid OMNIGENT_PUBLIC_PORT: {port}")

    off_raw = (src.get("OMNIGENT_PUBLIC_OFF_FILE") or "").strip()
    log_raw = (src.get("OMNIGENT_PUBLIC_REFUSAL_LOG") or "").strip()
    off_file = Path(off_raw).expanduser() if off_raw else DEFAULT_OFF_FILE
    refusal_log = Path(log_raw).expanduser() if log_raw else DEFAULT_REFUSAL_LOG

    return PublicOmnigentConfig(
        google_client_id=client_id,
        google_client_secret=client_secret,
        public_url=public_url,
        allowed_emails=emails,
        host=host,
        port=port,
        jwt_signing_key=(src.get("OMNIGENT_PUBLIC_JWT_SIGNING_KEY") or "").strip() or None,
        off_file=off_file,
        refusal_log=refusal_log,
    )


def _is_google_host(hostname: str) -> bool:
    host = hostname.lower()
    return (
        host == "google.com"
        or host.endswith(".google.com")
        or host == "googleusercontent.com"
        or host.endswith(".googleusercontent.com")
    )


def is_allowed_redirect_uri(uri: Any) -> bool:
    """Allow only Claude, ChatGPT, Google/Antigravity web, and RFC 8252 loopback callbacks."""
    raw = str(uri or "").strip()
    if not raw:
        return False
    parsed = urlsplit(raw)
    if parsed.username or parsed.password or parsed.fragment:
        return False

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if scheme == "http":
        return host in {"127.0.0.1", "localhost", "::1"} and parsed.port is not None

    if scheme != "https":
        return False

    bare = f"https://{host}{parsed.path}"
    if bare in CLAUDE_CALLBACK_URIS:
        return True
    if bare in CHATGPT_EXACT_CALLBACK_URIS:
        return True
    if host == "chat.openai.com" and parsed.path.startswith("/aip/"):
        return True
    return _is_google_host(host)


def _is_allowed_origin(origin: str, public_host: str) -> bool:
    parsed = urlsplit(origin.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if scheme == "http":
        return host in {"127.0.0.1", "localhost", "::1"}
    if scheme != "https":
        return False
    if host == public_host:
        return True
    if f"https://{host}" in ALLOWED_CLIENT_ORIGINS:
        return True
    return _is_google_host(host)


def _email_allowed(token: AccessToken | None, allowed_emails: frozenset[str]) -> tuple[bool, str]:
    if token is None:
        return False, "invalid_or_missing_token"
    claims = token.claims if isinstance(token.claims, dict) else {}
    email = str(claims.get("email") or "").strip().lower()
    verified_raw = claims.get("email_verified")
    is_verified = verified_raw is True or str(verified_raw).lower() == "true"
    if not email or not is_verified:
        return False, "email_unverified"
    if email not in allowed_emails:
        return False, "disallowed_email"
    return True, email


class RefusalLogger:
    """Thread-safe sanitized JSONL logger for blocked/refused public requests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(
        self,
        *,
        reason: str,
        status: int,
        ip: str,
        method: str,
        path: str,
        detail: str = "",
    ) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "reason": reason,
            "status": status,
            "ip": ip,
            "method": method,
            "path": path,
            "detail": detail[:200],
        }
        line = json.dumps(entry, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            os.chmod(self.path, 0o600)


class _OwnerTokenVerifierProxy:
    """Wrap FastMCP's GoogleTokenVerifier to enforce verified owner email allowlisting."""

    def __init__(
        self,
        inner: Any,
        allowed_emails: frozenset[str],
        refusals: RefusalLogger,
    ) -> None:
        self._inner = inner
        self._allowed_emails = allowed_emails
        self._refusals = refusals

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await self._inner.verify_token(token)
        if verified is None:
            return None
        ok, reason_or_email = _email_allowed(verified, self._allowed_emails)
        if not ok:
            LOG.warning("Public Omnigent OAuth rejected upstream account", reason=reason_or_email)
            self._refusals.record(
                reason=reason_or_email,
                status=403,
                ip="oauth_upstream",
                method="VERIFY",
                path="/mcp",
                detail="Google account is not verified/allowlisted",
            )
            return None
        return verified


class OmnigentGoogleProvider(GoogleProvider):
    """Google OAuth 2.1 proxy locked to approved redirect URIs and owner emails."""

    def __init__(
        self,
        *,
        allowed_emails: frozenset[str],
        refusal_logger: RefusalLogger,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("required_scopes", GOOGLE_SCOPES)
        kwargs.setdefault("require_authorization_consent", False)
        super().__init__(**kwargs)
        self._allowed_emails = allowed_emails
        self._refusals = refusal_logger
        self._token_validator = _OwnerTokenVerifierProxy(
            self._token_validator,
            allowed_emails=allowed_emails,
            refusals=refusal_logger,
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = list(client_info.redirect_uris or [])
        if not uris or not all(is_allowed_redirect_uri(u) for u in uris):
            bad = [str(u)[:120] for u in uris]
            self._refusals.record(
                reason="invalid_redirect_uri",
                status=400,
                ip="dcr",
                method="POST",
                path="/register",
                detail=f"redirect_uris={bad}",
            )
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Redirect URI is not in the Omnigent connector allowlist.",
            )
        await super().register_client(client_info)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = await super().get_client(client_id)
        if client is None:
            return None
        uris = list(client.redirect_uris or [])
        if not uris or not all(is_allowed_redirect_uri(u) for u in uris):
            return None
        return client

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = await super().load_access_token(token)
        if access is None:
            return None
        ok, reason_or_email = _email_allowed(access, self._allowed_emails)
        if not ok:
            self._refusals.record(
                reason=reason_or_email,
                status=403,
                ip="token_verify",
                method="TOKEN",
                path="/mcp",
                detail="AccessToken failed owner email allowlist check",
            )
            return None
        return access


class PublicOmnigentGuardMiddleware:
    """ASGI security wrapper: kill switch, loopback /healthz, Host/Origin check, rate limits."""

    def __init__(
        self,
        app: ASGIApp,
        config: PublicOmnigentConfig,
        refusals: RefusalLogger,
    ) -> None:
        self.app = app
        self.config = config
        self.refusals = refusals
        self._lock = threading.Lock()
        self._rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._refusal_windows: dict[str, deque[float]] = defaultdict(deque)
        self._lockouts: dict[str, float] = {}

    async def _send_json(self, send: Send, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(raw)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": raw})

    async def _send_empty(self, send: Send, status: int) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-length", b"0"), (b"cache-control", b"no-store")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    def _note_refusal_ip(self, ip: str, *, count_lockout: bool) -> None:
        if not count_lockout or _is_loopback_ip(ip):
            return
        now = time.monotonic()
        with self._lock:
            q = self._refusal_windows[ip]
            cutoff = now - self.config.lockout_window_s
            while q and q[0] < cutoff:
                q.popleft()
            q.append(now)
            if len(q) >= self.config.lockout_after:
                self._lockouts[ip] = now + self.config.lockout_s

    def _check_rate_or_lockout(self, ip: str, bucket: str, limit: int) -> str | None:
        now = time.monotonic()
        with self._lock:
            locked_until = self._lockouts.get(ip)
            if locked_until is not None:
                if now < locked_until:
                    return "locked_out"
                self._lockouts.pop(ip, None)
            q = self._rate_windows[(ip, bucket)]
            cutoff = now - 60.0
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return "rate_limited"
            q.append(now)
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "/")
        method = str(scope.get("method") or "GET").upper()
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        client_info = scope.get("client")
        peer_ip = str(client_info[0]) if client_info else ""
        cf_ip = headers.get("cf-connecting-ip", "").strip()
        caller_ip = cf_ip or peer_ip or "unknown"

        if self.config.off_file.exists():
            self.refusals.record(
                reason="kill_switch",
                status=503,
                ip=caller_ip,
                method=method,
                path=path,
                detail="OFF file present",
            )
            await self._send_json(send, 503, {"error": "service_disabled"})
            return

        if method in {"GET", "HEAD"} and path in QUIET_404_PATHS:
            await self._send_empty(send, 404)
            return

        if path == "/healthz":
            if cf_ip or not _is_loopback_ip(peer_ip):
                self.refusals.record(
                    reason="healthz_public_blocked",
                    status=403,
                    ip=caller_ip,
                    method=method,
                    path=path,
                )
                await self._send_json(send, 403, {"error": "forbidden"})
                return
            await self._send_json(
                send,
                200,
                {
                    "status": "ok",
                    "service": "omnigent-public-mcp",
                    "publicUrl": self.config.public_url,
                },
            )
            return

        raw_host = headers.get("host", "").strip().lower()
        host_only = raw_host.split(":", 1)[0]
        if host_only.startswith("[") and "]" in raw_host:
            host_only = raw_host[1 : raw_host.index("]")]
        direct_loopback = (not cf_ip) and _is_loopback_ip(peer_ip) and host_only in {
            "127.0.0.1",
            "localhost",
            "::1",
            "testserver",
        }
        if host_only != self.config.public_host and not direct_loopback:
            self.refusals.record(
                reason="bad_host",
                status=403,
                ip=caller_ip,
                method=method,
                path=path,
                detail=f"host={raw_host[:80]}",
            )
            self._note_refusal_ip(caller_ip, count_lockout=True)
            await self._send_json(send, 403, {"error": "forbidden_host"})
            return

        origin = headers.get("origin", "").strip()
        if origin and method not in {"GET", "HEAD"} and not _is_allowed_origin(origin, self.config.public_host):
            self.refusals.record(
                reason="bad_origin",
                status=403,
                ip=caller_ip,
                method=method,
                path=path,
                detail=f"origin={origin[:80]}",
            )
            self._note_refusal_ip(caller_ip, count_lockout=True)
            await self._send_json(send, 403, {"error": "forbidden_origin"})
            return

        is_auth_path = path.startswith(AUTH_RATE_LIMIT_PREFIXES) or path.startswith("/.well-known/")
        bucket = "auth" if is_auth_path else "mcp"
        limit = self.config.auth_per_ip_per_min if is_auth_path else self.config.mcp_per_ip_per_min
        limit_err = self._check_rate_or_lockout(caller_ip, bucket, limit)
        if limit_err is not None:
            self.refusals.record(
                reason=limit_err,
                status=429,
                ip=caller_ip,
                method=method,
                path=path,
            )
            await self._send_json(send, 429, {"error": limit_err})
            return

        observed_status = 200

        async def _tracking_send(message: dict[str, Any]) -> None:
            nonlocal observed_status
            if message["type"] == "http.response.start":
                observed_status = int(message["status"])
            await send(message)

        await self.app(scope, receive, _tracking_send)

        if observed_status in {401, 403, 429}:
            is_discovery_401 = observed_status == 401 and path.startswith("/mcp")
            if not is_discovery_401:
                self.refusals.record(
                    reason=f"http_{observed_status}",
                    status=observed_status,
                    ip=caller_ip,
                    method=method,
                    path=path,
                )
            self._note_refusal_ip(caller_ip, count_lockout=(observed_status in {403, 429}))


def build_public_omnigent_app(
    settings: MCPStackSettings,
    config: PublicOmnigentConfig,
    *,
    http_client: httpx.AsyncClient | None = None,
    client_storage: Any | None = None,
) -> ASGIApp:
    """Build the hardened Google OAuth 2.1 Omnigent MCP ASGI application."""
    effective_settings = settings.model_copy(
        update={
            "omnigent": settings.omnigent.model_copy(update={"allow_mutations": True}),
        }
    )
    refusals = RefusalLogger(config.refusal_log)
    provider = OmnigentGoogleProvider(
        allowed_emails=config.allowed_emails,
        refusal_logger=refusals,
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        base_url=config.public_url,
        redirect_path="/auth/callback",
        jwt_signing_key=config.effective_jwt_signing_key,
        client_storage=client_storage,
    )
    mcp = create_omnigent_server(effective_settings, http_client=http_client, auth=provider)
    inner_app = mcp.http_app(path="/mcp", stateless_http=True)
    return PublicOmnigentGuardMiddleware(inner_app, config, refusals)
