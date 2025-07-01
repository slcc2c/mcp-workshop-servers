#!/usr/bin/env node

/**
 * Runner for redis MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { RedisServer } from '../dist/servers/redis/index.js';

const redisServer = new RedisServer();

// Create MCP server instance
const server = new Server(
  {
    name: redisServer.name,
    version: redisServer.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: redisServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await redisServer.executeTool(name, args || {});
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${error.message}`,
        },
      ],
    };
  }
});

// Initialize and start server
async function main() {
  try {
    // Initialize the redis server
    await redisServer.initialize();
    console.error('redis server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('redis MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
