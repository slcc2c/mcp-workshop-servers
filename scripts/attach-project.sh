#!/bin/bash

# MCP Project Attachment Script
# Easily attach your project to Claude Desktop with MCP servers

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
MCP_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

# Default values
PROJECT_PATH=""
PROJECT_NAME=""
TEMPLATE=""
WITH_DB=""
WITH_DOCKER=false
WITH_K8S=false
WITH_SIMULATOR=false

# Function to print colored output
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Show usage
usage() {
    echo "Usage: $0 <project-path> [options]"
    echo ""
    echo "Options:"
    echo "  --template=<template>    Use a project template (web-app, api, mobile, data-science)"
    echo "  --with-db=<db>          Include database server (postgresql, mongodb, redis)"
    echo "  --with-docker           Include Docker server"
    echo "  --with-k8s              Include Kubernetes server"
    echo "  --with-simulator        Include iOS simulator support"
    echo "  --name=<name>           Override project name"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/my-project"
    echo "  $0 /path/to/my-app --template=web-app --with-db=postgresql"
    echo "  $0 /path/to/ios-app --template=ios --with-simulator"
}

# Parse command line arguments
parse_args() {
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi

    PROJECT_PATH="$1"
    shift

    while [[ $# -gt 0 ]]; do
        case $1 in
            --template=*)
                TEMPLATE="${1#*=}"
                shift
                ;;
            --with-db=*)
                WITH_DB="${1#*=}"
                shift
                ;;
            --with-docker)
                WITH_DOCKER=true
                shift
                ;;
            --with-k8s)
                WITH_K8S=true
                shift
                ;;
            --with-simulator)
                WITH_SIMULATOR=true
                shift
                ;;
            --name=*)
                PROJECT_NAME="${1#*=}"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# Validate project path
validate_project() {
    if [ ! -d "$PROJECT_PATH" ]; then
        print_error "Project path does not exist: $PROJECT_PATH"
        exit 1
    fi

    # Get absolute path
    PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"
    
    # Derive project name if not provided
    if [ -z "$PROJECT_NAME" ]; then
        PROJECT_NAME="$(basename "$PROJECT_PATH")"
    fi

    print_success "Project validated: $PROJECT_NAME at $PROJECT_PATH"
}

# Create Claude Desktop config directory if it doesn't exist
ensure_config_dir() {
    if [ ! -d "$CONFIG_DIR" ]; then
        print_step "Creating Claude Desktop config directory..."
        mkdir -p "$CONFIG_DIR"
    fi
}

# Backup existing configuration
backup_config() {
    if [ -f "$CONFIG_FILE" ]; then
        BACKUP_FILE="$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        print_step "Backing up existing configuration..."
        cp "$CONFIG_FILE" "$BACKUP_FILE"
        print_success "Backup saved to: $BACKUP_FILE"
    fi
}

# Generate MCP server configuration
generate_config() {
    print_step "Generating MCP server configuration..."

    # Start with base configuration
    cat > "$CONFIG_FILE" << EOF
{
  "mcpServers": {
    "mcp-filesystem-${PROJECT_NAME}": {
      "command": "npx",
      "args": [
        "-y", 
        "@modelcontextprotocol/server-filesystem",
        "${PROJECT_PATH}"
      ]
    },
    "mcp-memory": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/memory/index.js"],
      "env": {
        "MEMORY_PROJECT": "${PROJECT_NAME}",
        "MEMORY_STORAGE_PATH": "${HOME}/.mcp/memory"
      }
    },
    "mcp-github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "env:GITHUB_TOKEN"
      }
    }
EOF

    # Add Docker server if requested
    if [ "$WITH_DOCKER" = true ]; then
        cat >> "$CONFIG_FILE" << EOF
,
    "mcp-docker": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/docker/index.js"],
      "env": {
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "DOCKER_RESOURCE_LIMITS": "true"
      }
    }
EOF
    fi

    # Add database server if requested
    case "$WITH_DB" in
        postgresql)
            cat >> "$CONFIG_FILE" << EOF
,
    "mcp-postgresql": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/postgresql/index.js"],
      "env": {
        "POSTGRES_URL": "env:POSTGRES_URL",
        "PG_MAX_CONNECTIONS": "10"
      }
    }
EOF
            ;;
        mongodb)
            cat >> "$CONFIG_FILE" << EOF
,
    "mcp-mongodb": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/mongodb/index.js"],
      "env": {
        "MONGODB_URL": "env:MONGODB_URL",
        "MONGODB_DATABASE": "${PROJECT_NAME}_db"
      }
    }
EOF
            ;;
        redis)
            cat >> "$CONFIG_FILE" << EOF
,
    "mcp-redis": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/redis/index.js"],
      "env": {
        "REDIS_URL": "env:REDIS_URL"
      }
    }
EOF
            ;;
    esac

    # Add Kubernetes server if requested
    if [ "$WITH_K8S" = true ]; then
        cat >> "$CONFIG_FILE" << EOF
,
    "mcp-kubernetes": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/kubernetes/index.js"],
      "env": {
        "KUBECONFIG": "${HOME}/.kube/config"
      }
    }
EOF
    fi

    # Add XcodeBuild server if iOS template or simulator requested
    if [ "$TEMPLATE" = "ios" ] || [ "$TEMPLATE" = "mobile" ] || [ "$WITH_SIMULATOR" = true ]; then
        cat >> "$CONFIG_FILE" << EOF
