/**
 * STDIO Adapter for MCP Gateway
 * Allows Claude Desktop to communicate with the HTTP gateway via stdio
 */

// @ts-ignore - MCP SDK types
import { StdioServerTransport } from '@modelcontextprotocol/sdk/dist/server/stdio.js';
// @ts-ignore - MCP SDK types
import { Server } from '@modelcontextprotocol/sdk/dist/server/index.js';
import axios, { AxiosInstance } from 'axios';
import { z } from 'zod';

// Environment configuration
const GATEWAY_URL = process.env.MCP_GATEWAY_URL || 'http://localhost:3000';
const AUTH_TOKEN = process.env.MCP_AUTH_TOKEN || '';

// Request/Response schemas
const ToolCallSchema = z.object({
  name: z.string(),
  arguments: z.any().optional(),
});

export class GatewayStdioAdapter {
  private server: Server;
  private axios: AxiosInstance;
  private availableServers: Map<string, any> = new Map();

  constructor() {
    // Create axios instance with auth
    this.axios = axios.create({
      baseURL: GATEWAY_URL,
      headers: {
        'Authorization': `Bearer ${AUTH_TOKEN}`,
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    // Create MCP server
    this.server = new Server(
      {
        name: 'mcp-gateway-adapter',
        version: '1.0.0',
      },
      {
        capabilities: {
          resources: {},
          tools: {},
          prompts: {},
        },
      }
    );

    this.setupHandlers();
  }

  private async fetchAvailableTools() {
    try {
      // Get list of available servers
      const serversResponse = await this.axios.get('/api/v1/servers');
      const servers = serversResponse.data.servers;

      // Fetch tools from each running server
      for (const server of servers) {
        if (server.status === 'running') {
          try {
            const toolsResponse = await this.axios.post(`/api/v1/servers/${server.name}/execute`, {
              id: `list-tools-${Date.now()}`,
              method: 'tools/list',
              params: {},
            });

            if (toolsResponse.data.result?.tools) {
              this.availableServers.set(server.name, {
                ...server,
                tools: toolsResponse.data.result.tools,
              });
            }
          } catch (error) {
            console.error(`Failed to fetch tools from ${server.name}:`, error);
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch available servers:', error);
    }
  }

  private setupHandlers() {
    // List available tools from all servers
    this.server.setRequestHandler('tools/list', async () => {
      await this.fetchAvailableTools();
      
      const allTools: any[] = [];
      
      for (const [serverName, _serverInfo] of this.availableServers) {
        for (const tool of _serverInfo.tools || []) {
          // Prefix tool name with server name to avoid conflicts
          allTools.push({
            ...tool,
            name: `${serverName}:${tool.name}`,
            description: `[${serverName}] ${tool.description}`,
          });
        }
      }

      return {
        tools: allTools,
      };
    });

    // Execute tool calls
    this.server.setRequestHandler('tools/call', async (request: any) => {
      const { name, arguments: args } = ToolCallSchema.parse(request.params);
      
      // Parse server name and tool name
      const [serverName, ...toolNameParts] = name.split(':');
      const toolName = toolNameParts.join(':');
      
      if (!this.availableServers.has(serverName)) {
        throw new Error(`Server '${serverName}' not found or not running`);
      }

      try {
        // Forward tool call to the appropriate server via gateway
        const response = await this.axios.post(`/api/v1/servers/${serverName}/execute`, {
          id: `tool-call-${Date.now()}`,
          method: 'tools/call',
          params: {
            name: toolName,
            arguments: args,
          },
        });

        return response.data.result;
      } catch (error: any) {
        if (error.response?.data?.error) {
          throw new Error(error.response.data.error.message);
        }
        throw error;
      }
    });

    // List resources (if any servers provide them)
    this.server.setRequestHandler('resources/list', async () => {
      const allResources: any[] = [];
      
      for (const [serverName, _serverInfo] of this.availableServers) {
        try {
          const response = await this.axios.post(`/api/v1/servers/${serverName}/execute`, {
            id: `list-resources-${Date.now()}`,
            method: 'resources/list',
            params: {},
          });

          if (response.data.result?.resources) {
            for (const resource of response.data.result.resources) {
              allResources.push({
                ...resource,
                uri: `${serverName}:${resource.uri}`,
                name: `[${serverName}] ${resource.name}`,
              });
            }
          }
        } catch (error) {
          // Server might not support resources
          continue;
        }
      }

      return {
        resources: allResources,
      };
    });

    // Read resources
    this.server.setRequestHandler('resources/read', async (request: any) => {
      const { uri } = request.params as { uri: string };
      
      // Parse server name from URI
      const [serverName, ...uriParts] = uri.split(':');
      const resourceUri = uriParts.join(':');
      
      if (!this.availableServers.has(serverName)) {
        throw new Error(`Server '${serverName}' not found`);
      }

      const response = await this.axios.post(`/api/v1/servers/${serverName}/execute`, {
        id: `read-resource-${Date.now()}`,
        method: 'resources/read',
        params: {
          uri: resourceUri,
        },
      });

      return response.data.result;
    });

    // List prompts (if any servers provide them)
    this.server.setRequestHandler('prompts/list', async () => {
      const allPrompts: any[] = [];
      
      for (const [serverName, _serverInfo] of this.availableServers) {
        try {
          const response = await this.axios.post(`/api/v1/servers/${serverName}/execute`, {
            id: `list-prompts-${Date.now()}`,
            method: 'prompts/list',
            params: {},
          });

          if (response.data.result?.prompts) {
            for (const prompt of response.data.result.prompts) {
              allPrompts.push({
                ...prompt,
                name: `${serverName}:${prompt.name}`,
                description: `[${serverName}] ${prompt.description}`,
              });
            }
          }
        } catch (error) {
          // Server might not support prompts
          continue;
        }
      }

      return {
        prompts: allPrompts,
      };
    });

    // Get prompt details
    this.server.setRequestHandler('prompts/get', async (request: any) => {
      const { name, arguments: args } = request.params as { name: string; arguments?: any };
      
      // Parse server name and prompt name
      const [serverName, ...promptNameParts] = name.split(':');
      const promptName = promptNameParts.join(':');
      
      if (!this.availableServers.has(serverName)) {
        throw new Error(`Server '${serverName}' not found`);
      }

      const response = await this.axios.post(`/api/v1/servers/${serverName}/execute`, {
        id: `get-prompt-${Date.now()}`,
        method: 'prompts/get',
        params: {
          name: promptName,
          arguments: args,
        },
      });

      return response.data.result;
    });
  }

  async start() {
    console.error('MCP Gateway STDIO Adapter starting...');
    console.error(`Connecting to gateway at: ${GATEWAY_URL}`);
    
    // Test connection to gateway
    try {
      const health = await this.axios.get('/health');
      console.error('Gateway connection successful');
      console.error(`Available servers: ${health.data.servers.map((s: any) => s.name).join(', ')}`);
    } catch (error: any) {
      console.error('Failed to connect to gateway:', error.message);
      console.error('Make sure the gateway is running and authentication is configured');
    }

    // Create stdio transport
    const transport = new StdioServerTransport();
    
    // Connect transport to server
    await this.server.connect(transport);
    
    console.error('STDIO adapter ready');
  }
}

// Start the adapter
if (import.meta.url === `file://${process.argv[1]}`) {
  const adapter = new GatewayStdioAdapter();
  adapter.start().catch((error) => {
    console.error('Failed to start adapter:', error);
    process.exit(1);
  });
}