# How to Share XcodeBuildMCP Setup with Other Instances

## Method 1: Share the Configuration File

The simplest way is to share your Claude Desktop configuration. You can:

1. **Export your current config**:
```bash
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json ~/Desktop/my-mcp-config.json
```

2. **Share the specific XcodeBuildMCP section**:
```json
{
  "mcpServers": {
    "xcodebuild": {
      "command": "node",
      "args": ["/Users/spencer/repos/mcp-server/external/XcodeBuildMCP/external/XcodeBuildMCP/build/index.js"],
      "env": {}
    }
  }
}
```

## Method 2: Create a Portable Setup Script

Create a script that others can run to set up XcodeBuildMCP:

```bash
#!/bin/bash
# save as: setup-xcodebuild-mcp.sh

# Clone and build XcodeBuildMCP
INSTALL_DIR="$HOME/mcp-servers"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ ! -d "XcodeBuildMCP" ]; then
    git clone https://github.com/cameroncooke/XcodeBuildMCP.git
    cd XcodeBuildMCP
    npm install
    npm run build
else
    echo "XcodeBuildMCP already installed"
fi

# Add to Claude Desktop config
CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

echo "Add this to your Claude Desktop config at: $CONFIG_FILE"
echo ""
cat << EOF
"xcodebuild": {
    "command": "node",
    "args": ["$INSTALL_DIR/XcodeBuildMCP/build/index.js"],
    "env": {}
}
EOF
```

## Method 3: Use NPX (Simplest for Others)

The easiest way for others to use XcodeBuildMCP is through npx:

```json
{
  "mcpServers": {
    "xcodebuild": {
      "command": "npx",
      "args": ["-y", "xcodebuildmcp"],
      "env": {}
    }
  }
}
```

**Note**: This requires the package to be published to npm. Check if it's available with:
```bash
npm view xcodebuildmcp
```

## Method 4: Create a Shared Configuration Repository

1. **Create a GitHub repo** with your MCP configurations:
```
my-mcp-configs/
├── README.md
├── configs/
│   ├── claude-desktop-full.json
│   ├── claude-desktop-minimal.json
│   └── servers/
│       ├── xcodebuild.json
│       ├── github.json
│       └── filesystem.json
└── scripts/
    ├── install-all.sh
    └── install-xcodebuild.sh
```

2. **Others can then**:
```bash
git clone https://github.com/yourusername/my-mcp-configs
./scripts/install-xcodebuild.sh
```

## Method 5: Use Environment Variables

Make the configuration portable by using environment variables:

```json
{
  "mcpServers": {
    "xcodebuild": {
      "command": "node",
      "args": ["${XCODEBUILD_MCP_PATH}/build/index.js"],
      "env": {}
    }
  }
}
```

Then share instructions:
```bash
# Add to ~/.zshrc or ~/.bash_profile
export XCODEBUILD_MCP_PATH="$HOME/mcp-servers/XcodeBuildMCP"
```

## Method 6: Create a Claude Desktop Config Manager

I can create a tool for you that manages multiple MCP server configurations:

```bash
# Example usage
mcp-config add xcodebuild --from-git https://github.com/cameroncooke/XcodeBuildMCP
mcp-config enable xcodebuild
mcp-config share xcodebuild --output xcodebuild-config.json
mcp-config import xcodebuild-config.json
```

## For Your Current Setup

Since you have XcodeBuildMCP installed at:
`/Users/spencer/repos/mcp-server/external/XcodeBuildMCP/external/XcodeBuildMCP/`

You can share this configuration snippet with others:

```json
{
  "mcpServers": {
    "xcodebuild": {
      "command": "node",
      "args": ["/absolute/path/to/XcodeBuildMCP/build/index.js"],
      "env": {}
    }
  }
}
```

They would need to:
1. Clone XcodeBuildMCP
2. Build it (`npm install && npm run build`)
3. Update the path in their config
4. Restart Claude Desktop

## Quick Sharing Commands

```bash
# Extract just the xcodebuild config
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | jq '.mcpServers.xcodebuild' > xcodebuild-config.json

# Create a setup bundle
tar -czf xcodebuild-mcp-setup.tar.gz \
    xcodebuild-config.json \
    /Users/spencer/repos/mcp-server/external/XcodeBuildMCP/external/XcodeBuildMCP/README.md

# Share via GitHub Gist
gh gist create xcodebuild-config.json --public --desc "XcodeBuildMCP Claude Desktop Configuration"
```

## Best Practice Recommendation

For easiest sharing, I recommend:

1. **For personal use**: Use Method 1 (share config file)
2. **For team use**: Use Method 4 (shared config repository)
3. **For public sharing**: Use Method 3 (npx if available) or create a setup script

Would you like me to create any of these sharing tools for you?