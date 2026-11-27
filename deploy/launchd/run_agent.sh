#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

# shellcheck source=/Users/spencer/repos/mcp-server/deploy/launchd/load_env_safe.sh
source /Users/spencer/repos/mcp-server/deploy/launchd/load_env_safe.sh
load_env_safe "$HOME/.config/mcp-stack/gateway.env"

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:5002}"
export MLFLOW_TRACING_ENABLED="${MLFLOW_TRACING_ENABLED:-true}"
export MLFLOW_DISABLE_AGENT_HINT=1
export MCP_AGENT_URL="${MCP_AGENT_URL:-http://127.0.0.1:8092}"
export MCP_AGENT_LLM_BASE_URL="${MCP_AGENT_LLM_BASE_URL:-http://localhost:5002/gateway/mlflow/v1}"
export MCP_AGENT_LLM_MODEL="${MCP_AGENT_LLM_MODEL:-mcp-workshop-agent-v1}"
export MCP_AGENT_DEFAULT_PROFILE="${MCP_AGENT_DEFAULT_PROFILE:-core}"

# Wait briefly for the gateway /ready endpoint so MCP tool calls resolve on boot.
/Users/spencer/repos/mcp-server/.venv/bin/python -c "
import time, httpx
deadline = time.monotonic() + 15.0
while time.monotonic() < deadline:
    try:
        r = httpx.get('http://127.0.0.1:8090/ready', timeout=1.5)
        if r.status_code == 200:
            break
    except Exception:
        pass
    time.sleep(0.5)
" || true

exec /Users/spencer/repos/mcp-server/.venv/bin/mcp-stack serve agent \
  --host "${MCP_AGENT_HOST:-127.0.0.1}" \
  --port "${MCP_AGENT_PORT:-8092}"
