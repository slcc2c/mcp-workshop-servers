/**
 * WebSocket handler for real-time MCP communication
 */

import { WebSocketServer, WebSocket } from 'ws';
import { Server as HTTPServer } from 'http';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { ServerManager } from './server-manager';
import { AuthenticationMiddleware } from './auth';

export interface WebSocketClient {
  id: string;
  socket: WebSocket;
  isAuthenticated: boolean;
  clientInfo: {
    userAgent?: string;
    clientId?: string;
    connectedAt: Date;
  };
}

export interface WebSocketMessage {
  type: 'tool_call' | 'tool_response' | 'status' | 'error' | 'ping' | 'pong';
  id?: string;
  data: any;
  timestamp: number;
}

export class WebSocketHandler {
  private wss: WebSocketServer;
  private clients: Map<string, WebSocketClient> = new Map();
  private logger: Logger;

  constructor(
    private server: HTTPServer,
    private serverManager: ServerManager,
    _auth: AuthenticationMiddleware
  ) {
    this.logger = createLogger('websocket-handler');
    this.wss = new WebSocketServer({ 
      server: this.server,
      path: '/ws'
    });
    
    this.setupWebSocketServer();
  }

  private setupWebSocketServer(): void {
    this.wss.on('connection', (ws: WebSocket, request) => {
      const clientId = this.generateClientId();
      
      const client: WebSocketClient = {
        id: clientId,
        socket: ws,
        isAuthenticated: false,
        clientInfo: {
          userAgent: request.headers['user-agent'],
          connectedAt: new Date(),
        }
      };

      this.clients.set(clientId, client);
      this.logger.info('WebSocket client connected', { clientId, userAgent: client.clientInfo.userAgent });

      // Set up message handling
      ws.on('message', async (data: Buffer) => {
        try {
          const message: WebSocketMessage = JSON.parse(data.toString());
          await this.handleMessage(client, message);
        } catch (error: any) {
          this.logger.error('Error parsing WebSocket message', { clientId, error: error.message });
          this.sendError(client, 'Invalid message format', 'parse_error');
        }
      });

      // Handle client disconnect
      ws.on('close', (code: number, reason: Buffer) => {
        this.logger.info('WebSocket client disconnected', { 
          clientId, 
          code, 
          reason: reason.toString() 
        });
        this.clients.delete(clientId);
      });

      // Handle errors
      ws.on('error', (error: Error) => {
        this.logger.error('WebSocket error', { clientId, error: error.message });
        this.clients.delete(clientId);
      });

      // Send welcome message
      this.sendMessage(client, {
        type: 'status',
        data: { 
          message: 'Connected to MCP Gateway WebSocket',
          clientId,
          requiresAuth: true 
        },
        timestamp: Date.now()
      });
    });

    this.logger.info('WebSocket server initialized on /ws');
  }

  private async handleMessage(client: WebSocketClient, message: WebSocketMessage): Promise<void> {
    this.logger.debug('Received WebSocket message', { 
      clientId: client.id, 
      type: message.type,
      messageId: message.id 
    });

    try {
      switch (message.type) {
        case 'ping':
          this.sendMessage(client, {
            type: 'pong',
            id: message.id,
            data: { timestamp: Date.now() },
            timestamp: Date.now()
          });
          break;

        case 'tool_call':
          if (!client.isAuthenticated) {
            this.sendError(client, 'Authentication required', 'auth_required', message.id);
            return;
          }
          await this.handleToolCall(client, message);
          break;

        default:
          this.sendError(client, `Unknown message type: ${message.type}`, 'unknown_type', message.id);
      }
    } catch (error: any) {
      this.logger.error('Error handling WebSocket message', { 
        clientId: client.id, 
        type: message.type,
        error: error.message 
      });
      this.sendError(client, error.message, 'internal_error', message.id);
    }
  }

  private async handleToolCall(client: WebSocketClient, message: WebSocketMessage): Promise<void> {
    const { serverId, toolName, params } = message.data;

    if (!serverId || !toolName) {
      this.sendError(client, 'Missing serverId or toolName', 'invalid_params', message.id);
      return;
    }

    try {
      // Get the server connection
      const server = this.serverManager.getServer(serverId);
      if (!server) {
        this.sendError(client, `Server ${serverId} not found`, 'server_not_found', message.id);
        return;
      }

      // Execute the tool
      const result = await server.executeTool(toolName, params);

      // Send response back to client
      this.sendMessage(client, {
        type: 'tool_response',
        id: message.id,
        data: {
          success: true,
          result,
          serverId,
          toolName
        },
        timestamp: Date.now()
      });

    } catch (error: any) {
      this.sendError(client, error.message, 'tool_execution_error', message.id);
    }
  }

  private sendMessage(client: WebSocketClient, message: WebSocketMessage): void {
    if (client.socket.readyState === WebSocket.OPEN) {
      client.socket.send(JSON.stringify(message));
    }
  }

  private sendError(client: WebSocketClient, message: string, code: string, messageId?: string): void {
    this.sendMessage(client, {
      type: 'error',
      id: messageId,
      data: {
        error: message,
        code,
      },
      timestamp: Date.now()
    });
  }

  private generateClientId(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
  }

  // Public methods for broadcasting
  public broadcast(message: WebSocketMessage, excludeClient?: string): void {
    for (const [clientId, client] of this.clients) {
      if (excludeClient && clientId === excludeClient) continue;
      if (client.isAuthenticated) {
        this.sendMessage(client, message);
      }
    }
  }

  public sendToClient(clientId: string, message: WebSocketMessage): boolean {
    const client = this.clients.get(clientId);
    if (client && client.isAuthenticated) {
      this.sendMessage(client, message);
      return true;
    }
    return false;
  }

  public getConnectedClients(): Array<{ id: string; userAgent?: string; connectedAt: Date }> {
    return Array.from(this.clients.values()).map(client => ({
      id: client.id,
      userAgent: client.clientInfo.userAgent,
      connectedAt: client.clientInfo.connectedAt
    }));
  }

  public async shutdown(): Promise<void> {
    this.logger.info('Shutting down WebSocket server');
    
    // Close all client connections
    for (const client of this.clients.values()) {
      client.socket.close(1000, 'Server shutting down');
    }
    
    this.clients.clear();
    this.wss.close();
  }
}