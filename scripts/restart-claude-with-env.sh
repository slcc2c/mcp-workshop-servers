#!/bin/bash

# Script to restart Claude Desktop with proper environment variables
# This ensures MCP servers have access to required environment variables

echo "🔄 Restarting Claude Desktop with MCP environment variables..."

# Kill any existing Claude Desktop instances
echo "📌 Stopping Claude Desktop..."
pkill -x "Claude" 2>/dev/null || true
sleep 2

# Source environment variables if .env file exists
if [ -f "/Users/spencer/repos/Server-Configs/.env" ]; then
    echo "📋 Loading environment variables from Server-Configs/.env..."
    export $(grep -v '^#' /Users/spencer/repos/Server-Configs/.env | xargs)
fi

# Additional environment variables that might be needed
export MEMORY_PROJECT="${MEMORY_PROJECT:-claude-mcp-session}"
export MEMORY_STORAGE_PATH="${MEMORY_STORAGE_PATH:-/Users/spencer/.mcp/memory}"
export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
export JUPYTER_BASE_URL="${JUPYTER_BASE_URL:-http://localhost:8888}"
export KUBECONFIG="${KUBECONFIG:-/Users/spencer/.kube/config}"

# Create necessary directories
mkdir -p "$MEMORY_STORAGE_PATH" 2>/dev/null

# Start Claude Desktop with environment variables
echo "🚀 Starting Claude Desktop..."
open -a "Claude"

echo "✅ Claude Desktop restarted with MCP environment variables"
echo ""
echo "📝 Test your MCP servers with these commands:"
echo "  - GitHub: Use 'search_repositories' with query 'mcp servers'"
echo "  - Memory: Use 'memory_store' to save a test memory"
echo "  - Docker: Use 'docker_list_containers' to list containers"
echo "  - Jupyter: Use 'jupyter_list_notebooks' to list notebooks"
echo "  - Kubernetes: Use 'kubernetes_list_pods' to list pods"