#!/bin/bash

# Script to remove MCP servers auto-start on macOS

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}MCP Servers Auto-start Removal${NC}"
echo "================================="
echo

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}Error: This script is for macOS only${NC}"
    exit 1
fi

# Check if installed
INSTALLED_PLIST="$HOME/Library/LaunchAgents/com.mcp-workshop.servers.plist"

if [ ! -f "$INSTALLED_PLIST" ]; then
    echo -e "${YELLOW}Auto-start is not configured${NC}"
    exit 0
fi

echo "This will remove the MCP servers auto-start configuration."
read -p "Are you sure? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

# Unload the service
echo "Stopping MCP servers..."
launchctl unload "$INSTALLED_PLIST" 2>/dev/null || true
echo -e "${GREEN}✓${NC} Stopped launch agent"

# Remove the plist file
rm -f "$INSTALLED_PLIST"
echo -e "${GREEN}✓${NC} Removed launch agent configuration"

# Check if we should remove logs
LOG_DIR="$HOME/Library/Logs/MCP"
if [ -d "$LOG_DIR" ]; then
    echo
    read -p "Remove log files? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$LOG_DIR"
        echo -e "${GREEN}✓${NC} Removed log files"
    else
        echo "Log files kept at: $LOG_DIR"
    fi
fi

echo
echo -e "${GREEN}✅ Auto-start has been removed${NC}"
echo
echo "The MCP servers will no longer start automatically."
echo "You can still start them manually with: npm run mcp:start"