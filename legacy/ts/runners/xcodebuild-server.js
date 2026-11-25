#!/usr/bin/env node

/**
 * Runner for XcodeBuild MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { XcodeBuildServer } from '../external/XcodeBuildMCP/build/index.js';

const xcodebuildServer = new XcodeBuildServer();

// Create MCP server instance
const server = new Server(
  {
    name: xcodebuildServer.name || 'xcodebuild',
    version: xcodebuildServer.version || '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: xcodebuildServer.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await xcodebuildServer.executeTool(name, args || {});
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
    // Initialize the xcodebuild server
    if (xcodebuildServer.initialize) {
      await xcodebuildServer.initialize();
    }
    console.error('XcodeBuild server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('XcodeBuild MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();