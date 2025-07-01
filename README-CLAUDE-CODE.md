# 🤖 Claude Code MCP Integration

This repository provides a comprehensive MCP (Model Context Protocol) server ecosystem specifically designed for Claude Code integration.

## 🚀 Quick Start for Claude Code Instances

### Option 1: Copy Configuration File
```bash
cp claude-desktop-config.json ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Option 2: Manual Setup
Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mcp-workshop": {
      "command": "node",
      "args": ["/Users/spencer/repos/mcp-server/dist/gateway/stdio-adapter.js"],
      "env": {
        "MCP_GATEWAY_URL": "http://localhost:3000",
        "MCP_AUTH_TOKEN": "sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"
      }
    }
  }
}
```

**Then restart Claude Desktop completely.**

## 🛠️ Available Tools

### Memory System
- **Persistent context storage** across sessions
- **Tag-based organization** for easy retrieval
- **Project isolation** for different use cases
- **Graph relationships** between stored data

### GitHub Integration  
- **Repository search** and exploration
- **Issue and PR management** 
- **Code analysis** capabilities
- **Project discovery** tools

### Filesystem Access
- **Secure file operations** within project boundaries
- **Real-time file watching**
- **Content search** and manipulation
- **Project file management**

### Database Servers (Advanced)
- **PostgreSQL** - Relational database operations
- **Redis** - In-memory data store and caching
- **MongoDB** - NoSQL document database
- **Neo4j** - Graph database with Cypher queries

### Development Tools
- **Docker** - Container management
- **Kubernetes** - Orchestration and deployment
- **Jupyter** - Interactive notebook execution

## 📖 Documentation

- **[Quick Start Guide](./claude-code-quickstart.md)** - 5-minute setup
- **[Integration Guide](./docs/claude-code-integration.md)** - Comprehensive setup
- **[Client Connections](./docs/client-connections.md)** - Advanced configuration
- **[Share Instructions](./share-with-claude-code.md)** - Copy-paste setup for other instances

## 🎯 Example Usage

### Store Session Context
```
Use memory:store to save our conversation:
Key: "session-analysis"
Value: {"topic": "MCP integration", "findings": ["easy setup", "powerful tools"]}
Tags: ["session", "analysis"]
```

### Explore Codebase
```
Use filesystem:list_directory to see the project structure
```

### Research Related Projects
```
Use github:search_repositories to find "model context protocol" projects
```

## 🔧 Troubleshooting

### Tools Not Appearing
1. Check config file location and syntax
2. Verify environment variables are set
3. Restart Claude Desktop completely
4. Check server status: `npm run mcp:status`

### Connection Issues
1. Ensure servers are running: `npm run mcp:start`
2. Test connectivity: `curl http://localhost:3000/health`
3. Verify authentication token

### Memory Not Persisting
1. Check storage path: `~/.mcp/memory/`
2. Verify project names match across sessions
3. Ensure write permissions

## 🔐 Security

- **Token-based authentication** for secure access
- **Sandboxed filesystem access** to project directories only
- **Client-specific permissions** and rate limiting
- **Audit logging** for all operations

## 🏗️ Architecture

```
Claude Code Instance
        ↓ stdio
Gateway Adapter (stdio-adapter.js)
        ↓ HTTP + Auth
MCP Gateway (localhost:3000)
        ↓ Routes to
Individual MCP Servers
```

## 🎉 Features

- **🧠 Persistent Memory** - Context survives across sessions
- **🐙 GitHub Integration** - Full repository management
- **📁 File System** - Secure project file access
- **🗄️ Databases** - PostgreSQL, Redis, MongoDB, Neo4j
- **🐳 DevOps** - Docker and Kubernetes integration
- **📊 Analytics** - Jupyter notebook execution
- **🔐 Security** - Token-based authentication
- **⚡ Performance** - Connection pooling and caching

## 📊 Server Status

Check what's running:
```bash
npm run mcp:status
```

Start all servers:
```bash
npm run mcp:start
```

## 🤝 Sharing with Other Claude Code Instances

Simply share the contents of `share-with-claude-code.md` with other Claude Code instances for instant setup.

---

**Ready to explore? Start by storing something in memory and then browse the available tools!** 🚀