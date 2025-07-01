#!/bin/bash
# Validate Claude Desktop MCP configuration

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)    echo "macos";;
        Linux*)     echo "linux";;
        CYGWIN*|MINGW*|MSYS*) echo "windows";;
        *)          echo "unknown";;
    esac
}

# Function to get Claude config directory
get_claude_config_dir() {
    local os=$(detect_os)
    case "$os" in
        macos)
            echo "$HOME/Library/Application Support/Claude"
            ;;
        windows)
            echo "$APPDATA/Claude"
            ;;
        linux)
            echo "$HOME/.config/Claude"
            ;;
        *)
            echo ""
            ;;
    esac
}

echo -e "${BLUE}🔍 Validating Claude Desktop MCP Configuration${NC}"
echo "============================================="
echo

# Find config file
CLAUDE_CONFIG_DIR=$(get_claude_config_dir)
CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Configuration file not found${NC}"
    echo "   Expected at: $CONFIG_FILE"
    exit 1
fi

echo -e "${GREEN}✅ Found configuration file${NC}"

# Check JSON syntax
echo -e "${BLUE}Checking JSON syntax...${NC}"
if command -v jq &> /dev/null; then
    if jq . "$CONFIG_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Valid JSON syntax${NC}"
    else
        echo -e "${RED}❌ Invalid JSON syntax${NC}"
        jq . "$CONFIG_FILE" 2>&1 | head -n 5
        exit 1
    fi
else
    # Fallback check
    if python3 -m json.tool "$CONFIG_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Valid JSON syntax${NC}"
    else
        echo -e "${RED}❌ Invalid JSON syntax${NC}"
        exit 1
    fi
fi

# Check MCP servers
echo
echo -e "${BLUE}Checking MCP servers...${NC}"

if command -v jq &> /dev/null; then
    SERVERS=$(jq -r '.mcpServers | keys[]' "$CONFIG_FILE" 2>/dev/null)
else
    SERVERS=$(grep -o '"[^"]*"[[:space:]]*:[[:space:]]*{' "$CONFIG_FILE" | grep -o '"[^"]*"' | tr -d '"' | grep -v mcpServers)
fi

if [ -z "$SERVERS" ]; then
    echo -e "${RED}❌ No MCP servers configured${NC}"
    exit 1
fi

echo "Found servers:"
for server in $SERVERS; do
    echo -e "  ${GREEN}•${NC} $server"
done

# Test each server
echo
echo -e "${BLUE}Testing server configurations...${NC}"

# Check GitHub token
if echo "$SERVERS" | grep -q "github"; then
    echo -n "GitHub server: "
    if command -v jq &> /dev/null; then
        TOKEN=$(jq -r '.mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN // empty' "$CONFIG_FILE")
    else
        TOKEN=$(grep -A5 '"github"' "$CONFIG_FILE" | grep GITHUB_PERSONAL_ACCESS_TOKEN | cut -d'"' -f4)
    fi
    
    if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
        # Test token
        if curl -s -H "Authorization: token $TOKEN" https://api.github.com/user | grep -q '"login"'; then
            echo -e "${GREEN}✅ Valid token${NC}"
        else
            echo -e "${RED}❌ Invalid token${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  No token configured${NC}"
    fi
fi

# Check filesystem path
if echo "$SERVERS" | grep -q "filesystem"; then
    echo -n "Filesystem server: "
    if command -v jq &> /dev/null; then
        FS_PATH=$(jq -r '.mcpServers.filesystem.args[-1] // empty' "$CONFIG_FILE")
    else
        FS_PATH=$(grep -A3 '"filesystem"' "$CONFIG_FILE" | tail -1 | cut -d'"' -f2)
    fi
    
    if [ -n "$FS_PATH" ] && [ -d "$FS_PATH" ]; then
        echo -e "${GREEN}✅ Valid path: $FS_PATH${NC}"
    else
        echo -e "${RED}❌ Invalid path: $FS_PATH${NC}"
    fi
fi

# Check memory server
if echo "$SERVERS" | grep -q "memory"; then
    echo -n "Memory server: "
    echo -e "${GREEN}✅ Configured${NC}"
fi

# Check NPM/NPX availability
echo
echo -e "${BLUE}Checking dependencies...${NC}"

if command -v npx &> /dev/null; then
    echo -e "${GREEN}✅ npx available${NC}"
else
    echo -e "${RED}❌ npx not found - Node.js required${NC}"
fi

# Summary
echo
echo -e "${BLUE}Summary${NC}"
echo "======="

ISSUES=0

# Count issues
if [ ! -f "$CONFIG_FILE" ]; then
    ((ISSUES++))
fi

if ! command -v npx &> /dev/null; then
    ((ISSUES++))
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ Configuration is valid!${NC}"
    echo
    echo "Next steps:"
    echo "1. Restart Claude Desktop"
    echo "2. Test with: 'List my GitHub repositories'"
else
    echo -e "${RED}❌ Found $ISSUES issue(s)${NC}"
    echo
    echo "Please run ./setup.sh to fix these issues"
fi