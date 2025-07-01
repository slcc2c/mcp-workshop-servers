import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { MemoryServer } from '../dist/servers/memory/index.js';

const transport = new StdioServerTransport();
const memoryServer = new MemoryServer();

const server = new Server({
    name: memoryServer.name,
    version: memoryServer.version,
    capabilities: {
        tools: {}
    }
}, {
    onListTools: async () => ({
        tools: memoryServer.listTools()
    }),
    onCallTool: async (request) => ({
        content: [await memoryServer.executeTool(request.params.name, request.params.arguments || {})]
    })
});

async function main() {
    await memoryServer.initialize();
    await server.connect(transport);
    console.error('Memory MCP server running');
}

main().catch(error => {
    console.error('Server error:', error);
    process.exit(1);
});
