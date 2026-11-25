#!/bin/bash
# Source this file in bash/zsh to export MCP_*_AUTH_TOKEN env vars without printing secrets:
#   source /Users/spencer/repos/mcp-server/deploy/launchd/load_mcp_tokens.sh

_MCP_ENV_FILE="/Users/spencer/repos/mcp-server/.env"
if [ -f "$_MCP_ENV_FILE" ]; then
    while IFS='=' read -r key val; do
        case "$key" in
            MCP_CLAUDE_AUTH_TOKEN|MCP_CURSOR_AUTH_TOKEN|MCP_CODEX_AUTH_TOKEN|MCP_OPENAI_AUTH_TOKEN|MCP_DEFAULT_AUTH_TOKEN)
                val="${val#\"}"
                val="${val%\"}"
                val="${val#\'}"
                val="${val%\'}"
                export "$key=$val"
                ;;
        esac
    done < "$_MCP_ENV_FILE"
fi
unset _MCP_ENV_FILE key val
