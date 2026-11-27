#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

# shellcheck source=/Users/spencer/repos/mcp-server/deploy/launchd/load_env_safe.sh
source /Users/spencer/repos/mcp-server/deploy/launchd/load_env_safe.sh
load_env_safe "$HOME/.config/mcp-stack/gateway.env"

export MCP_AUTH_ENABLED=true
export MCP_GATEWAY_PUBLIC_URL="https://mcp.slcc2c.com"
export GATEWAY_UI_SESSION_TTL_S=2592000
export MCP_UI_TRUST_TAILNET=true
export MCP_UI_TRUST_FORWARD_AUTH=true
export MCP_UI_ALLOWED_EMAILS="${MCP_UI_ALLOWED_EMAILS:-spork76@gmail.com,spencer@slcc2c.com}"
export MLFLOW_TRACKING_URI=http://localhost:5002
export MLFLOW_MCP_URL=http://127.0.0.1:9012/mcp
export UC_BASE_URL=http://localhost:8082
export UC_ALLOW_MUTATIONS=false
export MLFLOW_ALLOW_MUTATIONS=false
export UC_FUNCTION_ALLOWLIST="unity.default,workshop.default"
export UC_EXECUTION_MODE=sandbox
export EXECUTOR_MAX_MEMORY_LIMIT=4096
export UC_VOLUME_LOCAL_PREFIX_MAP="file:///home/unitycatalog/etc/data/external/workshop=/Users/spencer/repos/mcp-server/data/uc-volumes"
export MLFLOW_TRACING_ENABLED=true
export MLFLOW_DISABLE_AGENT_HINT=1

/Users/spencer/repos/mcp-server/.venv/bin/mcp-stack service rotate-logs --max-mb 10 >/dev/null 2>&1 || true

# Wait briefly for co-launched mlflow[mcp] LaunchAgent so /mcp composes upstream tools on boot.
/Users/spencer/repos/mcp-server/.venv/bin/python -c "
import asyncio, time
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint

async def wait():
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        res = await probe_mcp_http_endpoint('http://127.0.0.1:9012/mcp', timeout=1.5)
        if res.get('reachable'):
            return
        await asyncio.sleep(0.5)

asyncio.run(wait())
" || true

exec /Users/spencer/repos/mcp-server/.venv/bin/mcp-stack serve gateway --host 127.0.0.1 --port 8090
