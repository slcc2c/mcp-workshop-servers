#!/bin/bash
# MCP Starter Kit - Basic Setup Script
# Sets up Claude Desktop with GitHub, Filesystem, and Memory MCP servers

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🤖 MCP Starter Kit - Quick Setup${NC}"
echo "=================================="
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

# Check Claude Desktop installation
CLAUDE_CONFIG_DIR=$(get_claude_config_dir)
if [ -z "$CLAUDE_CONFIG_DIR" ] || [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    echo -e "${RED}❌ Claude Desktop not found${NC}"
    echo "Please install Claude Desktop first:"
    echo "https://claude.ai/download"
    exit 1
fi

echo -e "${GREEN}✅ Found Claude Desktop${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found${NC}"
    echo "Please install Node.js 18 or later:"
    echo "https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}❌ Node.js version too old${NC}"
    echo "Please upgrade to Node.js 18 or later"
    exit 1
fi

echo -e "${GREEN}✅ Node.js $(node -v) installed${NC}"

# Get GitHub token
echo
echo -e "${YELLOW}GitHub Personal Access Token Setup${NC}"
echo "Create one at: https://github.com/settings/tokens"
echo "Required scopes: repo, read:org (for full functionality)"
echo
read -s -p "Enter your GitHub token: " GITHUB_TOKEN
echo
echo

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}❌ GitHub token is required${NC}"
    exit 1
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
cp -r "$(dirname "$0")/scripts/memory-helper.sh" scripts/ 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true

# Create backup
if [ -f "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" ]; then
    BACKUP_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.backup.$(date +%Y%m%d_%H%M%S).json"
    cp "$CLAUDE_CONFIG_DIR/claude_desktop_config.json" "$BACKUP_FILE"
    echo -e "${GREEN}✅ Backed up existing config to:${NC}"
    echo "   $BACKUP_FILE"
fi

# Create Claude Desktop configuration
echo
echo -e "${BLUE}Creating Claude Desktop configuration...${NC}"

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

# Create initial project context
echo
echo -e "${BLUE}Setting up initial project context...${NC}"
DEFAULT_PROJECT=$(basename "$PROJECT_DIR")
read -p "Project name (default: $DEFAULT_PROJECT): " PROJECT_NAME
PROJECT_NAME=${PROJECT_NAME:-$DEFAULT_PROJECT}

# Create example usage file
cat > "mcp-usage-examples.md" << EOF
# MCP Usage Examples for $PROJECT_NAME

## Setting Project Context
In Claude, say:
"I'm working on project:$PROJECT_NAME for session:$(date +%Y-%m-%d)"

## GitHub Examples
- "List my GitHub repositories"
- "Show issues in repo $PROJECT_NAME"
- "Create a PR in $PROJECT_NAME with title 'Add feature X'"

## Filesystem Examples
- "Read the README.md file"
- "Search for TODO comments in all JavaScript files"
- "Create a new file called config.json"

## Memory Examples
- "Remember for project:$PROJECT_NAME: We use React with TypeScript"
- "What do you know about project:$PROJECT_NAME?"
- "List all architectural decisions for project:$PROJECT_NAME"

## Memory Helper Script
\`\`\`bash
export MCP_PROJECT=$PROJECT_NAME
export MCP_SESSION=$(date +%Y-%m-%d)

# Store a memory
./scripts/memory-helper.sh store "Main language is TypeScript" preference

# Search memories
./scripts/memory-helper.sh search "typescript"
\`\`\`
EOF

# Show summary
echo
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo "=================="
echo
echo "Claude Desktop now has access to:"
echo -e "  ${BLUE}•${NC} GitHub (40+ operations)"
echo -e "  ${BLUE}•${NC} Filesystem (sandboxed to: $PROJECT_DIR)"
echo -e "  ${BLUE}•${NC} Memory (with project segregation)"
echo
echo -e "${YELLOW}⚠️  IMPORTANT: Restart Claude Desktop now${NC}"
echo
echo "Quick test commands to try in Claude:"
echo '  1. "List my GitHub repositories"'
echo '  2. "What files are in my project directory?"'
echo "  3. \"Remember for project:$PROJECT_NAME: This is my test project\""
echo
echo "See 'mcp-usage-examples.md' for more examples"
echo
echo -e "${GREEN}Happy coding with Claude! 🚀${NC}"