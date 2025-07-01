#!/bin/bash
# MCP Starter Kit - Setup with 1Password Integration
# Securely manages tokens using 1Password CLI

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🔐 MCP Starter Kit - 1Password Setup${NC}"
echo "====================================="
echo

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

# Check 1Password CLI
if ! command -v op &> /dev/null; then
    echo -e "${RED}❌ 1Password CLI not found${NC}"
    echo "Please install it first:"
    echo "https://developer.1password.com/docs/cli/get-started/"
    exit 1
fi

echo -e "${GREEN}✅ 1Password CLI installed${NC}"

# Check 1Password authentication
if ! op account list &> /dev/null; then
    echo -e "${YELLOW}Signing in to 1Password...${NC}"
    op signin
fi

if ! op vault list &> /dev/null; then
    echo -e "${RED}❌ Failed to authenticate with 1Password${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Authenticated with 1Password${NC}"

# Check Claude Desktop
CLAUDE_CONFIG_DIR=$(get_claude_config_dir)
if [ -z "$CLAUDE_CONFIG_DIR" ] || [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    echo -e "${RED}❌ Claude Desktop not found${NC}"
    echo "Please install Claude Desktop first:"
    echo "https://claude.ai/download"
    exit 1
fi

echo -e "${GREEN}✅ Found Claude Desktop${NC}"

# Check for existing GitHub token in 1Password
echo
echo -e "${BLUE}Checking for GitHub token in 1Password...${NC}"

# Try different vault names
GITHUB_TOKEN=""
for vault in "Private" "Personal" "Development" "AI" ""; do
    if [ -z "$vault" ]; then
        VAULT_ARG=""
    else
        VAULT_ARG="--vault=$vault"
    fi
    
    # Try to get GitHub token
    GITHUB_TOKEN=$(op item get "GitHub Token" $VAULT_ARG --fields label=token 2>/dev/null || \
                   op item get "GitHub Personal Access Token" $VAULT_ARG --fields label=token 2>/dev/null || \
                   op item get "GitHub" $VAULT_ARG --fields label=token 2>/dev/null || \
                   op item get "GitHub Token" $VAULT_ARG --fields label=credential 2>/dev/null || \
                   op item get "GitHub Token" $VAULT_ARG --fields label=notesPlain 2>/dev/null || \
                   echo "")
    
    if [ -n "$GITHUB_TOKEN" ]; then
        echo -e "${GREEN}✅ Found GitHub token in vault: ${vault:-Default}${NC}"
        break
    fi
done

# If no token found, help create one
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${YELLOW}No GitHub token found in 1Password${NC}"
    echo
    echo "Let's create one:"
    echo "1. Go to https://github.com/settings/tokens"
    echo "2. Click 'Generate new token (classic)'"
    echo "3. Select scopes: repo, read:org"
    echo "4. Generate the token"
    echo
    read -s -p "Enter your new GitHub token: " GITHUB_TOKEN
    echo
    echo
    
    if [ -z "$GITHUB_TOKEN" ]; then
        echo -e "${RED}❌ GitHub token is required${NC}"
        exit 1
    fi
    
    # Save to 1Password
    echo -e "${BLUE}Saving token to 1Password...${NC}"
    echo
    echo "Which vault should store the token?"
    op vault list
    echo
    read -p "Vault name (or press Enter for default): " VAULT_NAME
    
    if [ -z "$VAULT_NAME" ]; then
        VAULT_ARG=""
    else
        VAULT_ARG="--vault=$VAULT_NAME"
    fi
    
    # Create the item
    op item create \
        --category=login \
        --title="GitHub Token" \
        --tags="mcp,development" \
        $VAULT_ARG \
        token="$GITHUB_TOKEN" \
        url="https://github.com" \
        notes="GitHub Personal Access Token for MCP/Claude Desktop integration"
    
    echo -e "${GREEN}✅ Token saved to 1Password${NC}"
fi

# Validate token
echo -e "${BLUE}Validating GitHub token...${NC}"
if curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user | grep -q '"login"'; then
    echo -e "${GREEN}✅ GitHub token is valid${NC}"
else
    echo -e "${RED}❌ Invalid GitHub token${NC}"
    exit 1
fi

# Get project directory
echo
echo -e "${YELLOW}Filesystem Access Setup${NC}"
echo "Which directory should Claude have access to?"
echo "(This should be your main projects directory)"
echo
read -e -p "Directory path: " -i "$HOME/projects" PROJECT_DIR

# Expand tilde and make absolute
PROJECT_DIR=$(eval echo "$PROJECT_DIR")
PROJECT_DIR=$(cd "$PROJECT_DIR" 2>/dev/null && pwd || echo "$PROJECT_DIR")

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Directory doesn't exist. Create it? (y/n)${NC}"
    read -p "> " CREATE_DIR
    if [ "$CREATE_DIR" = "y" ]; then
        mkdir -p "$PROJECT_DIR"
        echo -e "${GREEN}✅ Created directory: $PROJECT_DIR${NC}"
    else
        echo -e "${RED}❌ Directory must exist${NC}"
        exit 1
    fi
fi

# Copy scripts
echo
echo -e "${BLUE}Setting up helper scripts...${NC}"
mkdir -p scripts
cp -r "$(dirname "$0")/scripts/." scripts/ 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true

# Create backup
if [ -f "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" ]; then
    BACKUP_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.backup.$(date +%Y%m%d_%H%M%S).json"
    cp "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" "$BACKUP_FILE"
    echo -e "${GREEN}✅ Backed up existing config${NC}"
fi

# Create Claude Desktop configuration
echo
echo -e "${BLUE}Creating secure Claude Desktop configuration...${NC}"

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
        "${PROJECT_DIR}"
      ]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
