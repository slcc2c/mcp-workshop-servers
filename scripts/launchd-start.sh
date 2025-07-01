#!/bin/bash

# MCP Servers launchd startup script
# This script is called by launchd to start the MCP servers

# Set up logging
LOG_DIR="$HOME/Library/Logs/MCP"
mkdir -p "$LOG_DIR"

# Log startup
echo "[$(date)] Starting MCP servers via launchd..." >> "$LOG_DIR/startup.log"

# Export environment variables
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Add Homebrew paths for M1/M2/M3 Macs
if [ -d "/opt/homebrew" ]; then
    export PATH="/opt/homebrew/bin:$PATH"
fi

# Find Node.js
NODE_PATH=$(which node)
if [ -z "$NODE_PATH" ]; then
    echo "[$(date)] ERROR: Node.js not found in PATH" >> "$LOG_DIR/startup.log"
    exit 1
fi

echo "[$(date)] Using Node.js at: $NODE_PATH" >> "$LOG_DIR/startup.log"

# Change to MCP server directory
cd "$(dirname "$0")/.." || exit 1

# Check if package.json exists
if [ ! -f "package.json" ]; then
    echo "[$(date)] ERROR: package.json not found in $(pwd)" >> "$LOG_DIR/startup.log"
    exit 1
fi

# Source .env file if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "[$(date)] Loaded environment from .env" >> "$LOG_DIR/startup.log"
fi

# Start the servers
echo "[$(date)] Running npm run mcp:start" >> "$LOG_DIR/startup.log"
exec npm run mcp:start 2>&1 | tee -a "$LOG_DIR/server.log"