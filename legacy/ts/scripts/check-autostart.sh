#!/bin/bash

# Script to check MCP servers auto-start status

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

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

GATEWAY_PORT=$(GATEWAY_CONFIG="$PROJECT_DIR/config/gateway.json" node -e 'const fs=require("fs");try{const c=JSON.parse(fs.readFileSync(process.env.GATEWAY_CONFIG,"utf8")); console.log(c.gateway?.port || 3000)}catch{console.log(3000)}' 2>/dev/null)
echo
echo "Gateway health:"
if curl -fsS --max-time 2 "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} http://localhost:${GATEWAY_PORT}/health"
else
    echo -e "  ${RED}✗${NC} http://localhost:${GATEWAY_PORT}/health"
fi

# Show only the launchd-managed process tree. There may be many unrelated MCP
# servers from active Codex/Claude sessions, so a broad process grep is noisy.
echo
echo "Managed process tree:"
if [ -n "$PID" ] && [ "$PID" != "-" ]; then
    PIDS="$PID"
    CHILDREN=$(pgrep -P "$PID" 2>/dev/null | tr '\n' ' ')
    GRANDCHILDREN=""
    for child in $CHILDREN; do
        GRANDCHILDREN="$GRANDCHILDREN $(pgrep -P "$child" 2>/dev/null | tr '\n' ' ')"
    done
    PIDS="$PIDS $CHILDREN $GRANDCHILDREN"
    ps -o pid,ppid,%cpu,%mem,etime,command -p $PIDS 2>/dev/null | sed 's/^/  /'
else
    echo "  (not running)"
fi

echo
echo "Commands:"
echo "  • View logs:     tail -f ~/Library/Logs/MCP/server.log"
echo "  • Stop servers:  launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"
echo "  • Start servers: launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist"
