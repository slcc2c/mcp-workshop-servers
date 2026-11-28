#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

export UC_BASE_URL="${UC_BASE_URL:-http://100.85.39.109:8082}"
export MLFLOW_DISABLE_AGENT_HINT=1

exec /Users/spencer/repos/mcp-server/.venv/bin/mcp-stack service watchdog-once
