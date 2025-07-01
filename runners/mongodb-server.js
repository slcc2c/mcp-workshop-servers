#!/usr/bin/env node

/**
 * Runner for mongodb MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { MongodbServer } from '../dist/servers/mongodb/index.js';

const mongodbServer = new MongodbServer();

// Create MCP server instance
const server = new Server(
  {
    name: mongodbServer.name,
    version: mongodbServer.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: mongodbServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await mongodbServer.executeTool(name, args || {});
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
    // Initialize the mongodb server
    await mongodbServer.initialize();
    console.error('mongodb server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('mongodb MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
