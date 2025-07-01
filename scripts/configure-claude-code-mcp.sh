#!/bin/bash

# Configure MCP servers for Claude Code with proper environment variables

echo "🔧 Configuring MCP servers for Claude Code with environment variables..."

# Remove existing servers to reconfigure with env vars
echo "Removing existing servers..."
claude mcp remove github -s user 2>/dev/null
claude mcp remove memory -s user 2>/dev/null
claude mcp remove docker -s user 2>/dev/null
claude mcp remove jupyter -s user 2>/dev/null
claude mcp remove kubernetes -s user 2>/dev/null

# GitHub server
echo "Adding GitHub server..."
claude mcp add-json github -s user '{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN_REMOVED"
  }
}'

# Filesystem server (no env needed)
echo "Adding Filesystem server..."
claude mcp add filesystem -s user npx -- -y @modelcontextprotocol/server-filesystem /Users/spencer/repos

# Memory server
echo "Adding Memory server..."
claude mcp add-json memory -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/memory-server.js"],
  "env": {
    "MEMORY_PROJECT": "claude-mcp-session",
    "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
  }
}'

# Docker server
echo "Adding Docker server..."
claude mcp add-json docker -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/docker-server.js"],
  "env": {
    "DOCKER_HOST": "unix:///var/run/docker.sock"
  }
}'

# Jupyter server
echo "Adding Jupyter server..."
claude mcp add-json jupyter -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/jupyter-server.js"],
  "env": {
    "JUPYTER_BASE_URL": "http://localhost:8888"
  }
}'

# Kubernetes server
echo "Adding Kubernetes server..."
claude mcp add-json kubernetes -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/kubernetes-server.js"],
  "env": {
    "KUBECONFIG": "/Users/spencer/.kube/config"
  }
}'

echo ""
echo "✅ MCP servers configured with environment variables!"
echo ""
echo "Current servers:"
claude mcp list