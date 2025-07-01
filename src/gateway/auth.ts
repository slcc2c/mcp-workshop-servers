/**
 * Enhanced authentication middleware with multi-client support
 */

import { Request, Response, NextFunction } from 'express';
import rateLimit from 'express-rate-limit';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { AuthenticationError } from '../utils/errors';

export interface ClientAuth {
  clientId: string;
  clientName: string;
  token: string;
  allowedServers: string[];
  rateLimit?: {
    windowMs: number;
    max: number;
  };
}

export interface AuthRequest extends Request {
  client?: ClientAuth;
}

export class AuthenticationMiddleware {
  private logger: Logger;
  private clientTokens: Map<string, ClientAuth> = new Map();
  private rateLimiters: Map<string, any> = new Map();
  private initialized: boolean = false;

  constructor() {
    this.logger = createLogger('gateway-auth');
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      // Load client tokens from environment/secrets
      const tokens = [
        {
          clientId: 'claude',
          clientName: 'Claude Desktop',
          tokenEnv: 'MCP_CLAUDE_AUTH_TOKEN',
          allowedServers: ['*'],
        },
        {
          clientId: 'cursor',
          clientName: 'Cursor IDE',
          tokenEnv: 'MCP_CURSOR_AUTH_TOKEN',
          allowedServers: ['*'],
        },
        {
          clientId: 'openai',
          clientName: 'OpenAI',
          tokenEnv: 'MCP_OPENAI_AUTH_TOKEN',
          allowedServers: ['github', 'filesystem', 'memory'],
        },
        {
          clientId: 'default',
          clientName: 'Default Client',
          tokenEnv: 'MCP_DEFAULT_AUTH_TOKEN',
          allowedServers: ['github', 'filesystem'],
        },
      ];

      for (const config of tokens) {
        try {
          // Get token from environment variable
          const token = process.env[config.tokenEnv];

          if (token) {
            const clientAuth: ClientAuth = {
              clientId: config.clientId,
              clientName: config.clientName,
              token,
              allowedServers: config.allowedServers,
            };
            
            this.clientTokens.set(token, clientAuth);
            
            // Create rate limiter for this client
            const limiter = rateLimit({
              windowMs: clientAuth.rateLimit?.windowMs || 60000,
              max: clientAuth.rateLimit?.max || 100,
              message: `Too many requests from client '${clientAuth.clientName}'`,
              keyGenerator: () => clientAuth.clientId,
              skip: () => false,
            });
            
            this.rateLimiters.set(clientAuth.clientId, limiter);
            this.logger.info(`Loaded auth token for client: ${config.clientName}`);
          }
        } catch (error) {
          this.logger.warn(`Failed to load token for ${config.clientName}:`, error as any);
        }
      }

      // Also support legacy AUTH_TOKEN for backward compatibility
      const legacyToken = process.env.AUTH_TOKEN;
      if (legacyToken && !this.clientTokens.has(legacyToken)) {
        const legacyClient: ClientAuth = {
          clientId: 'legacy',
          clientName: 'Legacy Client',
          token: legacyToken,
          allowedServers: ['*'],
        };
        
        this.clientTokens.set(legacyToken, legacyClient);
        
        // Create rate limiter for legacy client
        const limiter = rateLimit({
          windowMs: 60000,
          max: 100,
          message: `Too many requests from client 'Legacy Client'`,
          keyGenerator: () => 'legacy',
          skip: () => false,
        });
        
        this.rateLimiters.set('legacy', limiter);
      }

      this.initialized = true;
      this.logger.info(`Authentication initialized with ${this.clientTokens.size} client tokens`);
    } catch (error) {
      this.logger.error('Failed to initialize authentication:', error as any);
      throw error;
    }
  }

  middleware() {
    return async (req: AuthRequest, res: Response, next: NextFunction) => {
      // Initialize on first request if not already done
      if (!this.initialized) {
        await this.initialize();
      }

      // Skip auth for health checks and public endpoints
      if (req.path === '/health' || req.path === '/') {
        return next();
      }

      const authHeader = req.get('authorization');
      
      if (!authHeader) {
        return res.status(401).json({
          error: {
            message: 'Missing authorization header',
            code: 'AUTH_REQUIRED',
          },
        });
      }

      try {
        const token = authHeader.replace('Bearer ', '').trim();
        
        if (!token) {
          throw new AuthenticationError('Invalid authorization format');
        }

        // Look up client by token
        const client = this.clientTokens.get(token);
        
        if (!client) {
          throw new AuthenticationError('Invalid token');
        }

        // Check if client has access to requested server
        if (req.path.includes('/servers/') && req.path.includes('/execute')) {
          const serverMatch = req.path.match(/\/servers\/([^\/]+)\//);
          if (serverMatch) {
            const serverName = serverMatch[1];
            
            if (!client.allowedServers.includes('*') && 
                !client.allowedServers.includes(serverName)) {
              throw new AuthenticationError(
                `Client '${client.clientName}' does not have access to server '${serverName}'`
              );
            }
          }
        }

        // Attach client info to request
        req.client = client;
        
        // Log successful auth
        this.logger.debug('Authentication successful', {
          clientId: client.clientId,
          clientName: client.clientName,
          path: req.path,
          method: req.method,
        });

        next();
      } catch (error) {
        this.logger.warn('Authentication failed', {
          ip: req.ip,
          path: req.path,
          error: error instanceof Error ? error.message : 'Unknown error',
        });

        res.status(401).json({
          error: {
            message: error instanceof Error ? error.message : 'Authentication failed',
            code: 'AUTH_FAILED',
          },
        });
      }
    };
  }

  // Client-specific rate limiter factory
  clientRateLimiter() {
    return (req: AuthRequest, res: Response, next: NextFunction) => {
      // Skip rate limiting for health checks
      if (req.path === '/health' || req.path === '/') {
        return next();
      }

      if (!req.client) {
        return next();
      }

      // Get rate limiter for this client
      const clientId = req.client.clientId;
      const limiter = this.rateLimiters.get(clientId);
      
      if (!limiter) {
        this.logger.warn(`No rate limiter found for client: ${clientId}`);
        return next();
      }

      limiter(req, res, next);
    };
  }

  // Get client info for logging/monitoring
  getClientInfo(req: AuthRequest): { clientId: string; clientName: string } | null {
    return req.client ? {
      clientId: req.client.clientId,
      clientName: req.client.clientName,
    } : null;
  }
}