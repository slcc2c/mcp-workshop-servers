#!/usr/bin/env node

/**
 * Runner for memory MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { MemoryServer } from '../dist/servers/memory/index.js';

const memoryServer = new MemoryServer();

// Create MCP server instance
const server = new Server(
  {
    name: memoryServer.name,
    version: memoryServer.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: memoryServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await memoryServer.executeTool(name, args || {});
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
    // Initialize the memory server
    await memoryServer.initialize();
    console.error('memory server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('memory MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
