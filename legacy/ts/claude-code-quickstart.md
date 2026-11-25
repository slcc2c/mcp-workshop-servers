# 🚀 Claude Code MCP Quickstart

**5-minute setup to connect Claude Code to MCP Workshop servers**

## Step 1: Copy Configuration (2 minutes)

**Copy this EXACT configuration** to your Claude Desktop config file:

### macOS:
```bash
cp /Users/spencer/repos/mcp-server/claude-desktop-config.json \
   ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Manual Setup:
Create `~/Library/Application Support/Claude/claude_desktop_config.json` with:

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

## Step 2: Set Environment Variables (1 minute)

### For Bash/Zsh:
Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# MCP Authentication
export MCP_AUTH_TOKEN="sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"

# GitHub Access (optional - replace with your token)
export GITHUB_PERSONAL_ACCESS_TOKEN="<GITHUB_TOKEN>"
```

Then reload: `source ~/.zshrc`

### For Fish Shell:
Add to `~/.config/fish/config.fish`:

```fish
# MCP Authentication  
set -gx MCP_AUTH_TOKEN "sK0pHxZ-UyaRTakFZ8MxVS80i1zd3DFfP6CO6hGav20"

# GitHub Authentication
set -gx GITHUB_PERSONAL_ACCESS_TOKEN "<GITHUB_TOKEN>"
```

## Step 3: Verify Servers Running (30 seconds)

```bash
# Check if MCP servers are running
curl -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  http://localhost:3000/api/v1/servers
```

If not running:
```bash
cd /Users/spencer/repos/mcp-server
npm run mcp:start
```

## Step 4: Restart Claude Desktop (30 seconds)

1. Quit Claude Desktop completely
2. Restart Claude Desktop
3. Wait for it to fully load

## Step 5: Test Tools (1 minute)

In Claude Desktop, try these commands:

### Test Memory
```
Store this in memory:
Key: "quickstart-test"
Value: "Successfully connected to MCP servers"
Tags: ["test", "quickstart"]
```

### Test GitHub (if token configured)
```
Search GitHub for "model context protocol" repositories
```

### Test Filesystem
```
List files in the MCP server directory
```

## ✅ Success Indicators

You should see these tools available in Claude Desktop:
- `memory:store`, `memory:retrieve`, `memory:search`
- `github:search_repositories`, `github:get_repository` (if GitHub token set)
- `filesystem:read_file`, `filesystem:write_file`, `filesystem:list_directory`

## 🔧 Quick Troubleshooting

### "Tool not found"
- Check config file location is correct
- Verify JSON syntax is valid
- Restart Claude Desktop completely

### "Connection failed"
- Ensure MCP servers are running: `npm run mcp:status`
- Check environment variables: `echo $MCP_AUTH_TOKEN`
- Verify network connectivity: `curl http://localhost:3000/health`

### "Permission denied"
- Check file paths exist
- Verify authentication token is correct
- Ensure servers have proper permissions

## 🎯 What You Get

### Memory System
- **Persistent context** across Claude Code sessions
- **Tag-based organization** of information
- **Project isolation** for different use cases
- **Graph relationships** between stored data

### GitHub Integration
- **Repository search** and exploration
- **Issue and PR management**
- **Code analysis** and documentation
- **Project discovery** and research

### Filesystem Access
- **Secure file operations** within allowed directories
- **File watching** for live updates
- **Content search** and manipulation
- **Project file management**

## 🔗 Useful Commands

### Memory Operations
```
# Store session context
memory:store key="session-001" value={"topic": "...", "progress": "..."} tags=["session"]

# Retrieve previous context
memory:retrieve key="session-001"

# Search by topic
memory:search tags=["session"] query="MCP setup"

# View all memories
memory:search project="claude-code-session"
```

### File Operations
```
# Read configuration
filesystem:read_file path="/Users/spencer/repos/mcp-server/package.json"

# Create notes
filesystem:write_file path="./session-notes.md" content="# My Claude Code Session\n..."

# List project files
filesystem:list_directory path="/Users/spencer/repos/mcp-server" recursive=false
```

### GitHub Research
```
# Find related projects
github:search_repositories query="MCP server typescript" sort="stars"

# Get specific repo details
github:get_repository owner="modelcontextprotocol" repo="specification"
```

## 🚀 Next Steps

1. **Test each tool** to ensure everything works
2. **Create a memory project** for your sessions
3. **Set up GitHub token** for repository access
4. **Explore the servers** - there are 10+ available!
5. **Read full docs** at `/docs/claude-code-integration.md`

---

**Need help?** Check the full documentation or ask Claude Code to help debug using the available tools!