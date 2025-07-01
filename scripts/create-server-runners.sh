#!/bin/bash

# Create MCP server runners for all servers

SERVERS=(docker jupyter kubernetes memory mongodb neo4j postgresql redis)

for server in "${SERVERS[@]}"; do
  SERVER_CLASS="$(echo ${server:0:1} | tr '[a-z]' '[A-Z]')${server:1}Server"  # Capitalize first letter
  
  cat > "/Users/spencer/repos/mcp-server/runners/${server}-server.js" << EOF
#!/usr/bin/env node

/**
 * Runner for ${server} MCP Server
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { ${SERVER_CLASS} } from '../dist/servers/${server}/index.js';

const ${server}Server = new ${SERVER_CLASS}();

// Create MCP server instance
const server = new Server(
  {
    name: ${server}Server.name,
    version: ${server}Server.version,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Set up request handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: ${server}Server.listTools(),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    const result = await ${server}Server.executeTool(name, args || {});
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
          text: \`Error: \${error.message}\`,
        },
      ],
    };
  }
});

// Initialize and start server
async function main() {
  try {
    // Initialize the ${server} server
    await ${server}Server.initialize();
    console.error('${server} server initialized');
    
    // Create transport and connect
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('${server} MCP server running');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

main();
EOF

  chmod +x "/Users/spencer/repos/mcp-server/runners/${server}-server.js"
  echo "Created runner for ${server} server"
done

echo "All runners created!"