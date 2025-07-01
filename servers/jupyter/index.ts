/**
 * Jupyter MCP Server
 * Provides Jupyter notebook execution and management capabilities
 */

import { z } from 'zod';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs/promises';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';
import axios, { AxiosInstance } from 'axios';
import WebSocket from 'ws';

// Input schemas
const CreateNotebookSchema = z.object({
  name: z.string().describe('Notebook name (without .ipynb extension)'),
  directory: z.string().default('.').describe('Directory to create notebook in'),
  kernelName: z.string().default('python3').describe('Kernel to use'),
});

const OpenNotebookSchema = z.object({
  path: z.string().describe('Path to notebook file'),
});

const ExecuteCellSchema = z.object({
  notebookId: z.string().describe('Notebook session ID'),
  code: z.string().describe('Code to execute'),
  cellType: z.enum(['code', 'markdown']).default('code').describe('Cell type'),
});

const ExecuteNotebookSchema = z.object({
  path: z.string().describe('Path to notebook file'),
  parameters: z.record(z.any()).optional().describe('Parameters to pass to notebook'),
  timeout: z.number().default(300).describe('Execution timeout in seconds'),
});

const ListKernelsSchema = z.object({});

const KernelCommandSchema = z.object({
  notebookId: z.string().describe('Notebook session ID'),
  command: z.enum(['interrupt', 'restart', 'shutdown']).describe('Kernel command'),
});

const GetVariableSchema = z.object({
  notebookId: z.string().describe('Notebook session ID'),
  variableName: z.string().describe('Variable name to inspect'),
});

const PlotSchema = z.object({
  notebookId: z.string().describe('Notebook session ID'),
  plotType: z.enum(['line', 'scatter', 'bar', 'hist', 'box']).describe('Plot type'),
  data: z.object({
    x: z.array(z.number()).optional(),
    y: z.array(z.number()),
    labels: z.array(z.string()).optional(),
  }).describe('Plot data'),
  options: z.object({
    title: z.string().optional(),
    xlabel: z.string().optional(),
    ylabel: z.string().optional(),
    figsize: z.tuple([z.number(), z.number()]).optional(),
  }).optional().describe('Plot options'),
});

interface NotebookSession {
  id: string;
  path: string;
  kernelId: string;
  cells: Map<string, any>;
  variables: Map<string, any>;
}

interface JupyterConfig {
  baseUrl: string;
  token?: string;
  port: number;
}

export class JupyterServer extends BaseMCPServer {
  private jupyterProcess?: ChildProcess;
  private jupyterConfig: JupyterConfig;
  private httpClient!: AxiosInstance;
  private sessions: Map<string, NotebookSession> = new Map();
  private websockets: Map<string, WebSocket> = new Map();

  constructor() {
    super('jupyter', '1.0.0', 'Jupyter notebook execution and data science operations');
    
    this.jupyterConfig = {
      baseUrl: 'http://localhost',
      port: parseInt(process.env.JUPYTER_PORT || '8888'),
      token: process.env.JUPYTER_TOKEN,
    };
  }

  protected async onInitialize(): Promise<void> {
    // Check if Jupyter is already running
    try {
      await this.checkJupyterConnection();
      this.logger.info('Connected to existing Jupyter server');
    } catch {
      // Start Jupyter server if not running
      await this.startJupyterServer();
    }

    // Initialize HTTP client
    this.httpClient = axios.create({
      baseURL: `${this.jupyterConfig.baseUrl}:${this.jupyterConfig.port}`,
      headers: this.jupyterConfig.token ? {
        'Authorization': `token ${this.jupyterConfig.token}`,
      } : {},
    });

    this.logger.info('Jupyter server initialized', {
      port: this.jupyterConfig.port,
      hasToken: !!this.jupyterConfig.token,
    });
  }

  protected async onShutdown(): Promise<void> {
    // Close all WebSocket connections
    for (const [, ws] of this.websockets) {
      ws.close();
    }
    this.websockets.clear();

    // Shutdown all kernels
    for (const session of this.sessions.values()) {
      try {
        await this.shutdownKernel(session.kernelId);
      } catch (error) {
        this.logger.error('Failed to shutdown kernel', { error, kernelId: session.kernelId });
      }
    }
    this.sessions.clear();

    // Stop Jupyter server if we started it
    if (this.jupyterProcess) {
      this.jupyterProcess.kill('SIGTERM');
      await new Promise(resolve => setTimeout(resolve, 2000));
      if (!this.jupyterProcess.killed) {
        this.jupyterProcess.kill('SIGKILL');
      }
    }

    this.logger.info('Jupyter server shutdown');
  }

