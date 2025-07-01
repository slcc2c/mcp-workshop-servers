import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { KubernetesServer } from '../dist/servers/kubernetes/index.js';

const transport = new StdioServerTransport();
const kubernetesServer = new KubernetesServer();

const server = new Server({
    name: kubernetesServer.name,
    version: kubernetesServer.version,
    capabilities: {
        tools: {}
    }
}, {
    onListTools: async () => ({
        tools: kubernetesServer.listTools()
    }),
    onCallTool: async (request) => ({
        content: [await kubernetesServer.executeTool(request.params.name, request.params.arguments || {})]
    })
});

async function main() {
    await kubernetesServer.initialize();
    await server.connect(transport);
    console.error('Kubernetes MCP server running');
}

main().catch(error => {
    console.error('Server error:', error);
    process.exit(1);
});
