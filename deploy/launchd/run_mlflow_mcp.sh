#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:5002}"
export MLFLOW_DISABLE_AGENT_HINT=1

/Users/spencer/repos/mcp-server/.venv/bin/mcp-stack service rotate-logs --max-mb 10 >/dev/null 2>&1 || true

exec /Users/spencer/repos/mcp-server/.venv/bin/python -c \
  "from mlflow.mcp.server import create_mcp; create_mcp().run(transport='streamable-http', host='127.0.0.1', port=9012, show_banner=False)"
