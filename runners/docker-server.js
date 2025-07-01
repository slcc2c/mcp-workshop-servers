#!/usr/bin/env node

/**
 * Runner for docker MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { DockerServer } from '../dist/servers/docker/index.js';

const dockerServer = new DockerServer();

// Create MCP server instance
const server = new Server(
  {
    name: dockerServer.name,
    version: dockerServer.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: dockerServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await dockerServer.executeTool(name, args || {});
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
    // Initialize the docker server
    await dockerServer.initialize();
    console.error('docker server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('docker MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
