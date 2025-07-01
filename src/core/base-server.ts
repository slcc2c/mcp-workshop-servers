/**
 * Base implementation for MCP servers
 */

import { 
  IMCPServer, 
  MCPTool, 
  MCPRequest, 
  MCPResponse, 
  ToolHandler 
} from '../types/mcp';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { 
  MethodNotFoundError, 
  InvalidParamsError, 
  formatError 
} from '../utils/errors';
import { z } from 'zod';

export abstract class BaseMCPServer implements IMCPServer {
  protected logger: Logger;
  protected tools: Map<string, MCPTool>;
  protected handlers: Map<string, ToolHandler>;
  protected initialized: boolean = false;

  constructor(
    public readonly name: string,
    public readonly version: string,
    public readonly description: string
  ) {
    this.logger = createLogger(`mcp-${name}`);
    this.tools = new Map();
    this.handlers = new Map();
  }

  async initialize(): Promise<void> {
    if (this.initialized) {
      return;
    }

    this.logger.info('Initializing server', { 
      name: this.name, 
      version: this.version 
    });

    try {
      // Register tools
      await this.registerTools();
      
      // Perform server-specific initialization
      await this.onInitialize();
      
      this.initialized = true;
      this.logger.info('Server initialized successfully');
    } catch (error) {
      this.logger.error('Failed to initialize server', { error });
      throw error;
    }
  }

  async shutdown(): Promise<void> {
    if (!this.initialized) {
      return;
    }

    this.logger.info('Shutting down server');

    try {
      await this.onShutdown();
      this.initialized = false;
      this.logger.info('Server shut down successfully');
    } catch (error) {
      this.logger.error('Error during shutdown', { error });
      throw error;
    }
  }

  listTools(): MCPTool[] {
    return Array.from(this.tools.values());
  }

  async executeTool(name: string, params: unknown): Promise<unknown> {
    const tool = this.tools.get(name);
    const handler = this.handlers.get(name);

    if (!tool || !handler) {
      throw new MethodNotFoundError(`Tool '${name}' not found`);
    }

    // Validate parameters
    try {
      const validated = tool.inputSchema.parse(params);
      
      this.logger.debug('Executing tool', { 
        tool: name, 
        params: validated 
      });

      const result = await handler(validated);
      
      this.logger.debug('Tool execution completed', { 
        tool: name, 
        success: true 
      });

      return result;
    } catch (error) {
      if (error instanceof z.ZodError) {
        throw new InvalidParamsError(
          'Invalid tool parameters',
          { errors: error.errors }
        );
      }
      throw error;
    }
  }

  async handleRequest(request: MCPRequest): Promise<MCPResponse> {
    this.logger.debug('Handling request', { 
      id: request.id, 
      method: request.method 
    });

    try {
      let result: unknown;

      switch (request.method) {
        case 'initialize':
          await this.initialize();
          result = { 
            name: this.name, 
            version: this.version,
            capabilities: this.getCapabilities() 
          };
          break;

        case 'shutdown':
          await this.shutdown();
          result = { success: true };
          break;

        case 'listTools':
          result = { tools: this.listTools() };
          break;

        case 'executeTool':
          const { tool, arguments: args } = request.params as any;
          result = await this.executeTool(tool, args);
          break;

        default:
          // Allow servers to handle custom methods
          result = await this.handleCustomMethod(request.method, request.params);
      }

      return {
        id: request.id,
        result,
      };
    } catch (error) {
      this.logger.error('Request handling failed', { 
        error, 
        request 
      });

      return {
        id: request.id,
        error: formatError(error),
      };
    }
  }

  // Protected methods for subclasses

  protected registerTool(
    name: string,
    description: string,
    inputSchema: z.ZodType<any>,
    handler: ToolHandler
  ): void {
    const tool: MCPTool = { name, description, inputSchema };
    this.tools.set(name, tool);
    this.handlers.set(name, handler);
    
    this.logger.debug('Tool registered', { name });
  }

  protected getCapabilities(): Record<string, any> {
    return {
      tools: true,
      customMethods: this.getCustomMethods(),
    };
  }

  // Abstract methods for subclasses to implement

  protected abstract registerTools(): Promise<void>;
  protected abstract onInitialize(): Promise<void>;
  protected abstract onShutdown(): Promise<void>;

  // Optional methods for subclasses

  protected async handleCustomMethod(method: string, _params: unknown): Promise<unknown> {
    throw new MethodNotFoundError(method);
  }

  protected getCustomMethods(): string[] {
    return [];
  }
}

// Utility function to create a simple tool handler
export function createToolHandler<T>(
  fn: (params: T) => Promise<unknown> | unknown
): ToolHandler {
  return async (params: unknown) => {
    return await fn(params as T);
  };
}