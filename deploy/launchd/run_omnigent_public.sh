#!/bin/bash
set -euo pipefail
cd /Users/spencer/repos/mcp-server

ENV_FILE="$HOME/.config/mcp-stack/omnigent-public.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "omnigent-public-mcp: waiting for $ENV_FILE (run 'mcp-stack omnigent-public configure')."
  exit 0
fi

set -a
source "$ENV_FILE"
set +a

export OMNIGENT_BASE_URL=http://127.0.0.1:6767
export OMNIGENT_PUBLIC_URL=https://omnigent.slcc2c.com
export OMNIGENT_ALLOW_MUTATIONS=true
export MLFLOW_TRACKING_URI=http://localhost:5002
export MLFLOW_TRACING_ENABLED=true
export MLFLOW_DISABLE_AGENT_HINT=1

exec /Users/spencer/repos/mcp-server/.venv/bin/mcp-stack serve omnigent-public --host 127.0.0.1 --port 8768
