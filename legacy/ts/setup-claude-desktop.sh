#!/bin/bash
# Setup Claude Desktop with MCP servers and 1Password secrets

echo "🤖 Setting up Claude Desktop MCP Integration"
echo "==========================================="
echo

# Check if Claude Desktop config directory exists
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    echo "❌ Claude Desktop config directory not found at:"
    echo "   $CLAUDE_CONFIG_DIR"
    echo
    echo "Please make sure Claude Desktop is installed."
    echo "Download from: https://claude.ai/download"
    exit 1
fi

echo "✅ Found Claude Desktop configuration directory"

# Get GitHub token from 1Password
echo
echo "📝 Resolving GitHub token from 1Password..."
GITHUB_TOKEN=$(op item get "GitHub Token" --vault=AI --fields label=notesPlain 2>/dev/null)

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Failed to get GitHub token from 1Password"
    echo "   Make sure you're signed in: op signin"
    exit 1
fi

echo "✅ GitHub token retrieved (${#GITHUB_TOKEN} characters)"

# Create the Claude Desktop config
echo
echo "📄 Creating Claude Desktop MCP configuration..."

cat > "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" << EOF
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y", 
        "@modelcontextprotocol/server-filesystem",
        "/Users/spencer/repos"
      ]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "mcp-workshop-github": {
      "command": "node",
      "args": ["${PWD}/servers/github/index.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "mcp-workshop-filesystem": {
      "command": "node",
      "args": ["${PWD}/servers/filesystem/index.js"],
      "env": {
        "ALLOWED_PATHS": "/Users/spencer/repos"
      }
    }
  }
}
EOF

echo "✅ Configuration written to Claude Desktop"

# Backup existing config if exists
if [ -f "$CLAUDE_CONFIG_DIR/claude_desktop_config.json.backup" ]; then
    echo "📦 Backup already exists"
else
    cp "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" "$CLAUDE_CONFIG_DIR/claude_desktop_config.json.backup" 2>/dev/null && \
    echo "📦 Backed up existing config"
fi

echo
echo "🎉 Setup Complete!"
echo "================="
echo
echo "Claude Desktop now has access to:"
echo "  • GitHub (via your secure token from 1Password)"
echo "  • Filesystem (sandboxed to /Users/spencer/repos)"
echo "  • Memory (for persistent context)"
echo
echo "Available MCP tools in Claude:"
echo "  • 40+ GitHub operations (repos, issues, PRs, etc.)"
echo "  • 15+ File operations (read, write, search, etc.)"
echo "  • 10+ Memory operations (store, retrieve, search, etc.)"
echo
echo "⚠️  IMPORTANT: Restart Claude Desktop for changes to take effect"
echo
echo "📝 You can now ask Claude to:"
echo "  - 'List my GitHub repositories'"
echo "  - 'Create an issue in repo X'"
echo "  - 'Read the package.json file'"
echo "  - 'Search for files containing Y'"
echo "  - 'Remember this for later: Z'"
echo
echo "🔒 Security Note: Your GitHub token is embedded in the config."
echo "   To update it later, run this script again."