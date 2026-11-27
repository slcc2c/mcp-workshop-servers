"""Unit tests for the hardened public Google OAuth 2.1 Omnigent MCP connector."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from fastmcp.server.auth.providers.google import GoogleTokenVerifier
from key_value.aio.stores.memory import MemoryStore
from mcp.server.auth.provider import AccessToken, RegistrationError
from mcp.shared.auth import OAuthClientInformationFull

from mcp_stack.core.config import OmnigentSettings
from mcp_stack.gateway.public_omnigent import (
    OmnigentGoogleProvider,
    PublicOmnigentConfig,
    RefusalLogger,
    build_public_omnigent_app,
    is_allowed_redirect_uri,
    load_public_omnigent_config,
)

pytestmark = pytest.mark.unit


def _sample_config(tmp_path: Path) -> PublicOmnigentConfig:
    return PublicOmnigentConfig(
        google_client_id="123456.apps.googleusercontent.com",
        google_client_secret="dummy-client-secret-value",
        public_url="https://omnigent-mcp.slcc2c.com",
        allowed_emails=frozenset({"owner@example.com"}),
        off_file=tmp_path / "OFF",
        refusal_log=tmp_path / "refusals.jsonl",
    )


def test_load_public_omnigent_config_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Missing required public Omnigent config"):
        load_public_omnigent_config({})

    with pytest.raises(ValueError, match="bare https:// origin URL"):
        load_public_omnigent_config(
            {
                "OMNIGENT_PUBLIC_GOOGLE_CLIENT_ID": "cid",
                "OMNIGENT_PUBLIC_GOOGLE_CLIENT_SECRET": "csec",
                "OMNIGENT_PUBLIC_ALLOWED_EMAILS": "owner@example.com",
                "OMNIGENT_PUBLIC_MCP_URL": "http://omnigent-mcp.slcc2c.com",
            }
        )

    cfg = load_public_omnigent_config(
        {
            "OMNIGENT_PUBLIC_GOOGLE_CLIENT_ID": "cid",
            "OMNIGENT_PUBLIC_GOOGLE_CLIENT_SECRET": "csec",
            "OMNIGENT_PUBLIC_ALLOWED_EMAILS": "Owner@Example.com",
            "OMNIGENT_PUBLIC_MCP_URL": "https://omnigent-mcp.slcc2c.com/",
            "OMNIGENT_PUBLIC_OFF_FILE": str(tmp_path / "OFF"),
            "OMNIGENT_PUBLIC_REFUSAL_LOG": str(tmp_path / "refusals.jsonl"),
        }
    )
    assert cfg.public_url == "https://omnigent-mcp.slcc2c.com"
    assert cfg.allowed_emails == frozenset({"owner@example.com"})
    assert len(cfg.effective_jwt_signing_key) == 64


def test_redirect_uri_allowlist() -> None:
    assert is_allowed_redirect_uri("https://claude.ai/api/mcp/auth_callback")
    assert is_allowed_redirect_uri("https://claude.com/api/mcp/auth_callback")
    assert is_allowed_redirect_uri("https://chatgpt.com/connector_platform_oauth_redirect")
    assert is_allowed_redirect_uri("https://chatgpt.com/connector/oauth/MI-XEb-30pCy")
    assert is_allowed_redirect_uri("https://platform.openai.com/apps-manage/oauth")
    assert is_allowed_redirect_uri("https://chat.openai.com/aip/g-123/oauth/callback")
    assert is_allowed_redirect_uri("https://antigravity.google.com/oauth/callback")
    assert is_allowed_redirect_uri("http://127.0.0.1:54321/callback")
    assert is_allowed_redirect_uri("http://localhost:43123/auth/cb")

    assert not is_allowed_redirect_uri("https://evil.example/cb")
    assert not is_allowed_redirect_uri("http://evil.example:8080/cb")
    assert not is_allowed_redirect_uri("javascript:alert(1)")
    assert not is_allowed_redirect_uri("https://user@claude.ai/api/mcp/auth_callback")


async def test_provider_blocks_disallowed_redirects_and_emails(tmp_path: Path) -> None:
    refusals = RefusalLogger(tmp_path / "refusals.jsonl")
    provider = OmnigentGoogleProvider(
        allowed_emails=frozenset({"owner@example.com"}),
        refusal_logger=refusals,
        client_id="cid",
        client_secret="csec",
        base_url="https://omnigent-mcp.slcc2c.com",
        jwt_signing_key="test-signing-key",
        client_storage=MemoryStore(),
    )

    with pytest.raises(RegistrationError):
        await provider.register_client(
            OAuthClientInformationFull(
                client_id="evil-cli",
                redirect_uris=["https://evil.example/callback"],
            )
        )

    await provider.register_client(
        OAuthClientInformationFull(
            client_id="claude-cli",
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
        )
    )
    loaded = await provider.get_client("claude-cli")
    assert loaded is not None

    # Inject a forbidden client into storage directly and confirm get_client refuses it.
    await provider._client_store.put(
        key="rogue-cli",
        value=OAuthClientInformationFull(
            client_id="rogue-cli",
            redirect_uris=["https://rogue.example/cb"],
        ),
    )
    assert await provider.get_client("rogue-cli") is None

    # Simulate FastMCP CIMD clients (redirect_uris=None on ProxyDCRClient, URIs on cimd_document).
    from fastmcp.server.auth.cimd import CIMDDocument
    from fastmcp.server.auth.oauth_proxy.models import ProxyDCRClient

    claude_cimd = ProxyDCRClient(
        client_id="https://claude.ai/oauth/mcp-oauth-client-metadata",
        client_secret=None,
        redirect_uris=None,
        cimd_document=CIMDDocument(
            client_id="https://claude.ai/oauth/mcp-oauth-client-metadata",
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
        ),
    )
    chatgpt_cimd = ProxyDCRClient(
        client_id="https://chatgpt.com/oauth/MI-XEb-30pCy/client.json",
        client_secret=None,
        redirect_uris=None,
        cimd_document=CIMDDocument(
            client_id="https://chatgpt.com/oauth/MI-XEb-30pCy/client.json",
            redirect_uris=["https://chatgpt.com/connector/oauth/MI-XEb-30pCy"],
        ),
    )
    evil_cimd = ProxyDCRClient(
        client_id="https://evil.example/client.json",
        client_secret=None,
        redirect_uris=None,
        cimd_document=CIMDDocument(
            client_id="https://evil.example/client.json",
            redirect_uris=["https://evil.example/cb"],
        ),
    )

    class FakeCimdManager:
        def __init__(self, docs: dict[str, ProxyDCRClient]) -> None:
            self._docs = docs

        def is_cimd_client_id(self, cid: str) -> bool:
            return cid in self._docs

        async def get_client(self, cid: str) -> ProxyDCRClient | None:
            return self._docs.get(cid)

    provider._cimd_manager = FakeCimdManager(
        {
            claude_cimd.client_id: claude_cimd,
            chatgpt_cimd.client_id: chatgpt_cimd,
            evil_cimd.client_id: evil_cimd,
        }
    )
    assert await provider.get_client(claude_cimd.client_id) is not None
    assert await provider.get_client(chatgpt_cimd.client_id) is not None
    assert await provider.get_client(evil_cimd.client_id) is None

    # Verify owner email check inside wrapped verifier proxy.
    class FakeVerifier:
        def __init__(self, claims: dict[str, object]) -> None:
            self._claims = claims
            self.required_scopes = []

        async def verify_token(self, token: str) -> AccessToken | None:
            return AccessToken(
                token=token,
                client_id="sub-1",
                scopes=["openid"],
                expires_at=int(time.time()) + 3600,
                claims=self._claims,
            )

    provider._token_validator._inner = FakeVerifier(
        {"email": "stranger@example.com", "email_verified": True}
    )
    assert await provider._token_validator.verify_token("tok") is None

    provider._token_validator._inner = FakeVerifier(
        {"email": "owner@example.com", "email_verified": False}
    )
    assert await provider._token_validator.verify_token("tok") is None

    provider._token_validator._inner = FakeVerifier(
        {"email": "OWNER@example.com", "email_verified": "true"}
    )
    ok = await provider._token_validator.verify_token("tok")
    assert ok is not None

    # Ensure GoogleTokenVerifier import stays valid for FastMCP compatibility checks
    assert GoogleTokenVerifier is not None


async def test_public_omnigent_guard_and_oauth_discovery(make_settings, tmp_path: Path) -> None:
    settings = make_settings(
        omnigent=OmnigentSettings(
            base_url="http://omni.test",
            public_url="https://studio.ts.net:8446",
            allow_mutations=False,
        )
    )
    cfg = _sample_config(tmp_path)
    app = build_public_omnigent_app(settings, cfg, client_storage=MemoryStore())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 51234)),
        base_url="https://omnigent-mcp.slcc2c.com",
    ) as client:
        # 1. Quiet 404 on /
        r_root = await client.get("/")
        assert r_root.status_code == 404

        # 2. /healthz allowed on direct loopback, blocked when CF-Connecting-IP is present
        r_hz = await client.get("/healthz")
        assert r_hz.status_code == 200
        assert r_hz.json()["service"] == "omnigent-public-mcp"

        r_hz_cf = await client.get("/healthz", headers={"CF-Connecting-IP": "160.79.104.10"})
        assert r_hz_cf.status_code == 403

        # 3. Host header DNS-rebinding guard
        r_host = await client.get(
            "/.well-known/oauth-authorization-server", headers={"Host": "evil.example"}
        )
        assert r_host.status_code == 403

        # 4. OAuth metadata and 401 WWW-Authenticate on unauthenticated POST /mcp
        r_meta = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert r_meta.status_code == 200
        meta_json = r_meta.json()
        assert "https://omnigent-mcp.slcc2c.com" in json.dumps(meta_json)

        r_mcp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r_mcp.status_code == 401
        assert "resource_metadata" in r_mcp.headers.get("www-authenticate", "")

        # 5. Instant OFF kill switch toggles 503 without restart
        cfg.off_file.write_text("disabled\n", encoding="utf-8")
        r_off = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r_off.status_code == 503
        assert r_off.json()["error"] == "service_disabled"

        cfg.off_file.unlink()
        r_restored = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert r_restored.status_code == 401

    assert cfg.refusal_log.exists()
    refusal_lines = cfg.refusal_log.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["reason"] == "kill_switch" for line in refusal_lines)
