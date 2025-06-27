/**
 * Logger implementation using Winston
 */

import winston from 'winston';
import { Logger, LogLevel, LogContext } from '../types/logger';

const logLevels: Record<LogLevel, number> = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

class WinstonLogger implements Logger {
  private winston: winston.Logger;

  constructor(context?: LogContext) {
    this.winston = winston.createLogger({
      levels: logLevels,
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.errors({ stack: true }),
        winston.format.json()
      ),
      defaultMeta: context,
      transports: [
        new winston.transports.Console({
          format: winston.format.combine(
            winston.format.colorize(),
            winston.format.simple()
          ),
        }),
        new winston.transports.File({
          filename: 'logs/error.log',
          level: 'error',
        }),
        new winston.transports.File({
          filename: 'logs/combined.log',
        }),
      ],
    });
  }

  error(message: string, context?: LogContext): void {
    this.winston.error(message, context);
  }

  warn(message: string, context?: LogContext): void {
    this.winston.warn(message, context);
  }

  info(message: string, context?: LogContext): void {
    this.winston.info(message, context);
  }

  debug(message: string, context?: LogContext): void {
    this.winston.debug(message, context);
  }

  child(context: LogContext): Logger {
    return new WinstonLogger({ ...this.winston.defaultMeta, ...context });
  }
}

// Create default logger instance
export const logger = new WinstonLogger({ service: 'mcp-workshop' });

// Factory function for creating service-specific loggers
export function createLogger(service: string, context?: LogContext): Logger {
  return new WinstonLogger({ service, ...context });
}