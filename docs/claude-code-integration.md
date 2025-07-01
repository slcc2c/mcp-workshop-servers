# Claude Code Integration Guide

This guide explains how to configure Claude Code instances to connect to and use the MCP Workshop servers.

## Quick Setup for Claude Code

### 1. Configuration File Setup

Copy this configuration to your Claude Desktop config file:

**Location**: 
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mcp-workshop": {
      "command": "node",
      "args": ["/Users/spencer/repos/mcp-server/dist/gateway/stdio-adapter.js"],
      "env": {
        "MCP_GATEWAY_URL": "http://localhost:3000",
        "MCP_AUTH_TOKEN": "sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20",
        "NODE_ENV": "production"
      }
    },
    "mcp-github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token"
      }
    },
    "mcp-filesystem": {
      "command": "npx",
      "args": [
        "-y", 
        "@modelcontextprotocol/server-filesystem",
        "/Users/spencer/repos/mcp-server"
      ]
    },
    "mcp-memory": {
      "command": "node",
      "args": ["/Users/spencer/repos/mcp-server/servers/memory/stdio.js"],
      "env": {
        "MEMORY_PROJECT": "claude-code-session",
        "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
      }
    }
  }
}
```

### 2. Environment Variables

Set these environment variables in your shell:

```bash
# Authentication token for MCP servers
export MCP_AUTH_TOKEN="sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"

# GitHub token for repository access
export GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token-here"

# Optional: Custom memory project name
export MEMORY_PROJECT="your-project-name"
```

### 3. Verify Connection

After restarting Claude Desktop, you should have access to these tools:

#### GitHub Tools
```
- github:search_repositories - Search GitHub repositories
- github:get_repository - Get repository details
- github:list_issues - List repository issues
- github:create_issue - Create new issues
- github:get_pull_requests - List pull requests
```

#### Filesystem Tools
```
- filesystem:read_file - Read file contents
- filesystem:write_file - Write files
- filesystem:list_directory - List directory contents
- filesystem:search_files - Search for files
- filesystem:watch_files - Monitor file changes
```

#### Memory Tools
```
- memory:store - Store information with tags
- memory:retrieve - Retrieve stored information
- memory:search - Search memories by tags/content
- memory:list_tags - List all available tags
- memory:graph - Get memory relationship graph
```

## Usage Examples

### 1. Store Context in Memory

```
Use the memory tool to store our conversation context:

Key: "claude-code-session-001"
Value: {
  "topic": "MCP server setup and integration",
  "progress": "Configured authentication and client connections",
  "next_steps": ["test all tools", "document usage patterns"]
}
Tags: ["session", "setup", "claude-code"]
```

### 2. Search GitHub for Related Projects

```
Search GitHub for MCP server implementations:
Query: "model context protocol server"
Sort by: stars
Limit: 10
```

### 3. Read Project Files

```
Read the main configuration file:
Path: /Users/spencer/repos/mcp-server/claude-desktop-config.json
```

### 4. Create Project Documentation

```
Write a summary of our work to:
Path: /Users/spencer/repos/mcp-server/session-notes.md
Content: [session summary and findings]
```

## Advanced Configuration

### Custom Memory Projects

Each Claude Code instance can have its own memory project:

```json
{
  "mcp-memory": {
    "command": "node",
    "args": ["/Users/spencer/repos/mcp-server/servers/memory/stdio.js"],
    "env": {
      "MEMORY_PROJECT": "claude-code-user-alice",
      "MEMORY_STORAGE_PATH": "/Users/spencer/.mcp/memory"
    }
  }
}
```

### Database Access (Optional)

If you need database access, add these servers:

```json
{
  "mcp-postgresql": {
    "command": "node",
    "args": ["/Users/spencer/repos/mcp-server/dist/servers/postgresql/index.js"],
    "env": {
      "POSTGRES_URL": "postgresql://user:pass@localhost:5432/dbname"
    }
  },
  "mcp-redis": {
    "command": "node",
    "args": ["/Users/spencer/repos/mcp-server/dist/servers/redis/index.js"],
    "env": {
      "REDIS_URL": "redis://localhost:6379"
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **"Server not found" errors**
   - Ensure MCP servers are running: `npm run mcp:start`
   - Check paths are correct in configuration
   - Verify authentication token is set

2. **Permission denied**
   - Check file paths are accessible
   - Verify authentication token matches server configuration
   - Ensure GitHub token has necessary permissions

3. **Memory not persisting**
   - Verify memory storage path exists: `~/.mcp/memory/`
   - Check project name matches across sessions
   - Ensure write permissions to storage directory

### Debug Commands

```bash
# Check if servers are running
curl -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  http://localhost:3000/api/v1/servers

# Test memory storage
ls -la ~/.mcp/memory/

# View server logs
tail -f /Users/spencer/repos/mcp-server/logs/gateway.log
```

## Security Notes

- **Never share authentication tokens** in public repositories
- **Use environment variables** for sensitive configuration
- **Limit filesystem access** to necessary directories only
- **Rotate tokens regularly** for production use

## API Reference

### Memory Server API

```typescript
// Store data
memory:store({
  key: string,
  value: any,
  tags?: string[],
  project?: string
})

// Retrieve data
memory:retrieve({
  key: string,
  project?: string
})

// Search memories
memory:search({
  tags?: string[],
  query?: string,
  project?: string
})
```

### GitHub Server API

```typescript
// Search repositories
github:search_repositories({
  query: string,
  sort?: "stars" | "forks" | "updated",
  limit?: number
})

// Get repository info
github:get_repository({
  owner: string,
  repo: string
})
```

### Filesystem Server API

```typescript
// Read file
filesystem:read_file({
  path: string,
  encoding?: "utf8" | "base64"
})

// Write file
filesystem:write_file({
  path: string,
  content: string,
  encoding?: "utf8" | "base64"
})
```

## Next Steps

1. **Test each tool** to ensure connectivity
2. **Create your own memory project** for session persistence
3. **Set up GitHub token** for repository access
4. **Explore advanced features** like database servers
5. **Share configurations** with your team (without tokens!)

For more detailed information, see the [complete documentation](./client-connections.md).