#!/usr/bin/env node
/**
 * Generic MCP Server Runner
 * Handles the MCP protocol communication for any BaseMCPServer implementation
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { 
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { BaseMCPServer } from './base-server.js';

export async function runMCPServer(serverInstance: BaseMCPServer) {
  // Create stdio transport
  const transport = new StdioServerTransport();
  
  // Create MCP server using the SDK's Server class
  const server = new Server(
    {
      name: `mcp-${serverInstance.name}`,
      version: serverInstance.version,
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // Initialize the custom server
  await serverInstance.initialize();

  // Register tool listing handler using the correct schema
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const tools = serverInstance.listTools();
    return {
      tools: tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        inputSchema: {
          type: 'object',
          properties: {},
          required: [],
        },
      })),
    };
  });

  // Register tool execution handler using the correct schema
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    
    if (typeof name !== 'string') {
      throw new Error('Tool name must be a string');
    }
    
    try {
      const result = await serverInstance.executeTool(name, args || {});
      return { 
        content: [{ 
          type: 'text', 
          text: typeof result === 'string' ? result : JSON.stringify(result, null, 2) 
        }] 
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      return { 
        content: [{ type: 'text', text: `Error: ${errorMessage}` }],
        isError: true,
      };
    }
  });

  // Connect transport
  await server.connect(transport);
  
  console.error(`${serverInstance.name} MCP server started successfully`);

  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    await serverInstance.shutdown();
    await server.close();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    await serverInstance.shutdown();
    await server.close();
    process.exit(0);
  });
}
