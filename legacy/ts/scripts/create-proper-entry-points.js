#!/usr/bin/env node
/**
 * Create proper MCP server entry points
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.join(__dirname, '..');

const serverEntryTemplate = (serverName, className) => `#!/usr/bin/env node
/**
 * ${serverName} Server Entry Point
 */

import { ${className} } from './index.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

async function main() {
  const ${serverName.toLowerCase()}Server = new ${className}();
  
  // Create stdio transport
  const transport = new StdioServerTransport();
  
  // Create MCP server using the SDK's Server class
  const server = new Server(
    {
      name: 'mcp-${serverName.toLowerCase()}',
      version: '1.0.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // Register tool listing handler
  server.setRequestHandler('tools/list', async () => {
    const tools = ${serverName.toLowerCase()}Server.listTools();
    return {
      tools: tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        inputSchema: tool.inputSchema,
      })),
    };
  });

  // Register tool execution handler
  server.setRequestHandler('tools/call', async (request) => {
    const { name, arguments: args } = request.params as { name: string; arguments: unknown };
    const result = await ${serverName.toLowerCase()}Server.executeTool(name, args);
    return { result };
  });

  // Initialize the server
  await ${serverName.toLowerCase()}Server.initialize();
  
  // Connect transport
  await server.connect(transport);
  
  console.error('${serverName} MCP server started successfully');

  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    await ${serverName.toLowerCase()}Server.shutdown();
    await server.close();
    process.exit(0);
  });
}

main().catch((error) => {
  console.error('Failed to start ${serverName} server:', error);
  process.exit(1);
});
`;

const servers = [
  { name: 'memory', className: 'MemoryServer' },
  { name: 'docker', className: 'DockerServer' },
  { name: 'postgresql', className: 'PostgreSQLServer' },
  { name: 'redis', className: 'RedisServer' },
  { name: 'mongodb', className: 'MongoDBServer' },
  { name: 'neo4j', className: 'Neo4jServer' },
  { name: 'jupyter', className: 'JupyterServer' },
];

async function createEntryPoints() {
  console.log('Creating proper server entry points...\n');

  for (const { name, className } of servers) {
    const serverDir = path.join(projectRoot, 'servers', name);
    const entryFile = path.join(serverDir, 'run.ts');

    try {
      await fs.writeFile(entryFile, serverEntryTemplate(name, className));
      console.log(`✓ Created entry point for ${name} server`);
    } catch (error) {
      console.error(`✗ Failed to create entry point for ${name}:`, error.message);
    }
  }

  console.log('\nDone! Now run "npm run build" to compile.');
}

createEntryPoints().catch(console.error);