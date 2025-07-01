# 🚀 Claude Code CLI MCP Setup

**Setting up MCP servers for Claude Code CLI (not Claude Desktop)**

## Quick Setup Commands

### 1. Add Memory Server
```bash
claude mcp add memory node /Users/spencer/repos/mcp-server/servers/memory/index.ts \
  -e MEMORY_PROJECT=claude-code-session \
  -e MEMORY_STORAGE_PATH=/Users/spencer/.mcp/memory
```

### 2. Add Filesystem Server
```bash
claude mcp add filesystem npx @modelcontextprotocol/server-filesystem /Users/spencer/repos/mcp-server
```

### 3. Add GitHub Server  
```bash
claude mcp add github npx @modelcontextprotocol/server-github \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN
```

### 4. Add MCP Gateway (HTTP)
```bash
claude mcp add --transport http mcp-gateway http://localhost:3000/api/v1 \
  -e MCP_AUTH_TOKEN=$MCP_AUTH_TOKEN
```

## Alternative: Project-Wide Configuration

Create `.mcp.json` in your project directory:

```json
{
  "mcpServers": {
    "memory": {
      "command": "node",
      "args": ["/Users/spencer/repos/mcp-server/servers/memory/index.ts"],
      "env": {
        "MEMORY_PROJECT": "claude-code-session",
        "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem", "/Users/spencer/repos/mcp-server"]
    },
    "github": {
      "command": "npx", 
      "args": ["@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "env:GITHUB_PERSONAL_ACCESS_TOKEN"
      }
    },
    "mcp-gateway": {
      "transport": "http",
      "url": "http://localhost:3000/api/v1",
      "headers": {
        "Authorization": "Bearer env:MCP_AUTH_TOKEN"
      }
    }
  }
}
```

## Verification Commands

```bash
# List configured servers
claude mcp list

# Test a specific server
claude mcp get memory

# Check server status
claude mcp get github
```

## Using MCP Tools in Claude Code

Once configured, you can use tools directly in Claude Code CLI:

### Memory Operations
```
Store this conversation context in memory:
Key: "claude-code-setup"
Value: {"topic": "MCP integration", "status": "configured"}
Tags: ["setup", "claude-code"]
```

### File Operations  
```
Read the package.json file from the MCP server project
```

### GitHub Operations
```
Search GitHub for "model context protocol" repositories
```

## Environment Variables (Fish Shell)

Your environment is already configured with:
```fish
set -gx MCP_AUTH_TOKEN "sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"
set -gx GITHUB_PERSONAL_ACCESS_TOKEN "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"
```

## Troubleshooting

### Check if servers are configured:
```bash
claude mcp list
```

### Remove and re-add a server:
```bash
claude mcp remove memory
claude mcp add memory node /Users/spencer/repos/mcp-server/servers/memory/index.ts
```

### Check MCP gateway is running:
```bash
curl -H "Authorization: Bearer $MCP_AUTH_TOKEN" http://localhost:3000/api/v1/servers
```

## Transport Types

### Stdio (Default)
- Direct process communication
- Best for local servers
- Example: Memory, GitHub, Filesystem servers

### HTTP  
- REST API communication
- Best for remote/gateway servers
- Example: MCP Gateway

### SSE (Server-Sent Events)
- Real-time streaming
- Good for live updates
- Example: Log streaming, file watching

## Next Steps

1. **Run the setup commands above**
2. **Verify with `claude mcp list`** 
3. **Test tools in Claude Code CLI**
4. **Create memories for persistent context**

The main difference from Claude Desktop is using `claude mcp add` commands instead of config files!