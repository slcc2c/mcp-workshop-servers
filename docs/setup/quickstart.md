---
title: "Quick Start Guide - MCP Workshop Servers"
type: "setup"
difficulty: "beginner"
estimated_time: "5 minutes"
prerequisites: []
tags: ["setup", "quickstart", "getting-started"]
ai_context:
  purpose: "Get developers from zero to running MCP servers in under 5 minutes"
  dependencies: ["node-js", "npm", "claude-desktop"]
  integration_points: ["local-development", "ai-assistants"]
last_updated: "2025-01-27"
---

# Quick Start Guide

Get up and running with MCP Workshop Servers in under 5 minutes! This guide will help you set up a complete MCP server environment for rapid CS experimentation.

## System Requirements

### Minimum Requirements
- macOS 13.0+ (optimized for Mac Studio M3)
- Node.js 18.0+
- npm 9.0+
- 8GB RAM
- 10GB free disk space

### Recommended Setup
- Mac Studio M3 Ultra
- 32GB+ RAM
- Docker Desktop for Mac
- Claude Desktop installed

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/slcc2c/mcp-workshop-servers.git
cd mcp-workshop-servers
```

### 2. Install Dependencies

```bash
npm install
```

This installs all required packages including the MCP SDK and server dependencies.

### 3. Configure Claude Desktop

Add the following to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_config.json`

```json
{
  "mcpServers": {
    "workshop-github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token"
      }
    },
    "workshop-filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/your-username/projects"]
    },
    "workshop-memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

### 4. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# GitHub Integration
GITHUB_TOKEN=your_github_personal_access_token

# Database Connections (optional for quick start)
POSTGRES_URL=postgresql://user:pass@localhost:5432/workshop
REDIS_URL=redis://localhost:6379
MONGODB_URL=mongodb://localhost:27017/workshop

# Docker Configuration
DOCKER_HOST=unix:///var/run/docker.sock
```

### 5. Start MCP Servers

```bash
npm run mcp:start
```

This command starts all configured MCP servers. You should see:

```
✅ GitHub MCP Server started
✅ Filesystem MCP Server started
✅ Memory MCP Server started
✅ Docker MCP Server started
🚀 All servers running! Open Claude Desktop to start experimenting.
```

## Verify Installation

### Test with Claude Desktop

1. Open Claude Desktop
2. Start a new conversation
3. Type: "What MCP tools do I have available?"
4. Claude should list all available MCP servers and their capabilities

### Test Server Health

```bash
npm run mcp:status
```

Expected output:
```
📊 MCP Server Status:
- GitHub Server: ✅ Running (Port 3001)
- Filesystem Server: ✅ Running (Port 3002)
- Memory Server: ✅ Running (Port 3003)
- Docker Server: ✅ Running (Port 3004)
```

## Your First Experiment

Try this in Claude Desktop:

```
"Create a new Node.js project called 'hello-mcp' with Express, 
set up a basic API endpoint, and create a GitHub repository for it."
```

Claude will:
1. Use the Filesystem server to create project structure
2. Generate package.json and code files
3. Use the GitHub server to create and push the repository
4. Remember the context using the Memory server

## Common Quick Start Issues

### Issue: "Command not found: npx"
**Solution**: Install Node.js from [nodejs.org](https://nodejs.org) or via Homebrew:
```bash
brew install node
```

### Issue: "GitHub token not valid"
**Solution**: Create a personal access token:
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate new token with `repo`, `workflow` scopes
3. Add to `.env` file

### Issue: "Port already in use"
**Solution**: Check for conflicting processes:
```bash
lsof -i :3001-3010
# Kill conflicting process or change port in config
```

## Next Steps

### Essential Additions
1. [Set up GitHub self-hosted runner](./github-runner-setup.md) for CI/CD
2. [Configure databases](./database-setup.md) for data persistence
3. [Enable security features](./security.md) for production use

### Explore Features
- [Create custom MCP servers](../guides/custom-servers.md)
- [Integrate with VS Code](../guides/vscode-integration.md)
- [Build AI-powered workflows](../guides/ai-workflows.md)

### Advanced Configuration
- [Performance tuning](../troubleshooting/performance.md)
- [Multi-server orchestration](../guides/orchestration.md)
- [Production deployment](../guides/production.md)

## Quick Commands Reference

```bash
# Start all servers
npm run mcp:start

# Stop all servers
npm run mcp:stop

# Check status
npm run mcp:status

# View logs
npm run mcp:logs

# Run tests
npm test

# Build project
npm run build
```

## Getting Help

- 📖 [Full Documentation](../README.md)
- 💬 [GitHub Discussions](https://github.com/slcc2c/mcp-workshop-servers/discussions)
- 🐛 [Report Issues](https://github.com/slcc2c/mcp-workshop-servers/issues)
- 🤖 Ask Claude: "How do I use the MCP Workshop servers?"

---

🎉 **Congratulations!** You've achieved the "5-minute magic" - your MCP environment is ready for rapid experimentation!