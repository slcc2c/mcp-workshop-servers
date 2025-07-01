#!/bin/bash

# Configure ALL MCP servers for Claude Code with proper runners

echo "🔧 Configuring ALL MCP servers for Claude Code..."

# Remove all existing servers to start fresh
echo "Removing existing servers..."
servers=(github filesystem memory docker jupyter kubernetes postgresql redis mongodb neo4j xcodebuild)
for server in "${servers[@]}"; do
  claude mcp remove "$server" -s user 2>/dev/null
done

# GitHub server (official)
echo "Adding GitHub server..."
claude mcp add-json github -s user '{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN_REMOVED"
  }
}'

# Filesystem server (official)
echo "Adding Filesystem server..."
claude mcp add filesystem -s user npx -- -y @modelcontextprotocol/server-filesystem /Users/spencer/repos

# Memory server (custom)
echo "Adding Memory server..."
claude mcp add-json memory -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/memory-server.js"],
  "env": {
    "MEMORY_PROJECT": "claude-mcp-session",
    "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
  }
}'

# Docker server (custom)
echo "Adding Docker server..."
claude mcp add-json docker -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/docker-server.js"],
  "env": {
    "DOCKER_HOST": "unix:///var/run/docker.sock"
  }
}'

# Jupyter server (custom)
echo "Adding Jupyter server..."
claude mcp add-json jupyter -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/jupyter-server.js"],
  "env": {
    "JUPYTER_BASE_URL": "http://localhost:8888"
  }
}'

# Kubernetes server (custom)
echo "Adding Kubernetes server..."
claude mcp add-json kubernetes -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/kubernetes-server.js"],
  "env": {
    "KUBECONFIG": "/Users/spencer/.kube/config"
  }
}'

# PostgreSQL server (custom)
echo "Adding PostgreSQL server..."
claude mcp add-json postgresql -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/postgresql-server.js"],
  "env": {
    "POSTGRES_URL": "postgresql://localhost:5432/postgres"
  }
}'

# Redis server (custom)
echo "Adding Redis server..."
claude mcp add-json redis -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/redis-server.js"],
  "env": {
    "REDIS_URL": "redis://localhost:6379"
  }
}'

# MongoDB server (custom)
echo "Adding MongoDB server..."
claude mcp add-json mongodb -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/mongodb-server.js"],
  "env": {
    "MONGODB_URL": "mongodb://localhost:27017",
    "MONGODB_DATABASE": "mcp_workshop"
  }
}'

# Neo4j server (custom)
echo "Adding Neo4j server..."
claude mcp add-json neo4j -s user '{
  "command": "node",
  "args": ["/Users/spencer/repos/mcp-server/runners/neo4j-server.js"],
  "env": {
    "NEO4J_URL": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password"
  }
}'

echo ""
echo "✅ ALL MCP servers configured!"
echo ""
echo "Current servers:"
claude mcp list

echo ""
echo "📝 Test commands:"
echo "  - GitHub: search_repositories"
echo "  - Filesystem: list_directory"
echo "  - Memory: memory_store"
echo "  - Docker: docker_list_containers"
echo "  - Jupyter: jupyter_list_notebooks"
echo "  - Kubernetes: kubernetes_list_pods"
echo "  - PostgreSQL: postgresql_execute_query"
echo "  - Redis: redis_get"
echo "  - MongoDB: mongodb_find"
echo "  - Neo4j: neo4j_execute_query"