  private async checkJupyterConnection(): Promise<void> {
    const response = await axios.get(`${this.jupyterConfig.baseUrl}:${this.jupyterConfig.port}/api`, {
      headers: this.jupyterConfig.token ? {
        'Authorization': `token ${this.jupyterConfig.token}`,
      } : {},
      timeout: 5000,
    });
    
    if (response.status !== 200) {
      throw new Error('Jupyter server not responding');
    }
  }

  private async startJupyterServer(): Promise<void> {
    return new Promise((resolve, reject) => {
      const args = [
        'notebook',
        '--no-browser',
        `--port=${this.jupyterConfig.port}`,
        '--ip=0.0.0.0',
      ];

      if (!this.jupyterConfig.token) {
        args.push('--NotebookApp.token=');
        args.push('--NotebookApp.password=');
      }

      this.jupyterProcess = spawn('jupyter', args, {
        stdio: 'pipe',
        env: { ...process.env },
      });

      let started = false;
      const timeout = setTimeout(() => {
        if (!started) {
          this.jupyterProcess?.kill();
          reject(new Error('Jupyter server failed to start within timeout'));
        }
      }, 30000);

      this.jupyterProcess.stdout?.on('data', (data) => {
        const output = data.toString();
        this.logger.debug('Jupyter output', { output });
        
        if (output.includes('Jupyter Notebook is running') || output.includes('Jupyter Server is running')) {
          started = true;
          clearTimeout(timeout);
          
          // Extract token if present
          const tokenMatch = output.match(/token=([a-zA-Z0-9]+)/);
          if (tokenMatch) {
            this.jupyterConfig.token = tokenMatch[1];
          }
          
          // Wait a bit for server to fully initialize
          setTimeout(() => resolve(), 2000);
        }
      });

      this.jupyterProcess.stderr?.on('data', (data) => {
        this.logger.error('Jupyter error', { error: data.toString() });
      });

      this.jupyterProcess.on('error', (error) => {
        clearTimeout(timeout);
        reject(new Error(`Failed to start Jupyter: ${error.message}`));
      });

      this.jupyterProcess.on('exit', (code) => {
        if (!started) {
          clearTimeout(timeout);
          reject(new Error(`Jupyter process exited with code ${code}`));
        }
      });
    });
  }

  private async createKernel(kernelName: string): Promise<string> {
    const response = await this.httpClient.post('/api/kernels', {
      name: kernelName,
    });
    
    return response.data.id;
  }

  private async shutdownKernel(kernelId: string): Promise<void> {
    await this.httpClient.delete(`/api/kernels/${kernelId}`);
  }

  private async executeCode(kernelId: string, code: string): Promise<any> {
    return new Promise((resolve, reject) => {
      const wsUrl = `ws://localhost:${this.jupyterConfig.port}/api/kernels/${kernelId}/channels`;
      const ws = new WebSocket(wsUrl, {
        headers: this.jupyterConfig.token ? {
          'Authorization': `token ${this.jupyterConfig.token}`,
        } : {},
      });

      const msgId = this.generateUuid();
      const results: any[] = [];
      let executionComplete = false;

      ws.on('open', () => {
        // Send execute request
        const msg = {
          header: {
            msg_id: msgId,
            username: 'mcp',
            session: this.generateUuid(),
            msg_type: 'execute_request',
            version: '5.3',
          },
          parent_header: {},
          metadata: {},
          content: {
            code,
            silent: false,
            store_history: true,
            user_expressions: {},
            allow_stdin: false,
          },
        };
        
        ws.send(JSON.stringify(msg));
      });

      ws.on('message', (data) => {
        const msg = JSON.parse(data.toString());
        
        if (msg.parent_header.msg_id !== msgId) {
          return;
        }

        switch (msg.msg_type) {
          case 'stream':
            results.push({
              type: 'stream',
              name: msg.content.name,
              text: msg.content.text,
            });
            break;
            
          case 'display_data':
          case 'execute_result':
            results.push({
              type: 'display_data',
              data: msg.content.data,
              metadata: msg.content.metadata,
            });
            break;
            
          case 'error':
            results.push({
              type: 'error',
              ename: msg.content.ename,
              evalue: msg.content.evalue,
              traceback: msg.content.traceback,
            });
            break;
            
          case 'execute_reply':
            executionComplete = true;
            ws.close();
            
            if (msg.content.status === 'ok') {
              resolve({
                status: 'ok',
                execution_count: msg.content.execution_count,
                outputs: results,
              });
            } else {
              reject(new Error(`Execution failed: ${msg.content.status}`));
            }
            break;
        }
      });

      ws.on('error', (error) => {
        reject(error);
      });

      // Timeout after 30 seconds
      setTimeout(() => {
        if (!executionComplete) {
          ws.close();
          reject(new Error('Execution timeout'));
        }
      }, 30000);
    });
  }

