#!/usr/bin/env node
/**
 * Fix MCP Servers Script
 * Creates proper entry points for all MCP servers
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
 * Starts the ${serverName} MCP server with stdio transport
 */

import { ${className} } from './index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';

async function main() {
  try {
    // Create the server instance
    const ${serverName.toLowerCase()}Server = new ${className}();
    
    // Create MCP server
    const server = new Server(
      {
        name: 'mcp-${serverName.toLowerCase()}',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
          resources: {},
        },
      }
    );

    // Set up request handlers
    server.setRequestHandler('tools/list', async () => {
      const tools = ${serverName.toLowerCase()}Server.getTools();
      return {
        tools: Object.entries(tools).map(([name, tool]) => ({
          name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        })),
      };
    });

    server.setRequestHandler('tools/call', async (request) => {
      const { name, arguments: args } = request.params;
      const tools = ${serverName.toLowerCase()}Server.getTools();
      
      if (!tools[name]) {
        throw new Error(\`Unknown tool: \${name}\`);
      }

      const result = await tools[name].handler(args);
      return { result };
    });

    server.setRequestHandler('resources/list', async () => {
      const resources = await ${serverName.toLowerCase()}Server.listResources();
      return { resources };
    });

    server.setRequestHandler('resources/read', async (request) => {
      const { uri } = request.params;
      const resource = await ${serverName.toLowerCase()}Server.readResource(uri);
      return { contents: [resource] };
    });

    // Initialize server
    await ${serverName.toLowerCase()}Server.initialize();

    // Create and run stdio transport
    const transport = new StdioServerTransport();
    await server.connect(transport);
    
    console.error('${serverName} MCP server started');

    // Handle shutdown
    process.on('SIGINT', async () => {
      await ${serverName.toLowerCase()}Server.shutdown();
      await server.close();
      process.exit(0);
    });

  } catch (error) {
    console.error('Failed to start ${serverName.toLowerCase()} server:', error);
    process.exit(1);
  }
}

main();
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

async function createServerEntryPoints() {
  console.log('Creating server entry points...\n');

  for (const { name, className } of servers) {
    const serverDir = path.join(projectRoot, 'servers', name);
    const entryFile = path.join(serverDir, 'run.ts');

    try {
      // Check if directory exists
      await fs.stat(serverDir);
      
      // Create entry point
      await fs.writeFile(entryFile, serverEntryTemplate(name, className));
      console.log(`✓ Created entry point for ${name} server`);
    } catch (error) {
      console.error(`✗ Failed to create entry point for ${name}:`, error.message);
    }
  }

  console.log('\nDone! Now run "npm run build" to compile the entry points.');
}

// Update claude-desktop-config.json to use the new entry points
async function updateClaudeConfig() {
  console.log('\nUpdating claude-desktop-config.json...');

  const configPath = path.join(projectRoot, 'claude-desktop-config.json');
  
  try {
    const configContent = await fs.readFile(configPath, 'utf8');
    const config = JSON.parse(configContent);

    // Update server configurations to use run.js instead of index.js
    for (const { name } of servers) {
      const serverKey = `mcp-${name}`;
      if (config.mcpServers[serverKey]) {
        const oldPath = config.mcpServers[serverKey].args[0];
        const newPath = oldPath.replace('/index.js', '/run.js');
        config.mcpServers[serverKey].args[0] = newPath;
      }
    }

    // Fix the GitHub token environment variable
    if (config.mcpServers['mcp-github']) {
      config.mcpServers['mcp-github'].env.GITHUB_PERSONAL_ACCESS_TOKEN = 'env:GITHUB_PERSONAL_ACCESS_TOKEN';
    }

    await fs.writeFile(configPath, JSON.stringify(config, null, 2));
    console.log('✓ Updated configuration file');
  } catch (error) {
    console.error('✗ Failed to update config:', error.message);
  }
}

async function main() {
  await createServerEntryPoints();
  await updateClaudeConfig();
}

main().catch(console.error);