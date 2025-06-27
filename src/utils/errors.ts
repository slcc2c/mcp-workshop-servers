/**
 * Custom error classes for MCP servers
 */

import { MCPError, MCPErrorCode } from '../types/mcp';

export class MCPServerError extends Error {
  public readonly code: MCPErrorCode;
  public readonly data?: unknown;

  constructor(code: MCPErrorCode, message: string, data?: unknown) {
    super(message);
    this.name = 'MCPServerError';
    this.code = code;
    this.data = data;
  }

  toMCPError(): MCPError {
    return {
      code: this.code,
      message: this.message,
      data: this.data,
    };
  }
}

export class ServerNotFoundError extends MCPServerError {
  constructor(serverName: string) {
    super(
      MCPErrorCode.ServerNotFound,
      `Server '${serverName}' not found`,
      { serverName }
    );
  }
}

export class MethodNotFoundError extends MCPServerError {
  constructor(method: string) {
    super(
      MCPErrorCode.MethodNotFound,
      `Method '${method}' not found`,
      { method }
    );
  }
}

export class InvalidParamsError extends MCPServerError {
  constructor(message: string, params?: unknown) {
    super(
      MCPErrorCode.InvalidParams,
      message,
      { params }
    );
  }
}

export class AuthenticationError extends MCPServerError {
  constructor(message: string = 'Authentication failed') {
    super(MCPErrorCode.AuthenticationFailed, message);
  }
}

export class PermissionError extends MCPServerError {
  constructor(resource: string, operation: string) {
    super(
      MCPErrorCode.PermissionDenied,
      `Permission denied for ${operation} on ${resource}`,
      { resource, operation }
    );
  }
}

export class ResourceNotFoundError extends MCPServerError {
  constructor(resource: string) {
    super(
      MCPErrorCode.ResourceNotFound,
      `Resource '${resource}' not found`,
      { resource }
    );
  }
}

export class ResourceLimitError extends MCPServerError {
  constructor(limit: string, current: number, max: number) {
    super(
      MCPErrorCode.ResourceLimitExceeded,
      `${limit} limit exceeded: ${current}/${max}`,
      { limit, current, max }
    );
  }
}

export class TimeoutError extends MCPServerError {
  constructor(operation: string, timeout: number) {
    super(
      MCPErrorCode.ServerTimeout,
      `Operation '${operation}' timed out after ${timeout}ms`,
      { operation, timeout }
    );
  }
}

// Error handling utilities
export function isOperationalError(error: unknown): boolean {
  if (error instanceof MCPServerError) {
    return true;
  }
  
  if (error instanceof Error) {
    // Check for known operational errors
    const operationalErrors = [
      'ENOENT',
      'EACCES',
      'ECONNREFUSED',
      'ETIMEDOUT',
    ];
    
    return operationalErrors.some(code => 
      error.message.includes(code) || (error as any).code === code
    );
  }
  
  return false;
}

export function formatError(error: unknown): MCPError {
  if (error instanceof MCPServerError) {
    return error.toMCPError();
  }
  
  if (error instanceof Error) {
    return {
      code: MCPErrorCode.InternalError,
      message: error.message,
      data: {
        name: error.name,
        stack: process.env.NODE_ENV === 'development' ? error.stack : undefined,
      },
    };
  }
  
  return {
    code: MCPErrorCode.InternalError,
    message: 'An unknown error occurred',
    data: error,
  };
}