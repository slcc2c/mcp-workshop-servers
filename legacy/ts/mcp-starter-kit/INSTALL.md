# MCP Starter Kit Installation Guide

## Prerequisites Check

Before starting, ensure you have:

1. **Claude Desktop** installed
   - Download from: https://claude.ai/download
   - Verify: The app should be in your Applications folder

2. **Node.js 18+** installed
   - Check: `node --version` (should show v18.x.x or higher)
   - Install: https://nodejs.org/

3. **GitHub Personal Access Token**
   - Create at: https://github.com/settings/tokens
   - Required scopes: `repo`, `read:org`

4. **1Password CLI** (optional, for secure setup)
   - Install: https://developer.1password.com/docs/cli/get-started/
   - Verify: `op --version`

## Installation Methods

### Method 1: Basic Setup (Recommended)

```bash
# 1. Extract the starter kit
tar -xzf mcp-starter-kit-*.tar.gz
cd mcp-starter-kit-*/

# 2. Run setup
./setup.sh

# 3. Follow the prompts:
#    - Enter your GitHub token
#    - Choose your projects directory
#    - Enter a project name

# 4. Restart Claude Desktop
```

### Method 2: Secure Setup with 1Password

```bash
# 1. Extract the starter kit
tar -xzf mcp-starter-kit-*.tar.gz
cd mcp-starter-kit-*/

# 2. Sign in to 1Password
op signin

# 3. Run secure setup
./setup-with-1password.sh

# 4. Follow the prompts
#    - Token will be retrieved from 1Password
#    - Or you'll be guided to create and store one

# 5. Restart Claude Desktop
```

### Method 3: Manual Setup

If the scripts don't work on your system:

1. **Find your Claude config location:**
   - macOS: `~/Library/Application Support/Claude/`
   - Windows: `%APPDATA%\Claude\`
   - Linux: `~/.config/Claude/`

2. **Create the config file:**
   Create `claude_desktop_config.json` with:
   ```json
   {
     "mcpServers": {
       "github": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "env": {
           "GITHUB_PERSONAL_ACCESS_TOKEN": "YOUR_TOKEN_HERE"
         }
       },
       "filesystem": {
         "command": "npx",
         "args": [
           "-y", 
           "@modelcontextprotocol/server-filesystem",
           "/path/to/your/projects"
         ]
       },
       "memory": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-memory"]
       }
     }
   }
   ```

3. **Replace placeholders:**
   - `YOUR_TOKEN_HERE` → Your GitHub token
   - `/path/to/your/projects` → Your projects directory

4. **Restart Claude Desktop**

## Verification

After installation, verify everything works:

### 1. Check Configuration
```bash
./scripts/validate-config.sh
```

Should show:
- ✅ Valid JSON syntax
- ✅ GitHub token valid
- ✅ Filesystem path exists

### 2. Test GitHub Integration
```bash
./scripts/test-github.sh
```

Should show:
- Your GitHub username
- API rate limit status
- Repository access confirmation

### 3. Test in Claude Desktop

Open Claude and try:
- "List my GitHub repositories"
- "What files are in my project directory?"
- "Remember: This is a test"

## Troubleshooting

### Claude doesn't see the MCP servers

1. **Ensure Claude is fully quit:**
   - macOS: Cmd+Q, not just closing the window
   - Windows: Right-click system tray → Quit
   
2. **Check logs:**
   - macOS: `~/Library/Logs/Claude/`
   - Look for MCP-related errors

3. **Verify config location:**
   ```bash
   ls -la ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

### GitHub commands fail

1. **Token issues:**
   - Regenerate token at GitHub
   - Ensure it has `repo` scope
   - Re-run setup script

2. **Test token directly:**
   ```bash
   curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
   ```

### Memory commands don't work

1. **Check npx availability:**
   ```bash
   which npx
   npx --version
   ```

2. **Clear npm cache:**
   ```bash
   npm cache clean --force
   ```

### Filesystem access issues

1. **Verify directory exists:**
   ```bash
   ls -la /your/project/path
   ```

2. **Check permissions:**
   - Ensure you have read/write access
   - Path must be absolute, not relative

## Advanced Configuration

### Adding More MCP Servers

Edit your `claude_desktop_config.json`:

```json
"docker": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-docker"]
},
"postgres": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-postgres"],
  "env": {
    "POSTGRES_URL": "postgresql://user:pass@localhost/db"
  }
}
```

### Customizing Memory Tags

Set default project/session:
```bash
# Add to your shell profile (.bashrc, .zshrc, etc.)
export MCP_PROJECT=my-default-project
export MCP_SESSION=$(date +%Y-%m-%d)
```

### Automation

Create an alias for quick context switching:
```bash
# Add to shell profile
alias mcp-switch='function _mcp() { export MCP_PROJECT=$1; echo "Switched to project: $1"; }; _mcp'

# Usage
mcp-switch my-webapp
mcp-switch api-backend
```

## Security Best Practices

1. **Token Security:**
   - Use fine-grained personal access tokens
   - Minimum required scopes only
   - Rotate every 90 days

2. **Filesystem Sandboxing:**
   - Only grant access to project directories
   - Never grant access to home directory root
   - Use separate directories for different clients

3. **1Password Integration:**
   - Store all tokens in 1Password
   - Use the refresh script regularly
   - Enable 2FA on GitHub

## Getting Help

- **Issues**: File on our GitHub repository
- **Examples**: See `examples/project-setup.md`
- **Memory Guide**: See `docs/memory-segregation-guide.md`

## Next Steps

1. Read the [Memory Segregation Guide](docs/memory-segregation-guide.md)
2. Try the [Example Projects](examples/project-setup.md)
3. Set up your first project with proper context
4. Explore advanced MCP servers for databases, Docker, etc.

Happy coding with Claude! 🤖