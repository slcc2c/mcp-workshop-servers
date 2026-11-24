#!/bin/bash

# Export XcodeBuildMCP configuration for sharing

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
OUTPUT_FILE="${1:-xcodebuild-mcp-config.json}"

echo -e "${BLUE}📤 Exporting XcodeBuildMCP Configuration${NC}"
echo ""

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠${NC} Claude Desktop config not found"
    exit 1
fi

# Extract xcodebuild config using jq
if command -v jq &> /dev/null; then
    # Extract and create a complete config
    jq '{mcpServers: {xcodebuild: .mcpServers.xcodebuild}}' "$CONFIG_FILE" > "$OUTPUT_FILE"
    
    echo -e "${GREEN}✓${NC} Configuration exported to: $OUTPUT_FILE"
    echo ""
    echo "Share this file with others. They can add it to their Claude Desktop config."
    echo ""
    echo "Contents:"
    cat "$OUTPUT_FILE"
else
    # Fallback: Create manual config
    cat > "$OUTPUT_FILE" << 'EOF'
{
  "mcpServers": {
    "xcodebuild": {
      "command": "node",
      "args": ["INSERT_PATH_TO_XCODEBUILD_MCP/build/index.js"],
      "env": {}
    }
  }
}
EOF
    echo -e "${YELLOW}⚠${NC} jq not found. Created template config in: $OUTPUT_FILE"
    echo "Edit the file to add the correct path to XcodeBuildMCP"
fi

echo ""
echo -e "${BLUE}📋 Quick Setup Instructions for Others:${NC}"
echo ""
echo "1. Clone XcodeBuildMCP:"
echo "   git clone https://github.com/cameroncooke/XcodeBuildMCP.git"
echo ""
echo "2. Build it:"
echo "   cd XcodeBuildMCP && npm install && npm run build"
echo ""
echo "3. Update their Claude Desktop config with the contents of $OUTPUT_FILE"
echo ""
echo "4. Restart Claude Desktop"

# Create a shareable setup script
SETUP_SCRIPT="setup-xcodebuild-mcp.sh"
cat > "$SETUP_SCRIPT" << 'EOF'
#!/bin/bash
# XcodeBuildMCP Quick Setup Script

echo "🚀 Setting up XcodeBuildMCP for Claude Desktop"

# Install location
MCP_DIR="$HOME/.mcp/servers"
mkdir -p "$MCP_DIR"
cd "$MCP_DIR"

# Clone and build
if [ ! -d "XcodeBuildMCP" ]; then
    echo "📦 Cloning XcodeBuildMCP..."
    git clone https://github.com/cameroncooke/XcodeBuildMCP.git
    cd XcodeBuildMCP
    echo "🔨 Building..."
    npm install
    npm run build
    cd ..
fi

# Show config to add
echo ""
echo "✅ XcodeBuildMCP installed at: $MCP_DIR/XcodeBuildMCP"
echo ""
echo "Add this to your Claude Desktop config:"
echo "(Usually at: ~/Library/Application Support/Claude/claude_desktop_config.json)"
echo ""
cat << CONFIG
{
  "mcpServers": {
    "xcodebuild": {
      "command": "node",
      "args": ["$MCP_DIR/XcodeBuildMCP/build/index.js"],
      "env": {}
    }
  }
}
CONFIG
echo ""
echo "Then restart Claude Desktop!"
EOF

chmod +x "$SETUP_SCRIPT"

echo ""
echo -e "${GREEN}✓${NC} Also created setup script: $SETUP_SCRIPT"
echo "   Others can run this script to automatically install XcodeBuildMCP"