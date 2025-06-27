/**
 * Express middleware for MCP Gateway
 */

import { Request, Response, NextFunction } from 'express';
import rateLimit from 'express-rate-limit';
import { ServerConfig } from '../types/config';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { AuthenticationError } from '../utils/errors';

export class Middleware {
  private logger: Logger;

  constructor(private config: ServerConfig) {
    this.logger = createLogger('gateway-middleware');
  }

  requestLogger() {
    return (req: Request, res: Response, next: NextFunction) => {
      const start = Date.now();

      // Log request
      this.logger.info('Incoming request', {
        method: req.method,
        path: req.path,
        ip: req.ip,
        userAgent: req.get('user-agent'),
      });

      // Log response
      res.on('finish', () => {
        const duration = Date.now() - start;
        this.logger.info('Request completed', {
          method: req.method,
          path: req.path,
          statusCode: res.statusCode,
          duration,
        });
      });

      next();
    };
  }

  errorHandler() {
    return (err: Error, req: Request, res: Response, next: NextFunction) => {
      this.logger.error('Request error', {
        error: err.message,
        stack: err.stack,
        path: req.path,
        method: req.method,
      });

      // Don't expose internal errors in production
      const message = this.config.security.authentication.enabled && process.env.NODE_ENV === 'production'
        ? 'Internal server error'
        : err.message;

      res.status(500).json({
        error: {
          message,
          code: 'INTERNAL_ERROR',
        },
      });
    };
  }

  rateLimiter() {
    return rateLimit({
      windowMs: this.config.gateway.rateLimit.windowMs,
      max: this.config.gateway.rateLimit.max,
      message: 'Too many requests from this IP, please try again later',
      standardHeaders: true,
      legacyHeaders: false,
    });
  }

  authenticate() {
    return async (req: Request, res: Response, next: NextFunction) => {
      if (this.config.security.authentication.type === 'none') {
        return next();
      }

      const authHeader = req.get('authorization');
      
      if (!authHeader) {
        throw new AuthenticationError('Missing authorization header');
      }

      try {
        if (this.config.security.authentication.type === 'token') {
          const token = authHeader.replace('Bearer ', '');
          
          // Simple token validation (in production, use proper JWT or API key validation)
          if (!token || token !== process.env.AUTH_TOKEN) {
            throw new AuthenticationError('Invalid token');
          }
        } else if (this.config.security.authentication.type === 'oauth') {
          // OAuth validation would go here
          throw new Error('OAuth not implemented yet');
        }

        next();
      } catch (error) {
        this.logger.warn('Authentication failed', {
          ip: req.ip,
          path: req.path,
          error: error instanceof Error ? error.message : 'Unknown error',
        });

        res.status(401).json({
          error: {
            message: 'Authentication failed',
            code: 'AUTH_FAILED',
          },
        });
      }
    };
  }

  cors() {
    return (req: Request, res: Response, next: NextFunction) => {
      const origin = req.get('origin');
      const allowedOrigins = this.config.gateway.cors.origins;

      if (origin && allowedOrigins.some(allowed => {
        if (allowed.includes('*')) {
          const pattern = new RegExp(allowed.replace('*', '.*'));
          return pattern.test(origin);
        }
        return allowed === origin;
      })) {
        res.setHeader('Access-Control-Allow-Origin', origin);
        res.setHeader('Access-Control-Allow-Credentials', 'true');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      }

      if (req.method === 'OPTIONS') {
        res.sendStatus(200);
      } else {
        next();
      }
    };
  }

  validateRequest() {
    return (req: Request, res: Response, next: NextFunction) => {
      // Validate request body for MCP requests
      if (req.method === 'POST' && req.path.includes('/execute')) {
        const { id, method } = req.body;

        if (!id || typeof id !== 'string') {
          return res.status(400).json({
            error: {
              message: 'Invalid request: missing or invalid id',
              code: 'INVALID_REQUEST',
            },
          });
        }

        if (!method || typeof method !== 'string') {
          return res.status(400).json({
            error: {
              message: 'Invalid request: missing or invalid method',
              code: 'INVALID_REQUEST',
            },
          });
        }
      }

      next();
    };
  }
}