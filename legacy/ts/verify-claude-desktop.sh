#!/bin/bash
# Verify Claude Desktop MCP configuration

echo "🔍 Verifying Claude Desktop MCP Setup"
echo "===================================="
echo

CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

if [ ! -f "$CLAUDE_CONFIG" ]; then
    echo "❌ Claude Desktop config not found"
    exit 1
fi

echo "✅ Config file exists"
echo

# Check if MCP servers are configured
echo "📋 Configured MCP Servers:"
jq -r '.mcpServers | keys[]' "$CLAUDE_CONFIG" 2>/dev/null | while read server; do
    echo "   • $server"
done

# Test if the tools are accessible
echo
echo "🧪 Testing MCP server availability..."

# Test npx commands
echo -n "   GitHub server: "
if npx -y @modelcontextprotocol/server-github --help &>/dev/null; then
    echo "✅ Available"
else
    echo "❌ Not found"
fi

echo -n "   Filesystem server: "
if npx -y @modelcontextprotocol/server-filesystem --help &>/dev/null; then
    echo "✅ Available"
else
    echo "❌ Not found"
fi

echo -n "   Memory server: "
if npx -y @modelcontextprotocol/server-memory --help &>/dev/null; then
    echo "✅ Available"
else
    echo "❌ Not found"
fi

# Check if token is configured
echo
echo "🔐 Security check:"
if grep -q "GITHUB_PERSONAL_ACCESS_TOKEN" "$CLAUDE_CONFIG"; then
    TOKEN_LENGTH=$(jq -r '.mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN' "$CLAUDE_CONFIG" 2>/dev/null | wc -c)
    echo "   GitHub token: ✅ Configured ($((TOKEN_LENGTH-1)) characters)"
else
    echo "   GitHub token: ❌ Not configured"
fi

echo
echo "📁 Filesystem access:"
FILESYSTEM_PATH=$(jq -r '.mcpServers.filesystem.args[2]' "$CLAUDE_CONFIG" 2>/dev/null)
if [ -d "$FILESYSTEM_PATH" ]; then
    echo "   Path: $FILESYSTEM_PATH ✅"
    echo "   Contents: $(ls -1 "$FILESYSTEM_PATH" | wc -l) items"
else
    echo "   Path: $FILESYSTEM_PATH ❌ (not found)"
fi

echo
echo "✨ Next Steps:"
echo "1. Restart Claude Desktop"
echo "2. Look for the MCP icon in Claude's interface"
echo "3. Try these commands in Claude:"
echo "   - 'What GitHub repositories do I have?'"
echo "   - 'Show me the contents of my repos directory'"
echo "   - 'Remember that I'm working on MCP server setup'"