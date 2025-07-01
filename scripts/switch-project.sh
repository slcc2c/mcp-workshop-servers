#!/bin/bash

# MCP Project Switcher
# Quickly switch between attached projects

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"
PROJECTS_DIR="$HOME/.mcp/projects"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <project-name>"
    echo ""
    echo "Available projects:"
    if [ -d "$PROJECTS_DIR" ]; then
        for project in "$PROJECTS_DIR"/*; do
            if [ -d "$project" ]; then
                echo "  - $(basename "$project")"
            fi
        done
    else
        echo "  No projects found"
    fi
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_DIR="$PROJECTS_DIR/$PROJECT_NAME"

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}✗${NC} Project not found: $PROJECT_NAME"
    exit 1
fi

if [ -f "$PROJECT_DIR/claude_desktop_config.json" ]; then
    cp "$PROJECT_DIR/claude_desktop_config.json" "$CONFIG_FILE"
    echo -e "${GREEN}✓${NC} Switched to project: $PROJECT_NAME"
    echo "Please restart Claude Desktop to apply changes."
else
    echo -e "${RED}✗${NC} Configuration not found for project: $PROJECT_NAME"
    exit 1
fi