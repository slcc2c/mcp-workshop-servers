"""Authentication, UI shell, and session routes for the Gateway."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from mcp_stack import __version__
from mcp_stack.core.auth import (
    UI_SESSION_COOKIE,
    caller_auth_method_var,
    caller_client_id_var,
    find_client_by_id,
    resolve_owner_ui_client,
    resolve_trusted_ui_method,
    sign_ui_session,
    verify_ui_session,
)
from mcp_stack.core.config import ClientPolicy
from mcp_stack.gateway.dashboard import render_dashboard_html
from mcp_stack.gateway.state import GatewayRuntimeState


def set_session_cookie(
    state: GatewayRuntimeState,
    response: Response,
    cookie_token: str,
    request: Request,
) -> None:
    fwd_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    is_https = request.url.scheme == "https" or fwd_proto == "https"
    response.set_cookie(
        key=UI_SESSION_COOKIE,
        value=cookie_token,
        max_age=state.settings.gateway.ui_session_ttl_s,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_https,
    )


def resolve_auth_identity(
    state: GatewayRuntimeState,
    request: Request,
) -> tuple[ClientPolicy | None, str]:
    settings = state.settings
    if not settings.gateway.effective_auth_enabled:
        return None, "open"
    auth_header = request.headers.get("authorization", "")
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if bearer:
        return settings.gateway.clients.get(bearer), "bearer"
    cookie_val = request.cookies.get(UI_SESSION_COOKIE)
    cid = verify_ui_session(cookie_val, settings)
    if cid:
        return find_client_by_id(settings, cid), "cookie"
    return None, "anonymous"


def maybe_mint_trusted_ui_session(
    state: GatewayRuntimeState,
    request: Request,
    response: Response,
) -> tuple[ClientPolicy | None, str | None]:
    settings = state.settings
    if not settings.gateway.effective_auth_enabled:
        return None, None
    client_host = request.client.host if request.client else ""
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    trusted_method = resolve_trusted_ui_method(client_host, headers_lower, settings)
    if trusted_method is None:
        return None, None
    owner_cid, owner_policy = resolve_owner_ui_client(settings)
    existing_cid = verify_ui_session(request.cookies.get(UI_SESSION_COOKIE), settings)
    if not existing_cid:
        session_val = sign_ui_session(owner_cid, settings)
        set_session_cookie(state, response, session_val, request)
    return owner_policy, trusted_method


def build_auth_router(state: GatewayRuntimeState) -> APIRouter:
    router = APIRouter()
    settings = state.settings

    @router.get("/favicon.ico")
    async def favicon() -> Response:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<rect width="32" height="32" rx="7" fill="#0f172a"/>'
            '<path d="M8 10h6v6H8zm10 0h6v6h-6zM8 20h6v6H8zm10 0h6v6h-6z" fill="#38bdf8"/>'
            "</svg>"
        )
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @router.get("/ui", response_class=HTMLResponse)
    async def dashboard_ui(request: Request) -> HTMLResponse:
        resp = HTMLResponse(
            content=render_dashboard_html(__version__),
            headers={"Cache-Control": "no-store"},
        )
        maybe_mint_trusted_ui_session(state, request, resp)
        return resp

    @router.post("/api/v1/auth/login-link", response_model=None)
    async def ui_login_link_api(request: Request) -> dict[str, Any] | JSONResponse:
        if settings.gateway.effective_auth_enabled and caller_auth_method_var.get() != "bearer":
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "BEARER_REQUIRED",
                        "message": "Minting a /ui login link requires Authorization: Bearer auth",
                    }
                },
            )
        client_id = caller_client_id_var.get() or "codex"
        if client_id == "anonymous":
            first = next(iter(settings.gateway.clients.values()), None)
            client_id = first.client_id if first is not None else "local"
        nonce = state.login_nonces.issue(client_id)
        origin = (
            (settings.gateway.public_url or "").rstrip("/")
            or str(request.base_url).rstrip("/")
        )
        return {
            "url": f"{origin}/ui/login?nonce={nonce}",
            "expiresInSeconds": 60,
            "clientId": client_id,
        }

    @router.get("/ui/login")
    async def ui_login_consume(request: Request, nonce: str = "") -> RedirectResponse:
        client_id = state.login_nonces.consume(nonce)
        if not client_id:
            return RedirectResponse(url="/ui?auth_error=invalid_link", status_code=303)
        session_val = sign_ui_session(client_id, settings)
        resp = RedirectResponse(url="/ui", status_code=303)
        set_session_cookie(state, resp, session_val, request)
        return resp

    @router.post("/api/v1/auth/session", response_model=None)
    async def ui_session_create(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Response:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        if not token and isinstance(payload, dict):
            token = str(payload.get("token") or "").strip()

        if not settings.gateway.effective_auth_enabled:
            session_val = sign_ui_session("local", settings)
            resp = JSONResponse(
                {
                    "authenticated": True,
                    "authEnabled": False,
                    "clientId": "local",
                    "clientName": "Local (Auth Disabled)",
                    "allowedServers": ["*"],
                    "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
                }
            )
            set_session_cookie(state, resp, session_val, request)
            return resp

        policy = settings.gateway.clients.get(token) if token else None
        if policy is None:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "AUTH_FAILED", "message": "Invalid Bearer token"}},
            )
        session_val = sign_ui_session(policy.client_id, settings)
        resp = JSONResponse(
            {
                "authenticated": True,
                "authEnabled": True,
                "clientId": policy.client_id,
                "clientName": policy.client_name,
                "allowedServers": list(policy.allowed_servers),
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
            }
        )
        set_session_cookie(state, resp, session_val, request)
        return resp

    @router.get("/api/v1/auth/me", response_model=None)
    async def ui_session_me(request: Request) -> Response | dict[str, Any]:
        policy, method = resolve_auth_identity(state, request)
        if not settings.gateway.effective_auth_enabled:
            return {
                "authenticated": True,
                "authEnabled": False,
                "clientId": "local",
                "clientName": "Local (Auth Disabled)",
                "allowedServers": ["*"],
                "authMethod": "open",
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
                "adminToolsEnabled": settings.gateway.admin_tools_enabled,
            }
        if policy is None:
            client_host = request.client.host if request.client else ""
            headers_lower = {k.lower(): v for k, v in request.headers.items()}
            trusted_method = resolve_trusted_ui_method(client_host, headers_lower, settings)
            if trusted_method is not None:
                _owner_cid, owner_policy = resolve_owner_ui_client(settings)
                if owner_policy is not None:
                    resp = JSONResponse(
                        {
                            "authenticated": True,
                            "authEnabled": True,
                            "clientId": owner_policy.client_id,
                            "clientName": owner_policy.client_name,
                            "allowedServers": list(owner_policy.allowed_servers),
                            "authMethod": trusted_method,
                            "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
                            "adminToolsEnabled": settings.gateway.admin_tools_enabled,
                        }
                    )
                    maybe_mint_trusted_ui_session(state, request, resp)
                    return resp
            return {
                "authenticated": False,
                "authEnabled": True,
                "clientId": None,
                "clientName": None,
                "allowedServers": [],
                "authMethod": "anonymous",
                "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
                "adminToolsEnabled": settings.gateway.admin_tools_enabled,
            }
        return {
            "authenticated": True,
            "authEnabled": True,
            "clientId": policy.client_id,
            "clientName": policy.client_name,
            "allowedServers": list(policy.allowed_servers),
            "authMethod": method,
            "mlflowMutationsEnabled": settings.mlflow.allow_mutations,
            "adminToolsEnabled": settings.gateway.admin_tools_enabled,
        }

    @router.post("/api/v1/auth/logout")
    async def ui_session_logout() -> Response:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(key=UI_SESSION_COOKIE, path="/")
        return resp

    return router
