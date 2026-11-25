#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

export MLFLOW_DISABLE_AGENT_HINT=1

exec /Users/spencer/repos/mcp-server/.venv/bin/mcp-stack service watchdog-once
