# MCP Starter Kit - 5-Minute Setup

> Get Claude Desktop integrated with GitHub, filesystem access, and memory persistence in under 5 minutes!

## What's Included

This starter kit provides:
- **GitHub Integration** - Full access to repositories, issues, PRs, and more
- **Filesystem Access** - Sandboxed file operations in your project directories
- **Memory Persistence** - Project-segregated context that persists across sessions
- **Secret Management** - Optional 1Password integration for secure token storage

## Prerequisites

1. **Claude Desktop** - [Download here](https://claude.ai/download)
2. **Node.js 18+** - [Download here](https://nodejs.org/)
3. **GitHub Personal Access Token** - [Create one here](https://github.com/settings/tokens)
4. **1Password CLI** (optional) - [Install guide](https://developer.1password.com/docs/cli/get-started/)

## Quick Start

### 1. Basic Setup (2 minutes)

```bash
# Clone this starter kit
git clone https://github.com/your-org/mcp-starter-kit.git
cd mcp-starter-kit

# Run the setup script
./setup.sh

# Enter your GitHub token when prompted
# Choose your project directory when prompted

# Restart Claude Desktop
```

### 2. With 1Password Integration (3 minutes)

```bash
# Sign in to 1Password CLI
op signin

# Run setup with 1Password
./setup-with-1password.sh

# Restart Claude Desktop
```

## Memory Segregation Strategy

This kit includes an advanced memory segregation system that keeps your project contexts separate:

### How It Works

Every memory is automatically tagged with:
- `project:<your-project-name>` - Identifies which project the memory belongs to
- `session:<YYYY-MM-DD>` - Tracks when the memory was created

### Usage Examples

In Claude Desktop, you can now:

```
# Store project-specific information
"Remember for project:my-app: We use React 18 with TypeScript"

# Search within your project
"What do you know about project:my-app?"

# Set session context
"Remember: Working on authentication feature today"
```

### Memory Helper Script

Use the included helper script for command-line memory management:

```bash
# Set your project context
export MCP_PROJECT=my-app
export MCP_SESSION=2025-06-28

# Store a memory
./scripts/memory-helper.sh store "Database is PostgreSQL 15" architecture

# Search memories
./scripts/memory-helper.sh search "database"

# List all project memories
./scripts/memory-helper.sh list
```

## What You Can Do

Once set up, ask Claude to:

### GitHub Operations
- "List my GitHub repositories"
- "Create a new issue in repo X"
- "Show recent PRs in project Y"
- "Create a new repository called Z"

### File Operations
- "Read the package.json file"
- "Search for files containing 'TODO'"
- "Create a new file called config.js"
- "Show me all TypeScript files"

### Memory Operations
- "Remember: This project uses Tailwind CSS"
- "What do you know about this project?"
- "List all my preferences"

## Configuration

The configuration is stored in:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Customizing Access

Edit your `claude_desktop_config.json` to:

1. **Change filesystem access path**:
```json
"filesystem": {
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/your/path/here"]
}
```

2. **Add more MCP servers**:
```json
"docker": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-docker"]
}
```

## Security Best Practices

1. **GitHub Token Security**
   - Use fine-grained personal access tokens
   - Limit scope to only necessary permissions
   - Rotate tokens regularly

2. **Filesystem Sandboxing**
   - Only grant access to project directories
   - Never grant access to system directories
   - Use absolute paths for clarity

3. **Memory Privacy**
   - Memories are stored locally on your machine
   - Use project tags to prevent cross-contamination
   - Periodically clean old session data

## Troubleshooting

### Claude doesn't see the MCP servers
- Restart Claude Desktop completely
- Check the logs: `~/Library/Logs/Claude/`
- Verify config syntax with: `./scripts/validate-config.sh`

### GitHub operations fail
- Verify your token has necessary scopes
- Check token hasn't expired
- Test with: `./scripts/test-github.sh`

### Memory search returns unrelated results
- Ensure you're using project tags consistently
- Check your MCP_PROJECT environment variable
- Use the memory-helper script for debugging

## Advanced Usage

### Creating Custom MCP Servers

Use the included template:

```bash
./scripts/create-mcp-server.sh my-custom-server
```

### Integrating with CI/CD

```yaml
# .github/workflows/mcp-context.yml
- name: Store CI context in Claude memory
  run: |
    export MCP_PROJECT=${{ github.repository }}
    ./scripts/memory-helper.sh store "CI build ${{ github.run_number }} passed" ci
```

## Support

- **Documentation**: See the `docs/` directory
- **Examples**: Check `examples/` for common patterns
- **Issues**: File on our GitHub repository
- **Community**: Join our Discord server

## License

MIT License - feel free to use this in your projects!

---

Built with love for the AI-assisted development community 🤖❤️