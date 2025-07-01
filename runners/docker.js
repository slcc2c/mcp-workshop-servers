import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { DockerServer } from '../dist/servers/docker/index.js';

const transport = new StdioServerTransport();
const dockerServer = new DockerServer();

const server = new Server({
    name: dockerServer.name,
    version: dockerServer.version,
    capabilities: {
        tools: {}
    }
}, {
    onListTools: async () => ({
        tools: dockerServer.listTools()
    }),
    onCallTool: async (request) => ({
        content: [await dockerServer.executeTool(request.params.name, request.params.arguments || {})]
    })
});

async function main() {
    await dockerServer.initialize();
    await server.connect(transport);
    console.error('Docker MCP server running');
}

main().catch(error => {
    console.error('Server error:', error);
    process.exit(1);
});
