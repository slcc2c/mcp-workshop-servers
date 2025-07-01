#!/usr/bin/env node

/**
 * Runner for postgresql MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { PostgresqlServer } from '../dist/servers/postgresql/index.js';

const postgresqlServer = new PostgresqlServer();

// Create MCP server instance
const server = new Server(
  {
    name: postgresqlServer.name,
    version: postgresqlServer.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: postgresqlServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await postgresqlServer.executeTool(name, args || {});
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
    // Initialize the postgresql server
    await postgresqlServer.initialize();
    console.error('postgresql server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('postgresql MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
