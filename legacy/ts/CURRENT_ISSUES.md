# Current MCP Server Issues

## Fixed Issues ✅
1. **GitHub MCP Server** - Now using local runner with proper authentication mapping
2. **ESM Imports** - Fixed with `scripts/fix-esm-imports.js`
3. **Vitest Configuration** - Fixed syntax error (missing closing brace)
4. **Claude Code Configuration** - Updated to use local runners instead of npm packages

## Working Servers (5/12) ✅
- **github** - Local runner configured
- **filesystem** - Using npm package
- **memory** - Local runner working
- **docker** - Local runner working (needs Docker daemon running)
- **xcodebuild** - External package working

## Servers Needing Configuration (6/12) ⚠️
These servers are implemented but need environment variables:

### PostgreSQL
```bash
export POSTGRES_URL="postgresql://user:password@localhost:5432/dbname"
```

### Redis
```bash
export REDIS_URL="redis://localhost:6379"
```

### MongoDB
```bash
export MONGODB_URL="mongodb://localhost:27017"
```

### Neo4j
```bash
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
```

### Jupyter
Needs Jupyter installed:
```bash
pip install jupyter
export JUPYTER_TOKEN="your-token"
```

### Kubernetes
Needs kubectl configured with cluster access

## Not Configured (1/12) 🔧
- **mcp-workshop-gateway** - Not needed for Claude Code (only for Claude Desktop)

## Required Environment Variables
For full functionality, set these environment variables:
```bash
# GitHub (required for GitHub MCP)
export GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token"

# Databases (optional, only if using)
export POSTGRES_URL="postgresql://user:password@localhost:5432/dbname"
export REDIS_URL="redis://localhost:6379"
export MONGODB_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"

# Jupyter (optional)
export JUPYTER_TOKEN="your-jupyter-token"
```

## Next Steps
1. Set the required environment variables for the servers you want to use
2. Ensure Docker daemon is running for Docker MCP server
3. Install Jupyter if you want to use the Jupyter server
4. Configure kubectl for Kubernetes server access