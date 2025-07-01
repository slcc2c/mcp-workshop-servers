#!/bin/bash

# Update MCP servers to use the new runner scripts

echo "🔧 Updating MCP servers to use runner scripts..."

# Remove old servers
echo "Removing old server configurations..."
claude mcp remove docker -s user 2>/dev/null
claude mcp remove memory -s user 2>/dev/null
claude mcp remove jupyter -s user 2>/dev/null
claude mcp remove kubernetes -s user 2>/dev/null

# Add servers with runner scripts
echo "Adding Docker server with runner..."
claude mcp add-json docker -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/docker.js"],
  "env": {
    "DOCKER_HOST": "unix:///var/run/docker.sock"
  }
}'

echo "Adding Memory server with runner..."
claude mcp add-json memory -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/memory.js"],
  "env": {
    "MEMORY_PROJECT": "claude-mcp-session",
    "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
  }
}'

echo "Adding Jupyter server with runner..."
claude mcp add-json jupyter -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/jupyter.js"],
  "env": {
    "JUPYTER_BASE_URL": "http://localhost:8888"
  }
}'

echo "Adding Kubernetes server with runner..."
claude mcp add-json kubernetes -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/kubernetes.js"],
  "env": {
    "KUBECONFIG": "/Users/spencer/.kube/config"
  }
}'

echo ""
echo "✅ MCP servers updated to use runner scripts!"
echo ""
echo "Current servers:"
claude mcp list