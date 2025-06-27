/**
 * MCP Gateway - Routes requests to appropriate MCP servers
 */

import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import { createServer, Server as HTTPServer } from 'http';
import { GatewayRequest, MCPResponse, ServerConnection } from '../types/mcp';
import { ServerConfig } from '../types/config';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { ServerNotFoundError, formatError } from '../utils/errors';
import { ServerManager } from './server-manager';
import { RequestRouter } from './router';
import { Middleware } from './middleware';

export class MCPGateway {
  private app: Express;
  private server: HTTPServer;
  private logger: Logger;
  private serverManager: ServerManager;
  private router: RequestRouter;
  private middleware: Middleware;
  private started: boolean = false;

  constructor(private config: ServerConfig) {
    this.logger = createLogger('mcp-gateway');
    this.app = express();
    this.server = createServer(this.app);
    
    this.serverManager = new ServerManager(config);
    this.router = new RequestRouter(this.serverManager);
    this.middleware = new Middleware(config);
    
    this.setupMiddleware();
    this.setupRoutes();
  }

  private setupMiddleware(): void {
    // Basic middleware
    this.app.use(express.json({ limit: '10mb' }));
    this.app.use(express.urlencoded({ extended: true }));
    
    // CORS
    if (this.config.gateway.cors.enabled) {
      this.app.use(cors({
        origin: this.config.gateway.cors.origins,
        credentials: true,
      }));
    }
    
    // Custom middleware
    this.app.use(this.middleware.requestLogger());
    this.app.use(this.middleware.errorHandler());
    
    if (this.config.gateway.rateLimit.enabled) {
      this.app.use(this.middleware.rateLimiter());
    }
    
    if (this.config.security.authentication.enabled) {
      this.app.use(this.middleware.authenticate());
    }
  }

  private setupRoutes(): void {
    // Health check
    this.app.get('/health', (req: Request, res: Response) => {
      res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        servers: this.serverManager.getServerStatuses(),
      });
    });
    
    // Server status
    this.app.get('/api/v1/servers', (req: Request, res: Response) => {
      res.json({
        servers: this.serverManager.getServerStatuses(),
      });
    });
    
    // Server info
    this.app.get('/api/v1/servers/:name', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const status = await this.serverManager.getServerStatus(req.params.name);
        if (!status) {
          throw new ServerNotFoundError(req.params.name);
        }
        res.json(status);
      } catch (error) {
        next(error);
      }
    });
    
    // Execute tool
    this.app.post('/api/v1/execute', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const request = req.body as GatewayRequest;
        const response = await this.router.route(request);
        res.json(response);
      } catch (error) {
        next(error);
      }
    });
    
    // Direct server communication
    this.app.post('/api/v1/servers/:name/execute', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const request: GatewayRequest = {
          ...req.body,
          server: req.params.name,
        };
        const response = await this.router.route(request);
        res.json(response);
      } catch (error) {
        next(error);
      }
    });
    
    // Start/stop servers
    this.app.post('/api/v1/servers/:name/start', async (req: Request, res: Response, next: NextFunction) => {
      try {
        await this.serverManager.startServer(req.params.name);
        res.json({ success: true });
      } catch (error) {
        next(error);
      }
    });
    
    this.app.post('/api/v1/servers/:name/stop', async (req: Request, res: Response, next: NextFunction) => {
      try {
        await this.serverManager.stopServer(req.params.name);
        res.json({ success: true });
      } catch (error) {
        next(error);
      }
    });
    
    // WebSocket endpoint for real-time communication (future enhancement)
    this.app.get('/api/v1/ws', (req: Request, res: Response) => {
      res.status(501).json({ error: 'WebSocket support coming soon' });
    });
    
    // Error handling
    this.app.use((error: Error, req: Request, res: Response, next: NextFunction) => {
      const mcpError = formatError(error);
      this.logger.error('Request error', { 
        error: mcpError, 
        path: req.path,
        method: req.method 
      });
      
      res.status(500).json({ error: mcpError });
    });
    
    // 404 handler
    this.app.use((req: Request, res: Response) => {
      res.status(404).json({
        error: {
          code: -32001,
          message: 'Endpoint not found',
          data: { path: req.path },
        },
      });
    });
  }

  async start(): Promise<void> {
    if (this.started) {
      return;
    }

    try {
      // Initialize server manager
      await this.serverManager.initialize();
      
      // Start HTTP server
      await new Promise<void>((resolve, reject) => {
        this.server.listen(this.config.gateway.port, this.config.gateway.host, () => {
          resolve();
        });
        
        this.server.on('error', reject);
      });
      
      this.started = true;
      this.logger.info('Gateway started', {
        host: this.config.gateway.host,
        port: this.config.gateway.port,
      });
      
      // Log available servers
      const statuses = this.serverManager.getServerStatuses();
      this.logger.info('Available servers', {
        count: statuses.length,
        servers: statuses.map(s => ({
          name: s.name,
          status: s.status,
        })),
      });
    } catch (error) {
      this.logger.error('Failed to start gateway', { error });
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (!this.started) {
      return;
    }

    try {
      // Stop all servers
      await this.serverManager.shutdown();
      
      // Stop HTTP server
      await new Promise<void>((resolve, reject) => {
        this.server.close((error) => {
          if (error) {
            reject(error);
          } else {
            resolve();
          }
        });
      });
      
      this.started = false;
      this.logger.info('Gateway stopped');
    } catch (error) {
      this.logger.error('Error stopping gateway', { error });
      throw error;
    }
  }

  getServerManager(): ServerManager {
    return this.serverManager;
  }
}

// Export for use as a module
export { ServerManager } from './server-manager';
export { RequestRouter } from './router';
export { Middleware } from './middleware';