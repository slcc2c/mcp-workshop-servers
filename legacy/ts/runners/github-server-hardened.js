#!/usr/bin/env node

/**
 * Hardened Runner for GitHub MCP Server
 * Includes token validation, retry logic, and comprehensive error handling
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { GitHubServer } from '../dist/servers/github/index.js';
import https from 'https';
import fs from 'fs/promises';
import path from 'path';

// Token validation with retry logic
async function validateToken(token, tokenName, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const result = await new Promise((resolve, reject) => {
        const options = {
          hostname: 'api.github.com',
          path: '/user',
          method: 'GET',
          headers: {
            'Authorization': `token ${token}`,
            'User-Agent': 'MCP-GitHub-Server/1.0'
          }
        };

        const req = https.request(options, (res) => {
          let data = '';
          
          res.on('data', (chunk) => {
            data += chunk;
          });
          
          res.on('end', () => {
            if (res.statusCode === 200) {
              const parsed = JSON.parse(data);
              resolve({
                valid: true,
                user: parsed.login,
                scopes: res.headers['x-oauth-scopes'] || 'unknown'
              });
            } else {
              reject(new Error(`Invalid token (${res.statusCode}): ${data}`));
            }
          });
        });
        
        req.on('error', reject);
        req.end();
      });
      
      console.error(`✓ ${tokenName} validated successfully (user: ${result.user})`);
      return result;
      
    } catch (error) {
      console.error(`✗ ${tokenName} validation failed (attempt ${attempt}/${retries}): ${error.message}`);
      
      if (attempt < retries) {
        // Exponential backoff: 1s, 2s, 4s
        const delay = Math.pow(2, attempt - 1) * 1000;
        console.error(`  Retrying in ${delay/1000}s...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
}

// Token discovery with fallback chain
function discoverToken() {
  const tokenSources = [
    { env: 'GITHUB_TOKEN', description: 'Primary GitHub token' },
    { env: 'GITHUB_PERSONAL_ACCESS_TOKEN', description: 'Personal access token' },
    { env: 'MCP_GITHUB_TOKEN', description: 'MCP-specific GitHub token' },
    { env: 'GH_TOKEN', description: 'GitHub CLI token' }
  ];
  
  console.error('Searching for GitHub token...');
  
  for (const source of tokenSources) {
    const token = process.env[source.env];
    if (token) {
      console.error(`✓ Found token in ${source.env} (${source.description})`);
      
      // Map to GITHUB_TOKEN for the server
      if (source.env !== 'GITHUB_TOKEN') {
        process.env.GITHUB_TOKEN = token;
        console.error(`  Mapped ${source.env} → GITHUB_TOKEN`);
      }
      
      return token;
    }
  }
  
  return null;
}

// Log authentication status
async function logAuthStatus(status, error = null) {
  const logDir = path.join(process.cwd(), 'logs');
  await fs.mkdir(logDir, { recursive: true });
  
  const logFile = path.join(logDir, 'github-mcp-auth.log');
  const entry = {
    timestamp: new Date().toISOString(),
    status,
    error: error ? error.message : null,
    pid: process.pid
  };
  
  try {
    let logs = [];
    try {
      const existing = await fs.readFile(logFile, 'utf-8');
      logs = JSON.parse(existing);
    } catch (e) {
      // File doesn't exist yet
    }
    
    logs.push(entry);
    
    // Keep only last 100 entries
    if (logs.length > 100) {
      logs = logs.slice(-100);
    }
    
    await fs.writeFile(logFile, JSON.stringify(logs, null, 2));
  } catch (e) {
    console.error('Failed to write auth log:', e.message);
  }
}

// Health check endpoint simulation
async function performHealthCheck() {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return { healthy: false, error: 'No token configured' };
  }
  
  try {
    const result = await validateToken(token, 'GITHUB_TOKEN', 1);
    return { healthy: true, user: result.user };
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

// Main server startup
async function main() {
  console.error('GitHub MCP Server (Hardened) starting...');
  
  // Step 1: Token discovery
  const token = discoverToken();
  if (!token) {
    const error = new Error(
      'No GitHub token found. Please set one of:\n' +
      '  - GITHUB_TOKEN\n' +
      '  - GITHUB_PERSONAL_ACCESS_TOKEN\n' +
      '  - MCP_GITHUB_TOKEN\n' +
      '  - GH_TOKEN'
    );
    console.error(`Error: ${error.message}`);
    await logAuthStatus('failed', error);
    process.exit(1);
  }
  
  // Step 2: Validate token
  try {
    await validateToken(token, 'GITHUB_TOKEN');
    await logAuthStatus('success');
  } catch (error) {
    console.error('\nToken validation failed. Common causes:');
    console.error('  1. Token has expired - generate a new one at:');
    console.error('     https://github.com/settings/tokens');
    console.error('  2. Token lacks required scopes - ensure it has:');
    console.error('     repo, workflow, read:org, read:user');
    console.error('  3. Network issues - check your internet connection');
    
    await logAuthStatus('failed', error);
    process.exit(1);
  }
  
  // Step 3: Initialize server
  const githubServer = new GitHubServer();
  
  const server = new Server(
    {
      name: githubServer.name,
      version: githubServer.version,
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );
  
  // Enhanced error handling for tool calls
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    try {
      const tools = githubServer.listTools();
      return {
        tools: tools.map(tool => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        })),
      };
    } catch (error) {
      console.error('Error listing tools:', error);
      throw error;
    }
  });
  
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    try {
      // Periodic health check
      if (request.params.name === 'health_check') {
        const health = await performHealthCheck();
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(health, null, 2)
          }]
        };
      }
      
      const result = await githubServer.callTool(
        request.params.name, 
        request.params.arguments || {}
      );
      return result;
      
    } catch (error) {
      console.error(`Tool call failed (${request.params.name}):`, error);
      
      // Check if it's an auth error
      if (error.message.includes('Bad credentials') || 
          error.message.includes('401')) {
        console.error('Authentication failed - token may have expired');
        await logAuthStatus('failed', error);
        
        return {
          content: [{
            type: 'text',
            text: `Authentication Error: Your GitHub token has expired or is invalid. Please generate a new token at https://github.com/settings/tokens and update your environment variable.`,
          }],
        };
      }
      
      return {
        content: [{
          type: 'text',
          text: `Error: ${error.message}`,
        }],
      };
    }
  });
  
  // Step 4: Start server
  try {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    await githubServer.initialize();
    
    console.error(`✓ GitHub MCP server running successfully`);
    console.error(`  Name: ${githubServer.name}`);
    console.error(`  Version: ${githubServer.version}`);
    console.error(`  Health checks: Enabled`);
    console.error(`  Retry logic: Enabled`);
    
  } catch (error) {
    console.error('Fatal error starting server:', error);
    await logAuthStatus('failed', error);
    process.exit(1);
  }
}

// Handle process termination
process.on('SIGINT', async () => {
  console.error('\nShutting down GitHub MCP server...');
  await logAuthStatus('shutdown');
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await logAuthStatus('shutdown');
  process.exit(0);
});

// Start the server
main().catch(async (error) => {
  console.error('Fatal error:', error);
  await logAuthStatus('failed', error);
  process.exit(1);
});