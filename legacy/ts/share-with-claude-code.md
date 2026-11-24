# 📋 Share This With Other Claude Code Instances

**Copy and paste this message to share MCP server access with other Claude Code instances:**

---

## 🎉 You now have access to MCP Workshop Servers!

I've set up a comprehensive MCP server ecosystem that you can connect to. Here's everything you need:

### ⚡ Quick Setup (5 minutes)

1. **Add this to your Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

2. **Set environment variable**:
```bash
export MCP_AUTH_TOKEN="sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"
```

3. **Restart Claude Desktop** completely

### 🛠️ Available Tools

You'll have access to these powerful tools:

#### 🧠 **Memory System**
- `memory:store` - Save context, notes, and session data
- `memory:retrieve` - Get stored information
- `memory:search` - Find memories by tags or content
- Perfect for maintaining context across conversations!

#### 🐙 **GitHub Integration** 
- `github:search_repositories` - Find relevant repos
- `github:get_repository` - Get repo details
- `github:list_issues` - Browse issues and PRs
- Great for research and code exploration!

#### 📁 **Filesystem Access**
- `filesystem:read_file` - Read any file in the project
- `filesystem:write_file` - Create/modify files
- `filesystem:list_directory` - Browse directories
- Secure access to the MCP server codebase!

### 🎯 Try These Commands

**Test the memory system:**
```
Store this information in memory:
Key: "my-session"
Value: {"topic": "Exploring MCP servers", "timestamp": "now"}
Tags: ["session", "exploration"]
```

**Explore the codebase:**
```
List files in the MCP server directory to see what's available
```

**Find related projects:**
```
Search GitHub for "model context protocol" repositories
```

### 🗂️ What's Available

This MCP server ecosystem includes:

- **Gateway Server** - Central routing and authentication
- **Memory Server** - Persistent context storage
- **GitHub Server** - Repository management
- **Filesystem Server** - Secure file operations  
- **Docker Server** - Container management
- **Database Servers** - PostgreSQL, Redis, MongoDB, Neo4j
- **Jupyter Server** - Notebook execution
- **Kubernetes Server** - Orchestration tools

### 💡 Pro Tips

1. **Use memory storage** to maintain context between conversations
2. **Store your findings** with descriptive tags for easy retrieval
3. **Explore the codebase** to understand the implementation
4. **Search GitHub** for inspiration and related projects
5. **Create your own memory project** with a unique name

### 🔧 Troubleshooting

If tools don't appear:
- Verify config file location and JSON syntax
- Check environment variable: `echo $MCP_AUTH_TOKEN`
- Ensure servers are running: `curl http://localhost:3000/health`
- Restart Claude Desktop completely

### 📚 Documentation

Full documentation available at:
- `/Users/spencer/repos/mcp-server/docs/claude-code-integration.md`
- `/Users/spencer/repos/mcp-server/claude-code-quickstart.md`

### 🚀 Get Started

Try storing some information in memory right now, then explore the available tools. The memory system will help you maintain context across our conversations!

---

**This gives you access to a full MCP development environment with persistent memory, GitHub integration, and secure filesystem access. Have fun exploring!** 🎉