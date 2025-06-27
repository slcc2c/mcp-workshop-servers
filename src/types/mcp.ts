/**
 * Core MCP (Model Context Protocol) type definitions
 * These types define the protocol for communication between AI assistants and tools
 */

import { z } from 'zod';

// Base message types
export interface MCPRequest {
  id: string;
  method: string;
  params?: unknown;
}

export interface MCPResponse {
  id: string;
  result?: unknown;
  error?: MCPError;
}

export interface MCPError {
  code: number;
  message: string;
  data?: unknown;
}

// Tool definition types
export interface MCPTool {
  name: string;
  description: string;
  inputSchema: z.ZodType<any>;
}

export interface MCPServer {
  name: string;
  version: string;
  description: string;
  tools: MCPTool[];
}

// Server lifecycle types
export interface MCPServerConfig {
  name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
  workingDirectory?: string;
}

export interface MCPServerStatus {
  name: string;
  status: 'running' | 'stopped' | 'error' | 'starting';
  pid?: number;
  port?: number;
  startTime?: Date;
  error?: string;
}

// Protocol message types
export const MCPRequestSchema = z.object({
  id: z.string(),
  method: z.string(),
  params: z.unknown().optional(),
});

export const MCPResponseSchema = z.object({
  id: z.string(),
  result: z.unknown().optional(),
  error: z.object({
    code: z.number(),
    message: z.string(),
    data: z.unknown().optional(),
  }).optional(),
});

// Tool execution types
export interface ToolExecutionRequest {
  tool: string;
  arguments: unknown;
}

export interface ToolExecutionResult {
  success: boolean;
  result?: unknown;
  error?: string;
}

// Gateway types
export interface GatewayRequest extends MCPRequest {
  server: string;
}

export interface ServerConnection {
  id: string;
  server: MCPServer;
  status: MCPServerStatus;
  lastHeartbeat: Date;
}

// Common tool parameter schemas
export const FilePathSchema = z.object({
  path: z.string().describe('File path'),
});

export const DirectoryPathSchema = z.object({
  path: z.string().describe('Directory path'),
  recursive: z.boolean().optional().describe('Recurse into subdirectories'),
});

export const GitHubRepoSchema = z.object({
  owner: z.string().describe('Repository owner'),
  repo: z.string().describe('Repository name'),
});

// Error codes
export enum MCPErrorCode {
  // Standard JSON-RPC 2.0 errors
  ParseError = -32700,
  InvalidRequest = -32600,
  MethodNotFound = -32601,
  InvalidParams = -32602,
  InternalError = -32603,
  
  // Custom MCP errors
  ServerNotFound = -32000,
  ServerTimeout = -32001,
  AuthenticationFailed = -32002,
  PermissionDenied = -32003,
  ResourceNotFound = -32004,
  ResourceLimitExceeded = -32005,
}

// Utility types
export type MCPRequestHandler = (request: MCPRequest) => Promise<MCPResponse>;
export type ToolHandler = (params: unknown) => Promise<unknown>;

// Server interface that all MCP servers must implement
export interface IMCPServer {
  readonly name: string;
  readonly version: string;
  readonly description: string;
  
  initialize(): Promise<void>;
  shutdown(): Promise<void>;
  
  listTools(): MCPTool[];
  executeTool(name: string, params: unknown): Promise<unknown>;
  
  handleRequest(request: MCPRequest): Promise<MCPResponse>;
}