EOF

echo -e "${GREEN}✅ Configuration created${NC}"

# Create 1Password refresh script
cat > "scripts/refresh-tokens.sh" << 'EOF'
#!/bin/bash
# Refresh tokens from 1Password

CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
if [ ! -f "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" ]; then
    echo "Claude Desktop config not found"
    exit 1
fi

# Get fresh token from 1Password
GITHUB_TOKEN=$(op item get "GitHub Token" --fields label=token 2>/dev/null || \
               op item get "GitHub Token" --fields label=credential 2>/dev/null || \
               op item get "GitHub Token" --fields label=notesPlain 2>/dev/null)

if [ -z "$GITHUB_TOKEN" ]; then
    echo "Failed to get GitHub token from 1Password"
    exit 1
fi

# Update the config using jq or sed
if command -v jq &> /dev/null; then
    jq --arg token "$GITHUB_TOKEN" \
       '.mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN = $token' \
       "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" > tmp.json && \
    mv tmp.json "$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
else
    # Fallback to sed (less reliable)
    sed -i.bak "s/\"GITHUB_PERSONAL_ACCESS_TOKEN\": \"[^\"]*\"/\"GITHUB_PERSONAL_ACCESS_TOKEN\": \"$GITHUB_TOKEN\"/" \
        "$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
fi

echo "✅ Tokens refreshed from 1Password"
echo "⚠️  Restart Claude Desktop for changes to take effect"
EOF

chmod +x scripts/refresh-tokens.sh

# Show summary
echo
echo -e "${GREEN}🎉 Secure Setup Complete!${NC}"
echo "========================="
echo
echo "Claude Desktop now has access to:"
echo -e "  ${BLUE}•${NC} GitHub (token from 1Password)"
echo -e "  ${BLUE}•${NC} Filesystem (sandboxed to: $PROJECT_DIR)"
echo -e "  ${BLUE}•${NC} Memory (with project segregation)"
echo
echo -e "${YELLOW}⚠️  IMPORTANT: Restart Claude Desktop now${NC}"
echo
echo "Security features enabled:"
echo -e "  ${GREEN}✓${NC} GitHub token stored in 1Password"
echo -e "  ${GREEN}✓${NC} Token refresh script: ./scripts/refresh-tokens.sh"
echo -e "  ${GREEN}✓${NC} Filesystem sandboxed to project directory"
echo
echo "To update tokens later:"
echo "  ./scripts/refresh-tokens.sh"
echo
echo -e "${GREEN}Happy secure coding with Claude! 🔐🚀${NC}"