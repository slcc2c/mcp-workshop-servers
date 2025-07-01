import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { JupyterServer } from '../dist/servers/jupyter/index.js';

const transport = new StdioServerTransport();
const jupyterServer = new JupyterServer();

const server = new Server({
    name: jupyterServer.name,
    version: jupyterServer.version,
    capabilities: {
        tools: {}
    }
}, {
    onListTools: async () => ({
        tools: jupyterServer.listTools()
    }),
    onCallTool: async (request) => ({
        content: [await jupyterServer.executeTool(request.params.name, request.params.arguments || {})]
    })
});

async function main() {
    await jupyterServer.initialize();
    await server.connect(transport);
    console.error('Jupyter MCP server running');
}

main().catch(error => {
    console.error('Server error:', error);
    process.exit(1);
});
