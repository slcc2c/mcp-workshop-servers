#!/bin/bash

# Complete setup script for MCP servers in Claude Code
# This script fixes all known issues and configures servers properly

echo "🚀 MCP Server Setup for Claude Code"
echo "=================================="

# Step 1: Build the project
echo ""
echo "📦 Step 1: Building TypeScript project..."
npm run build

# Step 2: Fix ES module imports
echo ""
echo "🔧 Step 2: Fixing ES module imports..."
if [ -f scripts/fix-all-esm-imports.sh ]; then
  ./scripts/fix-all-esm-imports.sh
else
  echo "Import fix script not found, skipping..."
fi

# Step 3: Fix logger issues
echo ""
echo "📝 Step 3: Fixing logger configuration..."
if [ -f scripts/fix-logger-permanently.sh ]; then
  ./scripts/fix-logger-permanently.sh
else
  echo "Logger fix script not found, skipping..."
fi

# Step 4: Create server runners
echo ""
echo "🏃 Step 4: Creating server runners..."
if [ -f scripts/create-server-runners.sh ]; then
  ./scripts/create-server-runners.sh
else
  echo "Runner creation script not found, skipping..."
fi

# Step 5: Create necessary directories
echo ""
echo "📁 Step 5: Creating necessary directories..."
mkdir -p ~/.mcp/memory
mkdir -p logs

# Step 6: Configure MCP servers in Claude Code
echo ""
echo "⚙️  Step 6: Configuring MCP servers in Claude Code..."

# Function to add server with environment variables
add_mcp_server() {
  local name=$1
  local command=$2
  shift 2
  local args=("$@")
  
  echo "Adding $name server..."
  claude mcp remove "$name" -s user 2>/dev/null
  
  if [ ${#args[@]} -eq 0 ]; then
    claude mcp add "$name" -s user "$command"
  else
    claude mcp add "$name" -s user "$command" -- "${args[@]}"
  fi
}

# Add all servers
add_mcp_server "github" "npx" "-y" "@modelcontextprotocol/server-github"
add_mcp_server "filesystem" "npx" "-y" "@modelcontextprotocol/server-filesystem" "/Users/spencer/repos"
add_mcp_server "memory" "node" "/Users/spencer/repos/mcp-server/runners/memory-server.js"
add_mcp_server "docker" "node" "/Users/spencer/repos/mcp-server/runners/docker-server.js"
add_mcp_server "jupyter" "node" "/Users/spencer/repos/mcp-server/runners/jupyter-server.js"
add_mcp_server "kubernetes" "node" "/Users/spencer/repos/mcp-server/runners/kubernetes-server.js"
add_mcp_server "postgresql" "node" "/Users/spencer/repos/mcp-server/runners/postgresql-server.js"
add_mcp_server "redis" "node" "/Users/spencer/repos/mcp-server/runners/redis-server.js"
add_mcp_server "mongodb" "node" "/Users/spencer/repos/mcp-server/runners/mongodb-server.js"
add_mcp_server "neo4j" "node" "/Users/spencer/repos/mcp-server/runners/neo4j-server.js"

# Step 7: Set environment variables
echo ""
echo "🔐 Step 7: Setting environment variables..."
echo "Note: Environment variables should be set in your shell profile or .env file"
echo "Required variables:"
echo "  - GITHUB_PERSONAL_ACCESS_TOKEN"
echo "  - MEMORY_PROJECT=claude-mcp-session"
echo "  - MEMORY_STORAGE_PATH=~/.mcp/memory"
echo "  - DOCKER_HOST=unix:///var/run/docker.sock"
echo "  - JUPYTER_BASE_URL=http://localhost:8888"
echo "  - KUBECONFIG=~/.kube/config"
echo "  - Database connection strings for PostgreSQL, Redis, MongoDB, Neo4j"

# Step 8: Display configured servers
echo ""
echo "✅ Setup complete! Current MCP servers:"
echo "======================================"
claude mcp list

echo ""
echo "📝 Test your servers with these commands in Claude Code:"
echo "  - GitHub: Use tool 'search_repositories' with query"
echo "  - Filesystem: Use tool 'list_directory' with path"
echo "  - Memory: Use tool 'memory_store' with content"
echo "  - Docker: Use tool 'docker_list_containers'"
echo "  - Jupyter: Use tool 'jupyter_list_notebooks'"
echo "  - Kubernetes: Use tool 'kubernetes_list_pods'"
echo ""
echo "🎉 Setup complete! Your MCP servers should now be working in Claude Code."