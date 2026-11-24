#!/bin/bash

# List all attached MCP projects

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECTS_DIR="$HOME/.mcp/projects"
CURRENT_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

echo -e "${BLUE}📋 MCP Attached Projects${NC}"
echo ""

if [ ! -d "$PROJECTS_DIR" ]; then
    echo "No projects attached yet."
    echo "Use: ./scripts/attach-project.sh /path/to/project"
    exit 0
fi

# Get current project by comparing configs
CURRENT_PROJECT=""
if [ -f "$CURRENT_CONFIG" ]; then
    for project in "$PROJECTS_DIR"/*; do
        if [ -d "$project" ] && [ -f "$project/claude_desktop_config.json" ]; then
            if diff -q "$CURRENT_CONFIG" "$project/claude_desktop_config.json" >/dev/null 2>&1; then
                CURRENT_PROJECT=$(basename "$project")
                break
            fi
        fi
    done
fi

# List all projects
for project_dir in "$PROJECTS_DIR"/*; do
    if [ -d "$project_dir" ]; then
        project_name=$(basename "$project_dir")
        
        # Read project info if available
        if [ -f "$project_dir/project-info.json" ]; then
            project_path=$(jq -r '.path // "Unknown"' "$project_dir/project-info.json" 2>/dev/null || echo "Unknown")
            project_type=$(jq -r '.type // "custom"' "$project_dir/project-info.json" 2>/dev/null || echo "custom")
        else
            project_path="Unknown"
            project_type="custom"
        fi
        
        # Display project
        if [ "$project_name" = "$CURRENT_PROJECT" ]; then
            echo -e "${GREEN}● $project_name${NC} (active)"
        else
            echo -e "  $project_name"
        fi
        echo "    Path: $project_path"
        echo "    Type: $project_type"
        echo ""
    fi
done

echo ""
echo "Commands:"
echo "  Switch project:  ./scripts/switch-project.sh <project-name>"
echo "  Attach project:  ./scripts/attach-project.sh /path/to/project"