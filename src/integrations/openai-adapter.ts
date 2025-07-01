/**
 * OpenAI Function Calling Adapter for MCP Gateway
 * Converts OpenAI function calls to MCP protocol requests
 */

import axios, { AxiosInstance } from 'axios';
import { z } from 'zod';

// OpenAI function call schema
const FunctionCallSchema = z.object({
  name: z.string(),
  arguments: z.string(), // JSON string
});

// MCP request schema
/* const MCPRequestSchema = z.object({
  id: z.string(),
  method: z.string(),
  params: z.any(),
}); */

export interface OpenAIFunction {
  name: string;
  description: string;
  parameters: any;
  endpoint: string;
  method: string;
  tool: string;
}

export class OpenAIAdapter {
  private axios: AxiosInstance;
  private functions: Map<string, OpenAIFunction>;

  constructor(
    private _baseUrl: string,
    private _authToken: string,
    functions: OpenAIFunction[]
  ) {
    this.axios = axios.create({
      baseURL: this._baseUrl,
      headers: {
        'Authorization': `Bearer ${this._authToken}`,
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    // Index functions by name
    this.functions = new Map();
    functions.forEach(fn => {
      this.functions.set(fn.name, fn);
    });
  }

  /**
   * Convert OpenAI function call to MCP request and execute
   */
  async executeFunctionCall(functionCall: any): Promise<any> {
    const { name, arguments: argsString } = FunctionCallSchema.parse(functionCall);
    
    const fn = this.functions.get(name);
    if (!fn) {
      throw new Error(`Function '${name}' not found`);
    }

    // Parse arguments
    let args: any;
    try {
      args = JSON.parse(argsString);
    } catch (error) {
      throw new Error(`Invalid arguments for function '${name}': ${argsString}`);
    }

    // Create MCP request
    const mcpRequest: any = {
      id: `openai-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      method: fn.method,
      params: {
        name: fn.tool,
        arguments: args,
      },
    };

    // Execute request
    try {
      const response = await this.axios.post(fn.endpoint, mcpRequest);
      
      if (response.data.error) {
        throw new Error(response.data.error.message);
      }

      return response.data.result;
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new Error(error.response.data.error.message);
      }
      throw error;
    }
  }

  /**
   * Execute multiple function calls in parallel
   */
  async executeFunctionCalls(functionCalls: any[]): Promise<any[]> {
    return Promise.all(
      functionCalls.map(call => this.executeFunctionCall(call))
    );
  }

  /**
   * Get OpenAI-compatible function definitions
   */
  getFunctionDefinitions(): any[] {
    return Array.from(this.functions.values()).map(fn => ({
      type: 'function',
      function: {
        name: fn.name,
        description: fn.description,
        parameters: fn.parameters,
      },
    }));
  }

  /**
   * Create a completion with function calling
   */
  async createCompletionWithFunctions(
    messages: any[],
    options: any = {}
  ): Promise<any> {
    const openai = await import('openai');
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });

    const completion = await client.chat.completions.create({
      model: options.model || 'gpt-4-turbo-preview',
      messages,
      tools: this.getFunctionDefinitions(),
      tool_choice: options.tool_choice || 'auto',
      ...options,
    });

    // Process any function calls
    if (completion.choices[0].message.tool_calls) {
      const toolCalls = completion.choices[0].message.tool_calls;
      const results = await this.executeFunctionCalls(
        toolCalls.map(tc => tc.function)
      );

      // Return both the completion and function results
      return {
        completion,
        functionResults: results.map((result, i) => ({
          tool_call_id: toolCalls[i].id,
          result,
        })),
      };
    }

    return { completion };
  }
}

// Example usage function
export async function createOpenAIAdapter(configPath?: string): Promise<OpenAIAdapter> {
  const fs = await import('fs/promises');
  const path = await import('path');
  
  // Load configuration
  const configFile = configPath || path.join(process.cwd(), 'openai-functions.json');
  const config = JSON.parse(await fs.readFile(configFile, 'utf-8'));
  
  // Get auth token from environment
  const authToken = process.env.MCP_OPENAI_AUTH_TOKEN || config.api.authHeader.replace('Bearer ', '');
  
  return new OpenAIAdapter(
    config.api.baseUrl,
    authToken,
    config.functions
  );
}

// Standalone function for direct use with OpenAI SDK
export async function mcpFunctionHandler(
  functionName: string,
  args: any,
  configPath?: string
): Promise<any> {
  const adapter = await createOpenAIAdapter(configPath);
  return adapter.executeFunctionCall({
    name: functionName,
    arguments: JSON.stringify(args),
  });
}