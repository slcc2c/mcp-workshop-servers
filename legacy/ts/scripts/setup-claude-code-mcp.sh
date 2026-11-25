#!/bin/bash

# Setup MCP servers for Claude Code with environment variables

echo "🔧 Setting up MCP servers for Claude Code..."

# Remove existing servers first (optional, comment out if you want to keep existing)
# claude mcp remove github
# claude mcp remove memory
# claude mcp remove docker
# claude mcp remove jupyter
# claude mcp remove kubernetes

# GitHub server with token
echo "Adding GitHub server..."
GITHUB_PERSONAL_ACCESS_TOKEN="${GITHUB_TOKEN:-}" \
claude mcp add github -s user npx -- -y @modelcontextprotocol/server-github

# Memory server with environment variables
echo "Adding Memory server..."
MEMORY_PROJECT="claude-mcp-session" \
MEMORY_STORAGE_PATH="/Users/spencer/.mcp/memory" \
claude mcp add memory -s user node /Users/spencer/repos/mcp-server/dist/servers/memory/index.js

# Docker server with Docker host
echo "Adding Docker server..."
DOCKER_HOST="unix:///var/run/docker.sock" \
claude mcp add docker -s user node /Users/spencer/repos/mcp-server/dist/servers/docker/index.js

# Jupyter server with base URL
echo "Adding Jupyter server..."
JUPYTER_BASE_URL="http://localhost:8888" \
claude mcp add jupyter -s user node /Users/spencer/repos/mcp-server/dist/servers/jupyter/index.js

# Kubernetes server with kubeconfig
echo "Adding Kubernetes server..."
KUBECONFIG="/Users/spencer/.kube/config" \
claude mcp add kubernetes -s user node /Users/spencer/repos/mcp-server/dist/servers/kubernetes/index.js

echo "✅ MCP servers configured for Claude Code!"
echo ""
echo "Current servers:"
claude mcp list