  private generateUuid(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  protected async registerTools(): Promise<void> {
    // Create notebook
    this.registerTool(
      'jupyter_create_notebook',
      'Create a new Jupyter notebook',
      CreateNotebookSchema,
      createToolHandler<any>(async (params) => {
        const notebookPath = path.join(params.directory, `${params.name}.ipynb`);
        
        // Check if file already exists
        try {
          await fs.access(notebookPath);
          throw new InvalidParamsError(`Notebook ${notebookPath} already exists`);
        } catch (error: any) {
          if (error.code !== 'ENOENT') {
            throw error;
          }
        }

        // Create notebook structure
        const notebook = {
          cells: [],
          metadata: {
            kernelspec: {
              display_name: params.kernelName,
              language: 'python',
              name: params.kernelName,
            },
            language_info: {
              name: 'python',
              version: '3.9.0',
            },
          },
          nbformat: 4,
          nbformat_minor: 5,
        };

        await fs.writeFile(notebookPath, JSON.stringify(notebook, null, 2));

        return {
          success: true,
          path: notebookPath,
          name: params.name,
        };
      })
    );

    // Open notebook session
    this.registerTool(
      'jupyter_open_notebook',
      'Open a notebook and create a kernel session',
      OpenNotebookSchema,
      createToolHandler<any>(async (params) => {
        // Read notebook file
        const content = await fs.readFile(params.path, 'utf-8');
        const notebook = JSON.parse(content);
        
        // Create kernel
        const kernelName = notebook.metadata?.kernelspec?.name || 'python3';
        const kernelId = await this.createKernel(kernelName);
        
        // Create session
        const sessionId = this.generateUuid();
        const session: NotebookSession = {
          id: sessionId,
          path: params.path,
          kernelId,
          cells: new Map(),
          variables: new Map(),
        };
        
        this.sessions.set(sessionId, session);
        
        return {
          success: true,
          sessionId,
          kernelId,
          path: params.path,
          cellCount: notebook.cells?.length || 0,
        };
      })
    );

    // Execute cell
    this.registerTool(
      'jupyter_execute_cell',
      'Execute code in a notebook session',
      ExecuteCellSchema,
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        if (params.cellType === 'markdown') {
          // For markdown cells, just store the content
          const cellId = this.generateUuid();
          session.cells.set(cellId, {
            type: 'markdown',
            content: params.code,
          });
          
          return {
            success: true,
            cellId,
            type: 'markdown',
          };
        }

        // Execute code cell
        const result = await this.executeCode(session.kernelId, params.code);
        const cellId = this.generateUuid();
        
        session.cells.set(cellId, {
          type: 'code',
          source: params.code,
          execution_count: result.execution_count,
          outputs: result.outputs,
        });

        // Extract any display data
        const displayData = result.outputs
          .filter((o: any) => o.type === 'display_data')
          .map((o: any) => o.data);

        return {
          success: true,
          cellId,
          executionCount: result.execution_count,
          outputs: result.outputs,
          hasError: result.outputs.some((o: any) => o.type === 'error'),
          displayData,
        };
      })
    );

    // Execute entire notebook
    this.registerTool(
      'jupyter_execute_notebook',
      'Execute an entire notebook with optional parameters',
      ExecuteNotebookSchema,
      createToolHandler<any>(async (params) => {
        // Read notebook
        const content = await fs.readFile(params.path, 'utf-8');
        const notebook = JSON.parse(content);
        
        // Create kernel
        const kernelName = notebook.metadata?.kernelspec?.name || 'python3';
        const kernelId = await this.createKernel(kernelName);
        
        try {
          // Inject parameters if provided
          if (params.parameters && Object.keys(params.parameters).length > 0) {
            const paramCode = Object.entries(params.parameters)
              .map(([key, value]) => `${key} = ${JSON.stringify(value)}`)
              .join('\n');
            
            await this.executeCode(kernelId, paramCode);
          }

          // Execute all code cells
          const results = [];
          for (const cell of notebook.cells || []) {
            if (cell.cell_type === 'code') {
              const source = Array.isArray(cell.source) ? cell.source.join('') : cell.source;
              
              try {
                const result = await this.executeCode(kernelId, source);
                results.push({
                  success: true,
                  outputs: result.outputs,
                });
              } catch (error: any) {
                results.push({
                  success: false,
                  error: error.message,
                });
                // Continue executing remaining cells
              }
            }
          }

          return {
            success: true,
            path: params.path,
            cellsExecuted: results.length,
            results,
            hasErrors: results.some(r => !r.success),
          };
        } finally {
          // Clean up kernel
          await this.shutdownKernel(kernelId);
        }
      })
    );