,
    "mcp-xcodebuild": {
      "command": "node",
      "args": ["${MCP_DIR}/dist/servers/xcodebuild/index.js"],
      "env": {
        "XCODE_DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer",
        "NODE_ENV": "production"
      }
    }
EOF
    fi

    # Close the configuration
    cat >> "$CONFIG_FILE" << EOF

  }
}
EOF

    print_success "Configuration generated"
}

# Create project-specific environment file
create_project_env() {
    print_step "Creating project environment file..."
    
    ENV_FILE="${PROJECT_PATH}/.mcp-env"
    
    cat > "$ENV_FILE" << EOF
# MCP Environment Configuration for ${PROJECT_NAME}
# Generated on $(date)

PROJECT_NAME=${PROJECT_NAME}
PROJECT_PATH=${PROJECT_PATH}
PROJECT_TYPE=${TEMPLATE:-custom}

# Add your project-specific environment variables below:
# DATABASE_URL=postgresql://localhost/${PROJECT_NAME}
# API_ENDPOINT=http://localhost:3000
# GITHUB_REPO=username/repo
EOF

    print_success "Created .mcp-env file in project directory"
}

# Apply project template
apply_template() {
    if [ -z "$TEMPLATE" ]; then
        return
    fi

    print_step "Applying $TEMPLATE template..."

    case "$TEMPLATE" in
        web-app)
            # Web app specific setup
            echo "# Web App Configuration" >> "${PROJECT_PATH}/.mcp-env"
            echo "BUILD_COMMAND=npm run build" >> "${PROJECT_PATH}/.mcp-env"
            echo "DEV_COMMAND=npm run dev" >> "${PROJECT_PATH}/.mcp-env"
            echo "TEST_COMMAND=npm test" >> "${PROJECT_PATH}/.mcp-env"
            ;;
        api)
            # API specific setup
            echo "# API Configuration" >> "${PROJECT_PATH}/.mcp-env"
            echo "API_PORT=3000" >> "${PROJECT_PATH}/.mcp-env"
            echo "NODE_ENV=development" >> "${PROJECT_PATH}/.mcp-env"
            ;;
        mobile)
            # Mobile app specific setup
            echo "# Mobile App Configuration" >> "${PROJECT_PATH}/.mcp-env"
            echo "PLATFORM=ios,android" >> "${PROJECT_PATH}/.mcp-env"
            echo "BUILD_COMMAND=npm run build:mobile" >> "${PROJECT_PATH}/.mcp-env"
            ;;
        data-science)
            # Data science specific setup
            echo "# Data Science Configuration" >> "${PROJECT_PATH}/.mcp-env"
            echo "JUPYTER_NOTEBOOK_DIR=${PROJECT_PATH}/notebooks" >> "${PROJECT_PATH}/.mcp-env"
            echo "DATA_DIR=${PROJECT_PATH}/data" >> "${PROJECT_PATH}/.mcp-env"
            ;;
    esac

    print_success "Applied $TEMPLATE template"
}

# Create quick access scripts
create_shortcuts() {
    print_step "Creating project shortcuts..."

    # Create shortcuts directory
    SHORTCUTS_DIR="${HOME}/.mcp/projects/${PROJECT_NAME}"
    mkdir -p "$SHORTCUTS_DIR"

    # Create switch script
    cat > "$SHORTCUTS_DIR/activate.sh" << EOF
#!/bin/bash
# Activate ${PROJECT_NAME} project in Claude Desktop

echo "Activating project: ${PROJECT_NAME}"
echo "Project path: ${PROJECT_PATH}"

# Copy project-specific config
cp "${SHORTCUTS_DIR}/claude_desktop_config.json" "${CONFIG_FILE}"

echo "✓ Project activated. Please restart Claude Desktop."
EOF

    chmod +x "$SHORTCUTS_DIR/activate.sh"

    # Save a copy of the config
    cp "$CONFIG_FILE" "$SHORTCUTS_DIR/claude_desktop_config.json"

    print_success "Created project shortcuts in ~/.mcp/projects/${PROJECT_NAME}"
}

# Display next steps
show_next_steps() {
    echo ""
    echo -e "${GREEN}✨ Project attached successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Restart Claude Desktop"
    echo "2. Test your setup with these commands in Claude:"
    echo "   - 'List files in my project'"
    echo "   - 'Remember that this project is ${PROJECT_NAME}'"
    echo ""
    
    if [ -n "$WITH_DB" ]; then
        echo "3. Set up your database connection:"
        case "$WITH_DB" in
            postgresql)
                echo "   export POSTGRES_URL='postgresql://user:pass@localhost/${PROJECT_NAME}'"
                ;;
            mongodb)
                echo "   export MONGODB_URL='mongodb://localhost:27017/${PROJECT_NAME}'"
                ;;
            redis)
                echo "   export REDIS_URL='redis://localhost:6379'"
                ;;
        esac
    fi
    
    echo ""
    echo "Quick tips:"
    echo "- Switch to this project: ~/.mcp/projects/${PROJECT_NAME}/activate.sh"
    echo "- Edit environment: ${PROJECT_PATH}/.mcp-env"
    echo "- View configuration: cat '$CONFIG_FILE'"
}

# Main execution
main() {
    echo -e "${BLUE}🚀 MCP Project Attachment Tool${NC}"
    echo ""

    parse_args "$@"
    validate_project
    ensure_config_dir
    backup_config
    generate_config
    create_project_env
    apply_template
    create_shortcuts
    show_next_steps
}

# Run main function
main "$@"