#!/bin/bash

# Script to add database connection strings to 1Password vaults
# This helps users set up their database connections securely

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}Database Connection Setup for 1Password${NC}"
echo "=========================================="
echo

# Check if op CLI is available
if ! command -v op &> /dev/null; then
    echo -e "${RED}Error: 1Password CLI (op) not found${NC}"
    echo "Please install it from: https://developer.1password.com/docs/cli/get-started/"
    exit 1
fi

# Function to add a connection string to 1Password
add_connection() {
    local item_name="$1"
    local connection_string="$2"
    local vault="Server-Configurations"
    
    echo -e "${YELLOW}Adding ${item_name} to ${vault} vault...${NC}"
    
    # Check if item already exists
    if op item get "$item_name" --vault="$vault" &>/dev/null; then
        echo -e "${BLUE}Item already exists. Updating...${NC}"
        op item edit "$item_name" --vault="$vault" notesPlain="$connection_string"
    else
        echo -e "${GREEN}Creating new item...${NC}"
        op item create --category="Database" --title="$item_name" --vault="$vault" notesPlain="$connection_string"
    fi
}

# PostgreSQL Setup
echo -e "\n${BLUE}PostgreSQL Connection Setup${NC}"
echo "Example: postgresql://user:password@localhost:5432/mydb"
read -p "Enter your PostgreSQL connection string (or press Enter to skip): " postgres_url
if [ ! -z "$postgres_url" ]; then
    add_connection "PostgreSQL Connection" "$postgres_url"
fi

# Redis Setup
echo -e "\n${BLUE}Redis Connection Setup${NC}"
echo "Example: redis://user:password@localhost:6379/0"
echo "For local Redis without auth: redis://localhost:6379"
read -p "Enter your Redis connection string (or press Enter to skip): " redis_url
if [ ! -z "$redis_url" ]; then
    add_connection "Redis URL" "$redis_url"
fi

# MongoDB Setup
echo -e "\n${BLUE}MongoDB Connection Setup${NC}"
echo "Example: mongodb://user:password@localhost:27017/mydb"
echo "For replica set: mongodb://user:pass@host1:27017,host2:27017/mydb?replicaSet=rs0"
read -p "Enter your MongoDB connection string (or press Enter to skip): " mongodb_url
if [ ! -z "$mongodb_url" ]; then
    add_connection "MongoDB Connection" "$mongodb_url"
fi

# Neo4j Setup
echo -e "\n${BLUE}Neo4j Connection Setup${NC}"
echo "Neo4j requires separate URL, user, and password"
echo "Connection URL example: bolt://localhost:7687 or neo4j://localhost:7687"
read -p "Enter your Neo4j connection URL (or press Enter to skip): " neo4j_url
if [ ! -z "$neo4j_url" ]; then
    add_connection "Neo4j Connection" "$neo4j_url"
    
    read -p "Enter Neo4j username (default: neo4j): " neo4j_user
    neo4j_user=${neo4j_user:-neo4j}
    add_connection "Neo4j User" "$neo4j_user"
    
    read -sp "Enter Neo4j password: " neo4j_password
    echo
    if [ ! -z "$neo4j_password" ]; then
        add_connection "Neo4j Password" "$neo4j_password"
    fi
fi

# Jupyter Setup
echo -e "\n${BLUE}Jupyter Token Setup${NC}"
echo "Optional: Set a token for Jupyter notebook security"
read -p "Enter Jupyter token (or press Enter to run without token): " jupyter_token
if [ ! -z "$jupyter_token" ]; then
    add_connection "Jupyter Token" "$jupyter_token"
fi

# Docker Host Setup (if needed)
echo -e "\n${BLUE}Docker Host Setup${NC}"
echo "Default: unix:///var/run/docker.sock"
echo "Remote: tcp://host:2375"
read -p "Enter custom Docker host (or press Enter for default): " docker_host
if [ ! -z "$docker_host" ]; then
    add_connection "Docker Host" "$docker_host"
fi

echo
echo -e "${GREEN}✅ Database connections setup complete!${NC}"
echo
echo "Your connection strings are now securely stored in 1Password."
echo "The MCP servers will automatically retrieve them when needed."
echo
echo -e "${YELLOW}To test your connections:${NC}"
echo "1. Run: source .env"
echo "2. Start the servers: npm run mcp:start"
echo "3. Check logs for connection status"