    // Get variable value
    this.registerTool(
      'jupyter_get_variable',
      'Get the value of a variable in the notebook',
      GetVariableSchema,
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        // Execute code to get variable info
        const code = `
import json
import sys
try:
    _var = ${params.variableName}
    _type = type(_var).__name__
    
    # Try to get shape for arrays
    _shape = None
    if hasattr(_var, 'shape'):
        _shape = _var.shape
    
    # Try to get length
    _length = None
    if hasattr(_var, '__len__'):
        _length = len(_var)
    
    # Convert to string representation
    if _type in ['ndarray', 'DataFrame']:
        _value = str(_var)
    elif _length and _length > 100:
        _value = str(_var)[:100] + '...'
    else:
        _value = repr(_var)
    
    print(json.dumps({
        'name': '${params.variableName}',
        'type': _type,
        'shape': _shape,
        'length': _length,
        'value': _value
    }))
except NameError:
    print(json.dumps({'error': 'Variable not found'}))
except Exception as e:
    print(json.dumps({'error': str(e)}))
`;

        const result = await this.executeCode(session.kernelId, code);
        
        // Parse output
        const output = result.outputs.find((o: any) => o.type === 'stream' && o.name === 'stdout');
        if (output) {
          const data = JSON.parse(output.text);
          
          if (data.error) {
            throw new ResourceNotFoundError(data.error);
          }
          
          return data;
        }

        throw new Error('Failed to get variable value');
      })
    );

    // Create plot
    this.registerTool(
      'jupyter_plot',
      'Create a plot using matplotlib',
      PlotSchema,
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        // Build plotting code
        let code = `
import matplotlib.pyplot as plt
import numpy as np

# Set figure size
plt.figure(figsize=${JSON.stringify(params.options?.figsize || [10, 6])})
`;

        // Add plot based on type
        switch (params.plotType) {
          case 'line':
            if (params.data.x) {
              code += `plt.plot(${JSON.stringify(params.data.x)}, ${JSON.stringify(params.data.y)})`;
            } else {
              code += `plt.plot(${JSON.stringify(params.data.y)})`;
            }
            break;
            
          case 'scatter':
            if (params.data.x) {
              code += `plt.scatter(${JSON.stringify(params.data.x)}, ${JSON.stringify(params.data.y)})`;
            } else {
              code += `plt.scatter(range(len(${JSON.stringify(params.data.y)})), ${JSON.stringify(params.data.y)})`;
            }
            break;
            
          case 'bar':
            if (params.data.labels && params.data.x) {
              code += `plt.bar(${JSON.stringify(params.data.labels)}, ${JSON.stringify(params.data.y)})`;
            } else if (params.data.x) {
              code += `plt.bar(${JSON.stringify(params.data.x)}, ${JSON.stringify(params.data.y)})`;
            } else {
              code += `plt.bar(range(len(${JSON.stringify(params.data.y)})), ${JSON.stringify(params.data.y)})`;
            }
            break;
            
          case 'hist':
            code += `plt.hist(${JSON.stringify(params.data.y)}, bins=20)`;
            break;
            
          case 'box':
            code += `plt.boxplot(${JSON.stringify(params.data.y)})`;
            break;
        }

        // Add labels and title
        if (params.options?.title) {
          code += `\nplt.title('${params.options.title}')`;
        }
        if (params.options?.xlabel) {
          code += `\nplt.xlabel('${params.options.xlabel}')`;
        }
        if (params.options?.ylabel) {
          code += `\nplt.ylabel('${params.options.ylabel}')`;
        }

        code += '\nplt.show()';

        // Execute plotting code
        const result = await this.executeCode(session.kernelId, code);
        const cellId = this.generateUuid();
        
        session.cells.set(cellId, {
          type: 'code',
          source: code,
          outputs: result.outputs,
        });

        // Extract plot data
        const plotOutput = result.outputs.find((o: any) => 
          o.type === 'display_data' && o.data['image/png']
        );

        return {
          success: true,
          cellId,
          plotType: params.plotType,
          hasPlot: !!plotOutput,
          plotData: plotOutput?.data,
        };
      })
    );

    // List available kernels
    this.registerTool(
      'jupyter_list_kernels',
      'List available Jupyter kernels',
      ListKernelsSchema,
      createToolHandler(async () => {
        const response = await this.httpClient.get('/api/kernelspecs');
        
        const kernels = Object.entries(response.data.kernelspecs).map(([name, spec]: [string, any]) => ({
          name,
          displayName: spec.spec.display_name,
          language: spec.spec.language,
        }));

        return {
          kernels,
          default: response.data.default,
        };
      })
    );

    // Kernel control
    this.registerTool(
      'jupyter_kernel_control',
      'Control kernel (interrupt, restart, shutdown)',
      KernelCommandSchema,
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        switch (params.command) {
          case 'interrupt':
            await this.httpClient.post(`/api/kernels/${session.kernelId}/interrupt`);
            break;
            
          case 'restart':
            await this.httpClient.post(`/api/kernels/${session.kernelId}/restart`);
            // Clear session variables
            session.variables.clear();
            break;
            
          case 'shutdown':
            await this.shutdownKernel(session.kernelId);
            this.sessions.delete(params.notebookId);
            break;
        }

        return {
          success: true,
          command: params.command,
          kernelId: session.kernelId,
        };
      })
    );

    // Save notebook
    this.registerTool(
      'jupyter_save_notebook',
      'Save the current notebook session to file',
      z.object({
        notebookId: z.string().describe('Notebook session ID'),
        path: z.string().optional().describe('Path to save (defaults to original path)'),
      }),
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        const savePath = params.path || session.path;
        
        // Read original notebook
        const content = await fs.readFile(session.path, 'utf-8');
        const notebook = JSON.parse(content);
        
        // Update cells
        const cells = [];
        for (const [cellId, cell] of session.cells) {
          if (cell.type === 'markdown') {
            cells.push({
              cell_type: 'markdown',
              id: cellId,
              metadata: {},
              source: cell.content.split('\n'),
            });
          } else {
            cells.push({
              cell_type: 'code',
              id: cellId,
              metadata: {},
              source: cell.source.split('\n'),
              execution_count: cell.execution_count,
              outputs: cell.outputs || [],
            });
          }
        }
        
        notebook.cells = cells;
        
        // Save notebook
        await fs.writeFile(savePath, JSON.stringify(notebook, null, 2));
        
        return {
          success: true,
          path: savePath,
          cellCount: cells.length,
        };
      })
    );

    // List active sessions
    this.registerTool(
      'jupyter_list_sessions',
      'List active notebook sessions',
      z.object({}),
      createToolHandler(async () => {
        const sessions = Array.from(this.sessions.entries()).map(([id, session]) => ({
          id,
          path: session.path,
          kernelId: session.kernelId,
          cellCount: session.cells.size,
        }));

        return {
          sessions,
          count: sessions.length,
        };
      })
    );

    // Export notebook
    this.registerTool(
      'jupyter_export',
      'Export notebook to different formats',
      z.object({
        notebookId: z.string().describe('Notebook session ID'),
        format: z.enum(['html', 'pdf', 'markdown', 'latex', 'script']).describe('Export format'),
        outputPath: z.string().describe('Output file path'),
      }),
      createToolHandler<any>(async (params) => {
        const session = this.sessions.get(params.notebookId);
        if (!session) {
          throw new ResourceNotFoundError(`Notebook session ${params.notebookId} not found`);
        }

        // Save notebook state before export
        const savePath = session.path;
        const content = await fs.readFile(session.path, 'utf-8');
        const notebook = JSON.parse(content);
        
        // Update cells
        const cells = [];
        for (const [cellId, cell] of session.cells) {
          if (cell.type === 'markdown') {
            cells.push({
              cell_type: 'markdown',
              id: cellId,
              metadata: {},
              source: cell.content.split('\n'),
            });
          } else {
            cells.push({
              cell_type: 'code',
              id: cellId,
              metadata: {},
              source: cell.source.split('\n'),
              execution_count: cell.execution_count,
              outputs: cell.outputs || [],
            });
          }
        }
        
        notebook.cells = cells;
        await fs.writeFile(savePath, JSON.stringify(notebook, null, 2));

        // Use nbconvert to export
        return new Promise((resolve, reject) => {
          const args = [
            'nbconvert',
            '--to', params.format,
            '--output', params.outputPath,
            session.path,
          ];

          const process = spawn('jupyter', args);
          
          process.on('close', (code) => {
            if (code === 0) {
              resolve({
                success: true,
                format: params.format,
                outputPath: params.outputPath,
              });
            } else {
              reject(new Error(`Export failed with code ${code}`));
            }
          });

          process.on('error', (error) => {
            reject(new Error(`Export failed: ${error.message}`));
          });
        });
      })
    );
  }
}