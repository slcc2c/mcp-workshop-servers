/**
 * Tests for BaseMCPServer
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { z } from 'zod';
import { BaseMCPServer } from '../../../src/core/base-server';

class TestServer extends BaseMCPServer {
  constructor() {
    super('test', '1.0.0', 'Test server');
  }

  protected async registerTools(): Promise<void> {
    this.registerTool(
      'test_tool',
      'A test tool',
      z.object({
        message: z.string(),
      }),
      async ({ message }) => {
        return { result: `Hello ${message}` };
      }
    );
  }

  protected async onInitialize(): Promise<void> {
    // Test-specific initialization
  }

  protected async onShutdown(): Promise<void> {
    // Test-specific cleanup
  }
}

describe('BaseMCPServer', () => {
  let server: TestServer;

  beforeEach(() => {
    server = new TestServer();
  });

  it('should create server with correct properties', () => {
    expect(server.name).toBe('test');
    expect(server.version).toBe('1.0.0');
    expect(server.description).toBe('Test server');
  });

  it('should initialize successfully', async () => {
    await server.initialize();
    
    const tools = server.listTools();
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe('test_tool');
  });

  it('should execute tools correctly', async () => {
    await server.initialize();
    
    const result = await server.executeTool('test_tool', { message: 'World' });
    expect(result).toEqual({ result: 'Hello World' });
  });

  it('should throw error for unknown tool', async () => {
    await server.initialize();
    
    await expect(
      server.executeTool('unknown_tool', {})
    ).rejects.toThrow("Tool 'unknown_tool' not found");
  });

  it('should validate tool parameters', async () => {
    await server.initialize();
    
    await expect(
      server.executeTool('test_tool', { invalid: 'param' })
    ).rejects.toThrow();
  });

  it('should handle MCP requests', async () => {
    await server.initialize();
    
    const response = await server.handleRequest({
      id: 'test-1',
      method: 'executeTool',
      params: {
        tool: 'test_tool',
        arguments: { message: 'Test' }
      }
    });

    expect(response.id).toBe('test-1');
    expect(response.error).toBeUndefined();
    expect(response.result).toEqual({ result: 'Hello Test' });
  });

  it('should handle initialize request', async () => {
    const response = await server.handleRequest({
      id: 'init-1',
      method: 'initialize',
    });

    expect(response.id).toBe('init-1');
    expect(response.error).toBeUndefined();
    expect(response.result).toMatchObject({
      name: 'test',
      version: '1.0.0',
    });
  });

  it('should handle listTools request', async () => {
    await server.initialize();
    
    const response = await server.handleRequest({
      id: 'list-1',
      method: 'listTools',
    });

    expect(response.id).toBe('list-1');
    expect(response.error).toBeUndefined();
    expect(response.result).toMatchObject({
      tools: expect.arrayContaining([
        expect.objectContaining({
          name: 'test_tool',
        })
      ])
    });
  });

  it('should handle unknown method', async () => {
    const response = await server.handleRequest({
      id: 'unknown-1',
      method: 'unknownMethod',
    });

    expect(response.id).toBe('unknown-1');
    expect(response.error).toBeDefined();
    expect(response.error?.code).toBe(-32601); // Method not found
  });

  it('should shutdown cleanly', async () => {
    await server.initialize();
    await server.shutdown();
    
    // Should be able to shutdown multiple times
    await server.shutdown();
  });
});