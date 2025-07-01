# MCP Client Connection Guide

This guide explains how to securely connect various AI clients to your MCP servers, including Claude Desktop, Cursor IDE, OpenAI, and custom applications.

## Table of Contents
- [Overview](#overview)
- [Authentication Setup](#authentication-setup)
- [Claude Desktop](#claude-desktop)
- [Cursor IDE](#cursor-ide)
- [OpenAI Integration](#openai-integration)
- [Custom Clients](#custom-clients)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The MCP Workshop servers support multiple client connection methods:

1. **Direct stdio** - For Claude Desktop and native MCP clients
2. **HTTP Gateway** - For web-based clients and APIs
3. **WebSocket** - For real-time bidirectional communication (coming soon)
4. **SSE (Server-Sent Events)** - For streaming updates (coming soon)

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Claude Desktop  │     │   Cursor IDE    │     │     OpenAI      │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │ stdio                 │ HTTP                   │ HTTP
         │                       │                        │
         ▼                       ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Gateway (Port 3000)                   │
│                    Token-based Authentication                    │
│                    Client-specific Rate Limiting                 │
└─────────────────────────────────────────────────────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GitHub Server  │     │ Filesystem Srv  │     │  Memory Server  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Authentication Setup

### 1. Generate Authentication Tokens

First, generate secure tokens for each client:

```bash
node scripts/generate-tokens.js
```

This creates unique tokens for:
- Claude Desktop (`MCP_CLAUDE_AUTH_TOKEN`)
- Cursor IDE (`MCP_CURSOR_AUTH_TOKEN`)
- OpenAI (`MCP_OPENAI_AUTH_TOKEN`)
- Default/Other clients (`MCP_DEFAULT_AUTH_TOKEN`)

### 2. Store Tokens Securely

The tokens are automatically added to your `.env` file. For production use, store them in 1Password:

```bash
# Store Claude Desktop token
op item create --category="API Credential" \
  --title="MCP Claude Desktop Token" \
  --vault="AI" \
  notesPlain="your-token-here"

# Update .env to use 1Password reference
MCP_CLAUDE_AUTH_TOKEN=1password:AI/MCP-Claude-Desktop-Token:notesPlain
```

### 3. Enable Gateway Authentication

Authentication is configured in `config/gateway.json`:

```json
{
  "security": {
    "authentication": {
      "enabled": true,
      "type": "token"
    }
  }
}
```

## Claude Desktop

### Configuration

Claude Desktop uses the stdio adapter to communicate with the MCP gateway. The configuration is in `claude-desktop-config.json`.

### Installation Steps

1. **Copy configuration to Claude Desktop config directory:**
   ```bash
   # macOS
   cp claude-desktop-config.json ~/Library/Application\ Support/Claude/claude_desktop_config.json
   
   # Windows
   copy claude-desktop-config.json %APPDATA%\Claude\claude_desktop_config.json
   
   # Linux
   cp claude-desktop-config.json ~/.config/Claude/claude_desktop_config.json
   ```

2. **Set environment variable:**
   ```bash
   export MCP_CLAUDE_AUTH_TOKEN=your-token-here
   ```

3. **Restart Claude Desktop**

### Using MCP Servers in Claude

Once configured, you can use MCP tools directly in Claude:

```
- Use `github:search_repositories` to search GitHub
- Use `filesystem:read_file` to read files
- Use `memory:store` to save context
- Use `docker:list_containers` to manage Docker
```

### Verifying Connection

In Claude Desktop, type:
```
List all available MCP tools
```

You should see tools from all configured servers prefixed with their server names.

## Cursor IDE

### Configuration

Cursor IDE uses HTTP transport to communicate with the gateway. Configuration is in `cursor-mcp-config.json`.

### Installation Steps

1. **Install Cursor MCP extension** (if available)

2. **Configure MCP settings in Cursor:**
   - Open Settings (Cmd/Ctrl + ,)
   - Search for "MCP"
   - Set Gateway URL: `http://localhost:3000`
   - Set Auth Token: Your `MCP_CURSOR_AUTH_TOKEN`

3. **Or use configuration file:**
   ```bash
   # Copy to Cursor config directory
   cp cursor-mcp-config.json ~/.cursor/mcp/config.json
   ```

### Using in Cursor

- Use Command Palette (Cmd/Ctrl + Shift + P)
- Type "MCP" to see available commands
- Use shortcuts defined in configuration

### API Integration

Cursor can also be integrated programmatically:

```javascript
// In Cursor extension or script
const response = await fetch('http://localhost:3000/api/v1/execute', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${process.env.MCP_CURSOR_AUTH_TOKEN}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    id: 'cursor-request-001',
    server: 'github',
    method: 'tools/call',
    params: {
      name: 'search_repositories',
      arguments: { query: 'mcp server' }
    }
  })
});
```

## OpenAI Integration

### Configuration

OpenAI integration uses function calling to interact with MCP servers. Configuration is in `openai-functions.json`.

### Using with OpenAI SDK

```python
import openai
import json
import requests

# Load MCP functions configuration
with open('openai-functions.json', 'r') as f:
    mcp_config = json.load(f)

# Initialize OpenAI client
client = openai.OpenAI()

# Helper to execute MCP function
def execute_mcp_function(function_name, arguments):
    func = next(f for f in mcp_config['functions'] if f['name'] == function_name)
    
    response = requests.post(
        f"{mcp_config['api']['baseUrl']}{func['endpoint']}",
        headers={
            'Authorization': mcp_config['api']['authHeader']
        },
        json={
            'id': f'openai-{time.time()}',
            'method': func['method'],
            'params': {
                'name': func['tool'],
                'arguments': arguments
            }
        }
    )
    return response.json()['result']

# Create completion with MCP functions
completion = client.chat.completions.create(
    model="gpt-4-turbo-preview",
    messages=[
        {"role": "user", "content": "Search for Python MCP servers on GitHub"}
    ],
    tools=[{
        'type': 'function',
        'function': func
    } for func in mcp_config['functions']],
    tool_choice="auto"
)

# Process function calls
if completion.choices[0].message.tool_calls:
    for tool_call in completion.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        result = execute_mcp_function(function_name, arguments)
        print(f"Function {function_name} returned: {result}")
```

### Using the TypeScript Adapter

```typescript
import { createOpenAIAdapter } from './src/integrations/openai-adapter';

// Create adapter
const adapter = await createOpenAIAdapter();

// Use with OpenAI completion
const result = await adapter.createCompletionWithFunctions([
  { role: 'user', content: 'Find the top Python repositories for machine learning' }
], {
  model: 'gpt-4-turbo-preview',
  temperature: 0.7
});

// Function results are automatically executed and returned
console.log(result.functionResults);
```

## Custom Clients

### HTTP API Client

Any HTTP client can connect to the MCP gateway:

```javascript
class MCPClient {
  constructor(baseUrl, authToken) {
    this.baseUrl = baseUrl;
    this.authToken = authToken;
  }

  async executeCommand(server, method, params) {
    const response = await fetch(`${this.baseUrl}/api/v1/servers/${server}/execute`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        id: `custom-${Date.now()}`,
        method,
        params
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  // List available tools
  async listTools(server) {
    return this.executeCommand(server, 'tools/list', {});
  }

  // Call a tool
  async callTool(server, toolName, args) {
    return this.executeCommand(server, 'tools/call', {
      name: toolName,
      arguments: args
    });
  }
}

// Usage
const client = new MCPClient(
  'http://localhost:3000',
  process.env.MCP_DEFAULT_AUTH_TOKEN
);

const repos = await client.callTool('github', 'search_repositories', {
  query: 'mcp server',
  limit: 5
});
```

### Python Client

```python
import requests
import os
from typing import Any, Dict, Optional

class MCPClient:
    def __init__(self, base_url: str = "http://localhost:3000", 
                 auth_token: Optional[str] = None):
        self.base_url = base_url
        self.auth_token = auth_token or os.getenv('MCP_DEFAULT_AUTH_TOKEN')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json'
        })
    
    def execute_command(self, server: str, method: str, 
                       params: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/api/v1/servers/{server}/execute",
            json={
                'id': f'python-{time.time()}',
                'method': method,
                'params': params
            }
        )
        response.raise_for_status()
        return response.json()
    
    def call_tool(self, server: str, tool_name: str, 
                  arguments: Dict[str, Any]) -> Any:
        result = self.execute_command(server, 'tools/call', {
            'name': tool_name,
            'arguments': arguments
        })
        return result.get('result')

# Usage
client = MCPClient()
files = client.call_tool('filesystem', 'list_directory', {
    'path': '/Users/spencer/repos',
    'recursive': False
})
```

## Security Best Practices

### 1. Token Management

- **Never commit tokens** to version control
- **Rotate tokens regularly** (monthly recommended)
- **Use different tokens** for each client/environment
- **Store tokens securely** in 1Password or environment variables

### 2. Network Security

- **Use HTTPS** in production (configure SSL in gateway)
- **Restrict CORS origins** in `config/gateway.json`
- **Enable rate limiting** per client
- **Use firewall rules** to restrict access to port 3000

### 3. Access Control

Each client can be restricted to specific servers:

```javascript
// In src/gateway/auth.ts
{
  clientId: 'restricted-client',
  clientName: 'Restricted Client',
  token: 'xxx',
  allowedServers: ['filesystem', 'memory'], // Only these servers
}
```

### 4. Audit Logging

Enable audit logging in `config/gateway.json`:

```json
{
  "security": {
    "audit": {
      "enabled": true,
      "logPath": "./logs/audit.log"
    }
  }
}
```

## Troubleshooting

### Connection Issues

1. **Check gateway is running:**
   ```bash
   curl -H "Authorization: Bearer $MCP_DEFAULT_AUTH_TOKEN" \
     http://localhost:3000/health
   ```

2. **Verify token is correct:**
   ```bash
   echo $MCP_CLAUDE_AUTH_TOKEN
   ```

3. **Check logs:**
   ```bash
   tail -f logs/gateway.log
   tail -f ~/Library/Logs/MCP/server.log
   ```

### Common Errors

#### "Authentication failed"
- Token is missing or incorrect
- Token not set in environment
- Wrong token for the client

#### "Server not found"
- Server is not running
- Server name is misspelled
- Server failed to start (check logs)

#### "Tool not found"
- Tool name is incorrect
- Missing server prefix (use `server:tool`)
- Server doesn't support the tool

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=debug
npm run mcp:start
```

### Testing Connections

Test script for each client:

```bash
# Test Claude Desktop connection
node scripts/test-connections.js claude

# Test Cursor IDE connection
node scripts/test-connections.js cursor

# Test OpenAI connection
node scripts/test-connections.js openai
```

## Next Steps

1. **Set up SSL/TLS** for production deployments
2. **Configure monitoring** with Prometheus/Grafana
3. **Implement WebSocket** support for real-time updates
4. **Add SSE endpoints** for streaming responses
5. **Create client SDKs** for popular languages

For more information, see:
- [Architecture Overview](../ARCHITECTURE.md)
- [Security Configuration](./setup/security.md)
- [API Reference](./api/gateway.md)