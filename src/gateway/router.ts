/**
 * Routes MCP requests to appropriate servers
 */

import { GatewayRequest, MCPRequest, MCPResponse } from '../types/mcp';
import { ServerManager } from './server-manager';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { ServerNotFoundError } from '../utils/errors';

export class RequestRouter {
  private logger: Logger;

  constructor(private serverManager: ServerManager) {
    this.logger = createLogger('request-router');
  }

  async route(request: GatewayRequest): Promise<MCPResponse> {
    this.logger.debug('Routing request', {
      id: request.id,
      server: request.server,
      method: request.method,
    });

    // Get target server
    const server = this.serverManager.getServer(request.server);
    if (!server) {
      const status = this.serverManager.getServerStatus(request.server);
      
      if (!status) {
        throw new ServerNotFoundError(request.server);
      }
      
      if (status.status !== 'running') {
        throw new Error(`Server '${request.server}' is not running (status: ${status.status})`);
      }
      
      // Server exists but instance not available (external server)
      // In this case, we would need to communicate via IPC/network
      // For now, throw an error
      throw new Error(`Server '${request.server}' does not support direct communication`);
    }

    // Create MCP request without server field
    const mcpRequest: MCPRequest = {
      id: request.id,
      method: request.method,
      params: request.params,
    };

    // Route to server
    try {
      const response = await server.handleRequest(mcpRequest);
      
      this.logger.debug('Request completed', {
        id: request.id,
        server: request.server,
        success: !response.error,
      });

      return response;
    } catch (error) {
      this.logger.error('Request routing failed', {
        id: request.id,
        server: request.server,
        error,
      });
      
      throw error;
    }
  }

  async broadcast(method: string, params?: unknown): Promise<Map<string, MCPResponse>> {
    const responses = new Map<string, MCPResponse>();
    const servers = this.serverManager.getServerStatuses()
      .filter(s => s.status === 'running')
      .map(s => s.name);

    await Promise.all(
      servers.map(async (serverName) => {
        try {
          const response = await this.route({
            id: `broadcast-${Date.now()}-${serverName}`,
            server: serverName,
            method,
            params,
          });
          responses.set(serverName, response);
        } catch (error) {
          this.logger.error('Broadcast failed for server', {
            server: serverName,
            method,
            error,
          });
        }
      })
    );

    return responses;
  }
}