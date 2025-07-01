#!/bin/bash
# Example commands to populate AI and Server-Configurations vaults
# DO NOT RUN THIS DIRECTLY - Copy and modify commands as needed

echo "📝 Example 1Password Commands for Your Vaults"
echo "==========================================="
echo
echo "These are EXAMPLE commands. Replace the values with your actual secrets!"
echo

# AI Vault Examples
echo "🤖 AI Vault - API Keys and Tokens:"
echo "-----------------------------------"
echo
echo "# GitHub Personal Access Token"
echo 'op item create --vault=AI --title=GitHub --category=password \'
echo '  token[password]="ghp_REPLACE_WITH_YOUR_GITHUB_TOKEN" \'
echo '  notes="GitHub PAT for MCP servers"'
echo
echo "# OpenAI API Key"
echo 'op item create --vault=AI --title=OpenAI --category=password \'
echo '  api_key[password]="sk-REPLACE_WITH_YOUR_OPENAI_KEY" \'
echo '  organization[text]="org-OPTIONAL_ORG_ID" \'
echo '  notes="OpenAI API access"'
echo
echo "# Anthropic API Key"
echo 'op item create --vault=AI --title=Anthropic --category=password \'
echo '  api_key[password]="sk-ant-REPLACE_WITH_YOUR_KEY" \'
echo '  notes="Anthropic Claude API"'
echo

# Server-Configurations Vault Examples
echo "🖥️  Server-Configurations Vault - Infrastructure:"
echo "-----------------------------------------------"
echo
echo "# PostgreSQL Database"
echo 'op item create --vault=Server-Configurations --title="Database/postgres" --category=database \'
echo '  url[password]="postgresql://user:password@localhost:5432/dbname" \'
echo '  host[text]="localhost" \'
echo '  port[text]="5432" \'
echo '  database[text]="mcp_db" \'
echo '  username[text]="mcp_user"'
echo
echo "# Redis"
echo 'op item create --vault=Server-Configurations --title="Database/redis" --category=password \'
echo '  url[password]="redis://localhost:6379" \'
echo '  host[text]="localhost" \'
echo '  port[text]="6379"'
echo
echo "# MongoDB"
echo 'op item create --vault=Server-Configurations --title="Database/mongodb" --category=database \'
echo '  url[password]="mongodb://localhost:27017/mcp" \'
echo '  connection_string[password]="mongodb://user:pass@localhost:27017/mcp"'
echo
echo "# Auth Secret"
echo 'op item create --vault=Server-Configurations --title=Auth --category=password \'
echo '  secret[password]="'$(openssl rand -hex 32)'" \'
echo '  notes="JWT signing secret for gateway authentication"'
echo

echo
echo "📋 To use these secrets in your .env:"
echo "------------------------------------"
echo "GITHUB_TOKEN=1password:AI/GitHub:token"
echo "OPENAI_API_KEY=1password:AI/OpenAI:api_key"
echo "POSTGRES_URL=1password:Server-Configurations/Database/postgres:url"
echo "AUTH_SECRET=1password:Server-Configurations/Auth:secret"
echo
echo "🔍 To verify an item exists:"
echo "op item get GitHub --vault=AI"
echo "op item get Database/postgres --vault=Server-Configurations"