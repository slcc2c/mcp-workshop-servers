#!/bin/bash
# Test GitHub token and API access

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

echo -e "${BLUE}🔧 Testing GitHub Integration${NC}"
echo "============================="
echo

# Get token from config
CLAUDE_CONFIG_DIR=$(get_claude_config_dir)
CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Claude Desktop config not found${NC}"
    exit 1
fi

# Extract token
if command -v jq &> /dev/null; then
    TOKEN=$(jq -r '.mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN // empty' "$CONFIG_FILE")
else
    TOKEN=$(grep -A5 '"github"' "$CONFIG_FILE" | grep GITHUB_PERSONAL_ACCESS_TOKEN | cut -d'"' -f4)
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo -e "${RED}❌ No GitHub token found in config${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Found GitHub token${NC}"

# Test user endpoint
echo
echo -e "${BLUE}Testing user authentication...${NC}"
USER_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" https://api.github.com/user)

if echo "$USER_RESPONSE" | grep -q '"login"'; then
    USERNAME=$(echo "$USER_RESPONSE" | grep -o '"login":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✅ Authenticated as: $USERNAME${NC}"
else
    echo -e "${RED}❌ Authentication failed${NC}"
    echo "$USER_RESPONSE" | head -n 3
    exit 1
fi

# Check rate limit
echo
echo -e "${BLUE}Checking API rate limit...${NC}"
RATE_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" https://api.github.com/rate_limit)
RATE_LIMIT=$(echo "$RATE_RESPONSE" | grep -o '"limit":[0-9]*' | head -1 | cut -d: -f2)
RATE_REMAINING=$(echo "$RATE_RESPONSE" | grep -o '"remaining":[0-9]*' | head -1 | cut -d: -f2)

if [ -n "$RATE_LIMIT" ]; then
    echo -e "${GREEN}✅ Rate limit: $RATE_REMAINING/$RATE_LIMIT requests remaining${NC}"
else
    echo -e "${YELLOW}⚠️  Could not check rate limit${NC}"
fi

# Test repository access
echo
echo -e "${BLUE}Testing repository access...${NC}"
REPOS_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" "https://api.github.com/user/repos?per_page=5")

if echo "$REPOS_RESPONSE" | grep -q '"full_name"'; then
    REPO_COUNT=$(echo "$REPOS_RESPONSE" | grep -c '"full_name"')
    echo -e "${GREEN}✅ Can access repositories (found at least $REPO_COUNT)${NC}"
    
    # Show first repo
    FIRST_REPO=$(echo "$REPOS_RESPONSE" | grep -o '"full_name":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -n "$FIRST_REPO" ]; then
        echo "   Example: $FIRST_REPO"
    fi
else
    echo -e "${YELLOW}⚠️  No repositories found or limited access${NC}"
fi

# Check token scopes
echo
echo -e "${BLUE}Checking token permissions...${NC}"
SCOPES_HEADER=$(curl -s -I -H "Authorization: token $TOKEN" https://api.github.com/user | grep -i "x-oauth-scopes:")

if [ -n "$SCOPES_HEADER" ]; then
    SCOPES=$(echo "$SCOPES_HEADER" | cut -d: -f2- | tr -d '\r\n' | xargs)
    if [ -n "$SCOPES" ]; then
        echo -e "${GREEN}✅ Token scopes: $SCOPES${NC}"
    else
        echo -e "${YELLOW}⚠️  Token has no specific scopes (classic token with full access)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Could not determine token scopes${NC}"
fi

# Test creating an issue (dry run)
echo
echo -e "${BLUE}Testing issue creation capability...${NC}"
if echo "$SCOPES" | grep -q "repo\|public_repo" || [ -z "$SCOPES" ]; then
    echo -e "${GREEN}✅ Can create issues${NC}"
else
    echo -e "${YELLOW}⚠️  May not be able to create issues (needs 'repo' scope)${NC}"
fi

# Summary
echo
echo -e "${BLUE}Summary${NC}"
echo "======="
echo -e "${GREEN}✅ GitHub integration is working!${NC}"
echo
echo "You can now use these commands in Claude:"
echo '  • "List my GitHub repositories"'
echo '  • "Show recent issues in [repo-name]"'
echo '  • "Create a new issue in [repo-name]"'
echo '  • "Search for pull requests mentioning [topic]"'
echo
echo -e "${YELLOW}Note:${NC} Some operations require specific token scopes:"
echo "  • 'repo' - Full repository access"
echo "  • 'read:org' - Read organization data"
echo "  • 'workflow' - GitHub Actions access"