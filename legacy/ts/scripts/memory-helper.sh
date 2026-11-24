#!/bin/bash

# Memory MCP Helper Script - Implements project/session segregation via tags
# Usage: ./memory-helper.sh <command> [options]

set -e

# Configuration
PROJECT_NAME="${MCP_PROJECT:-mcp-server}"
SESSION_DATE="${MCP_SESSION:-$(date +%Y-%m-%d)}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Helper function to add standard tags
add_standard_tags() {
    local tags="$1"
    echo "project:${PROJECT_NAME},session:${SESSION_DATE}${tags:+,$tags}"
}

# Store memory with project/session tags
store_memory() {
    local content="$1"
    local type="${2:-context}"
    local additional_tags="$3"
    
    local tags=$(add_standard_tags "$additional_tags")
    
    echo -e "${BLUE}Storing memory:${NC}"
    echo "  Content: $content"
    echo "  Type: $type"
    echo "  Tags: $tags"
    echo ""
    
    # This would be called via MCP in Claude
    echo "In Claude, use:"
    echo "memory_store(\"$content\", \"$type\", [$(echo $tags | sed 's/,/", "/g' | sed 's/^/"/;s/$/"/')])"
}

# Search memories for current project/session
search_project_memories() {
    local query="$1"
    local type="$2"
    
    echo -e "${BLUE}Searching project memories:${NC}"
    echo "  Project: $PROJECT_NAME"
    echo "  Session: $SESSION_DATE"
    echo "  Query: $query"
    echo ""
    
    echo "In Claude, use:"
    echo "memory_search(\"$query\", \"$type\", [\"project:${PROJECT_NAME}\"])"
}

# List all memories for current project
list_project_memories() {
    echo -e "${BLUE}Listing memories for project: ${PROJECT_NAME}${NC}"
    echo ""
    
    echo "In Claude, use:"
    echo "memory_search(\"\", null, [\"project:${PROJECT_NAME}\"])"
}

# Create a context memory for the current session
create_session_context() {
    local description="$1"
    
    local content="Session Context: ${description}"
    local tags="context,session-start"
    
    store_memory "$content" "context" "$tags"
}

# Show current configuration
show_config() {
    echo -e "${GREEN}Memory Helper Configuration:${NC}"
    echo "  Project: $PROJECT_NAME"
    echo "  Session: $SESSION_DATE"
    echo ""
    echo "To change:"
    echo "  export MCP_PROJECT=your-project-name"
    echo "  export MCP_SESSION=2025-06-30"
}

# Main command handler
case "$1" in
    store)
        store_memory "$2" "$3" "$4"
        ;;
    search)
        search_project_memories "$2" "$3"
        ;;
    list)
        list_project_memories
        ;;
    context)
        create_session_context "$2"
        ;;
    config)
        show_config
        ;;
    *)
        echo "Memory MCP Helper - Project/Session Segregation"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  store <content> [type] [tags]    Store memory with auto-tags"
        echo "  search <query> [type]            Search within project"
        echo "  list                             List all project memories"
        echo "  context <description>            Create session context"
        echo "  config                           Show current configuration"
        echo ""
        echo "Environment Variables:"
        echo "  MCP_PROJECT    Project name (default: mcp-server)"
        echo "  MCP_SESSION    Session date (default: today)"
        echo ""
        echo "Examples:"
        echo "  $0 store \"User prefers TypeScript\" preference \"language,setup\""
        echo "  $0 search \"typescript\""
        echo "  $0 context \"Setting up 1Password integration\""
        ;;
esac