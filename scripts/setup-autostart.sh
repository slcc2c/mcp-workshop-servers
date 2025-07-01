#!/bin/bash

# Setup script to enable MCP servers auto-start on macOS

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}MCP Servers Auto-start Setup${NC}"
echo "================================"
echo

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}Error: This script is for macOS only${NC}"
    exit 1
fi

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check if launchd plist exists
PLIST_FILE="$PROJECT_DIR/com.mcp-workshop.servers.plist"
if [ ! -f "$PLIST_FILE" ]; then
    echo -e "${RED}Error: Plist file not found at $PLIST_FILE${NC}"
    exit 1
fi

# Create logs directory
LOG_DIR="$HOME/Library/Logs/MCP"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✓${NC} Created log directory: $LOG_DIR"

# Check if already installed
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
INSTALLED_PLIST="$LAUNCHD_DIR/com.mcp-workshop.servers.plist"

if [ -f "$INSTALLED_PLIST" ]; then
    echo -e "${YELLOW}Warning: Auto-start is already configured${NC}"
    read -p "Do you want to reinstall? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled"
        exit 0
    fi
    
    # Unload existing service
    launchctl unload "$INSTALLED_PLIST" 2>/dev/null || true
    rm -f "$INSTALLED_PLIST"
fi

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$LAUNCHD_DIR"

# Copy plist file
cp "$PLIST_FILE" "$INSTALLED_PLIST"
echo -e "${GREEN}✓${NC} Installed launch agent configuration"

# Load the service
launchctl load -w "$INSTALLED_PLIST"
echo -e "${GREEN}✓${NC} Loaded launch agent"

# Check if service is running
sleep 2
if launchctl list | grep -q "com.mcp-workshop.servers"; then
    echo -e "${GREEN}✓${NC} MCP servers are now running"
else
    echo -e "${YELLOW}Warning: Service may not have started properly${NC}"
    echo "Check logs at: $LOG_DIR"
fi

echo
echo -e "${GREEN}✅ Auto-start setup complete!${NC}"
echo
echo "The MCP servers will now:"
echo "  • Start automatically when you log in"
echo "  • Restart if they crash"
echo "  • Log output to: $LOG_DIR"
echo
echo "Useful commands:"
echo "  • Check status:  launchctl list | grep mcp"
echo "  • View logs:     tail -f ~/Library/Logs/MCP/server.log"
echo "  • Stop servers:  launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"
echo "  • Start servers: launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"
echo "  • Remove:        npm run autostart:remove"