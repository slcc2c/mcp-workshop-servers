"""Stdio-to-Streamable-HTTP bridge for local MCP GUI clients."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy

DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8090"
DEFAULT_PROFILE = "core"


def default_env_file() -> Path:
    """Return the default repository .env path independent of working directory."""
    return Path(__file__).resolve().parents[2] / ".env"


def parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a dotenv file without executing shell code."""
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        val = raw_val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def load_gateway_token(
    *,
    token_env_var: str,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the Bearer token for token_env_var from environ or .env, failing closed."""
    env_map = os.environ if environ is None else environ
    direct = str(env_map.get(token_env_var, "")).strip()
    if direct:
        return direct

    resolved_env_file = (env_file if env_file is not None else default_env_file()).expanduser()
    parsed = parse_env_file(resolved_env_file)
    from_file = parsed.get(token_env_var, "").strip()
    if from_file:
        return from_file

    raise RuntimeError(
        f"No gateway Bearer token found for {token_env_var} in environment or {resolved_env_file}"
    )


def build_target_url(
    *,
    base_url: str = DEFAULT_GATEWAY_BASE_URL,
    profile: str | None = None,
    server: str | None = None,
    explicit_url: str | None = None,
) -> str:
    """Construct the Streamable HTTP endpoint URL for a gateway profile or server."""
    if explicit_url and explicit_url.strip():
        return explicit_url.strip()

    clean_profile = profile.strip().strip("/") if profile is not None else ""
    clean_server = server.strip().strip("/") if server is not None else ""
    if clean_profile and clean_server:
        raise ValueError("Specify only one of --profile or --server")

    clean_base = base_url.rstrip("/")
    if clean_server:
        slug = clean_server.replace("_", "-").lower()
        return f"{clean_base}/servers/{slug}/mcp"

    selected_profile = clean_profile or DEFAULT_PROFILE
    if selected_profile == "full":
        return f"{clean_base}/mcp"
    return f"{clean_base}/profiles/{selected_profile}/mcp"


def run_stdio_bridge(
    *,
    profile: str | None = None,
    server: str | None = None,
    base_url: str = DEFAULT_GATEWAY_BASE_URL,
    explicit_url: str | None = None,
    token_env_var: str = "MCP_CLAUDE_AUTH_TOKEN",
    env_file: Path | None = None,
    allow_unauthenticated: bool = False,
) -> None:
    """Run a FastMCP stdio proxy targeting an authenticated Streamable HTTP gateway route."""
    target_url = build_target_url(
        base_url=base_url,
        profile=profile,
        server=server,
        explicit_url=explicit_url,
    )

    headers: dict[str, str] = {}
    try:
        token = load_gateway_token(token_env_var=token_env_var, env_file=env_file)
    except RuntimeError:
        if not allow_unauthenticated:
            raise
    else:
        headers["Authorization"] = f"Bearer {token}"

    transport = StreamableHttpTransport(
        url=target_url,
        headers=headers or None,
    )
    target_label = (server or profile or DEFAULT_PROFILE).strip().replace("_", "-").lower()
    proxy_name = f"mcp-workshop-gateway-{target_label}"
    proxy = create_proxy(transport, name=proxy_name)
    proxy.run(transport="stdio", show_banner=False)
