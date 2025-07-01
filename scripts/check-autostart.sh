#!/bin/bash

# Script to check MCP servers auto-start status

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}MCP Servers Auto-start Status${NC}"
echo "==============================="
echo

# Check if launchd plist is installed
INSTALLED_PLIST="$HOME/Library/LaunchAgents/com.mcp-workshop.servers.plist"

if [ -f "$INSTALLED_PLIST" ]; then
    echo -e "${GREEN}✓${NC} Auto-start is configured"
    echo "   Configuration: $INSTALLED_PLIST"
    
    # Check if service is loaded
    if launchctl list | grep -q "com.mcp-workshop.servers"; then
        echo -e "${GREEN}✓${NC} Service is loaded"
        
        # Get PID if running
        PID=$(launchctl list | grep "com.mcp-workshop.servers" | awk '{print $1}')
        if [ "$PID" != "-" ]; then
            echo -e "${GREEN}✓${NC} MCP servers are running (PID: $PID)"
            
            # Show process info
            echo
            echo "Process information:"
            ps -p "$PID" -o pid,ppid,%cpu,%mem,start,time,command | head -n 2
        else
            echo -e "${RED}✗${NC} MCP servers are not running"
        fi
    else
        echo -e "${RED}✗${NC} Service is not loaded"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Auto-start is not configured"
    echo "   Run 'npm run autostart:setup' to enable"
fi

# Check log files
LOG_DIR="$HOME/Library/Logs/MCP"
if [ -d "$LOG_DIR" ]; then
    echo
    echo "Log files:"
    for log in "$LOG_DIR"/*.log; do
        if [ -f "$log" ]; then
            SIZE=$(du -h "$log" | cut -f1)
            echo "  • $(basename "$log") ($SIZE)"
        fi
    done
    
    # Show recent errors if any
    ERROR_LOG="$LOG_DIR/mcp-servers.err.log"
    if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
        echo
        echo -e "${YELLOW}Recent errors:${NC}"
        tail -n 5 "$ERROR_LOG" | sed 's/^/  /'
    fi
fi

# Show running MCP-related Node processes
echo
echo "MCP-related processes:"
ps aux | grep -E "node.*mcp|npm.*mcp" | grep -v grep | head -n 5 | while read line; do
    echo "  • $line" | cut -c1-120
done || echo "  (none found)"

echo
echo "Commands:"
echo "  • View logs:     tail -f ~/Library/Logs/MCP/server.log"
echo "  • Stop servers:  launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"
echo "  • Start servers: launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"