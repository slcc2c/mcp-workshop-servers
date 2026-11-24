#!/usr/bin/env node

/**
 * Runner for GitHub MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { GitHubServer } from '../dist/servers/github/index.js';

// Check for required environment variables
const requiredEnvVars = ['GITHUB_TOKEN'];
const envMapping = {
  'GITHUB_PERSONAL_ACCESS_TOKEN': 'GITHUB_TOKEN'
};

// Map environment variables
for (const [from, to] of Object.entries(envMapping)) {
  if (process.env[from] && !process.env[to]) {
    process.env[to] = process.env[from];
  }
}

// Check required environment variables
for (const envVar of requiredEnvVars) {
  if (!process.env[envVar]) {
    console.error(`Error: ${envVar} environment variable is required`);
    console.error(`You can also set ${Object.keys(envMapping).find(k => envMapping[k] === envVar) || envVar}`);
    process.exit(1);
  }
}

const githubServer = new GitHubServer();

// Create MCP server instance
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

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  const tools = githubServer.listTools();
  return {
    tools: tools.map(tool => ({
      name: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema,
    })),
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    const result = await githubServer.callTool(request.params.name, request.params.arguments || {});
    return result;
  } catch (error) {
    return {
      content: [{
        type: 'text',
        text: `Error: ${error.message}`,
      }],
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  await githubServer.initialize();
  console.error(`GitHub MCP server running with name: ${githubServer.name}`);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});