import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { JupyterServer } from '../../servers/jupyter';
import * as fs from 'fs/promises';
import * as path from 'path';
import axios from 'axios';

describe('Jupyter MCP Server Integration Tests', () => {
  let server: any; // JupyterServer with any cast for testing
  const testNotebooksDir = path.join(process.cwd(), 'test-notebooks');
  const createdFiles: string[] = [];
  const activeSessions: string[] = [];

  beforeAll(async () => {
    // Check if Jupyter is available
    try {
      // First try to connect to existing Jupyter server
      const jupyterPort = process.env.JUPYTER_PORT || '8888';
      await axios.get(`http://localhost:${jupyterPort}/api`, { timeout: 5000 });
    } catch (error) {
      // Check if jupyter command is available
      try {
        const { spawn } = await import('child_process');
        const process = spawn('jupyter', ['--version'], { stdio: 'pipe' });
        
        await new Promise((resolve, reject) => {
          process.on('exit', (code) => {
            if (code === 0) resolve(true);
            else reject(new Error(`Jupyter not available (exit code: ${code})`));
          });
          process.on('error', reject);
          setTimeout(() => reject(new Error('Jupyter check timeout')), 5000);
        });
      } catch (error) {
        console.log('⚠️  Jupyter not available, skipping Jupyter tests');
        return;
      }
    }

    // Create test notebooks directory
    try {
      await fs.mkdir(testNotebooksDir, { recursive: true });
    } catch (error) {
      // Directory might already exist
    }

    // Initialize server
    try {
      server = new JupyterServer();
      await server.initialize();
    } catch (error) {
      console.log('⚠️  Failed to initialize Jupyter server, skipping tests:', error);
      return;
    }
  });

  afterAll(async () => {
    if (server) {
      // Close all active sessions
      for (const sessionId of activeSessions) {
        try {
          await server.executeTool('jupyter_kernel_control', {
            notebookId: sessionId,
            command: 'shutdown',
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      await server.shutdown();
    }

    // Clean up created files
    for (const filePath of createdFiles) {
      try {
        await fs.unlink(filePath);
      } catch (error) {
        // Ignore cleanup errors
      }
    }

    // Remove test directory if empty
    try {
      await fs.rmdir(testNotebooksDir);
    } catch (error) {
      // Directory might not be empty or might not exist
    }
  });

  beforeEach(async () => {
    if (!server) return;

    // Clean up any existing sessions
    try {
      const sessions = await server.executeTool('jupyter_list_sessions', {});
      for (const session of sessions.sessions) {
        if (session.path.includes('test-')) {
          try {
            await server.executeTool('jupyter_kernel_control', {
              notebookId: session.id,
              command: 'shutdown',
            });
          } catch (error) {
            // Ignore cleanup errors
          }
        }
      }
    } catch (error) {
      // Ignore if no sessions exist
    }
  });

  describe('Notebook Management', () => {
    it('should create a new notebook', async () => {
      if (!server) return;

      const notebookName = 'test-notebook-1';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      const createResult = await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
        kernelName: 'python3',
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(notebookName);
      expect(createResult.path).toBe(notebookPath);

      createdFiles.push(notebookPath);

      // Verify file exists and has correct structure
      const content = await fs.readFile(notebookPath, 'utf-8');
      const notebook = JSON.parse(content);
      
      expect(notebook.nbformat).toBe(4);
      expect(notebook.cells).toEqual([]);
      expect(notebook.metadata.kernelspec.name).toBe('python3');
    });

    it('should open an existing notebook', async () => {
      if (!server) return;

      // First create a notebook
      const notebookName = 'test-notebook-open';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
        kernelName: 'python3',
      });

      createdFiles.push(notebookPath);

      // Open the notebook
      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      expect(openResult.success).toBe(true);
      expect(openResult.sessionId).toBeDefined();
      expect(openResult.kernelId).toBeDefined();
      expect(openResult.path).toBe(notebookPath);
      expect(openResult.cellCount).toBe(0);

      activeSessions.push(openResult.sessionId);
    });

    it('should list available kernels', async () => {
      if (!server) return;

      const kernelsResult = await server.executeTool('jupyter_list_kernels', {});

      expect(kernelsResult.kernels).toBeInstanceOf(Array);
      expect(kernelsResult.kernels.length).toBeGreaterThan(0);
      expect(kernelsResult.default).toBeDefined();

      // Should have at least python3 kernel
      const pythonKernel = kernelsResult.kernels.find(k => k.name.includes('python'));
      expect(pythonKernel).toBeDefined();
      expect(pythonKernel.displayName).toBeDefined();
      expect(pythonKernel.language).toBeDefined();
    });
  });

  describe('Code Execution', () => {
    let sessionId: string;

    beforeEach(async () => {
      if (!server) return;

      // Create and open a notebook for testing
      const notebookName = 'test-execution-notebook';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      sessionId = openResult.sessionId;
      activeSessions.push(sessionId);
    });

    it('should execute simple Python code', async () => {
      if (!server || !sessionId) return;

      const executeResult = await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: 'print("Hello, Jupyter!")\nresult = 2 + 2\nprint(f"2 + 2 = {result}")',
        cellType: 'code',
      });

      expect(executeResult.success).toBe(true);
      expect(executeResult.cellId).toBeDefined();
      expect(executeResult.executionCount).toBeGreaterThan(0);
      expect(executeResult.outputs).toBeInstanceOf(Array);
      expect(executeResult.hasError).toBe(false);

      // Check output contains our print statements
      const streamOutput = executeResult.outputs.find(o => o.type === 'stream');
      expect(streamOutput).toBeDefined();
      expect(streamOutput.text).toContain('Hello, Jupyter!');
      expect(streamOutput.text).toContain('2 + 2 = 4');
    });

    it('should handle code with variables and imports', async () => {
      if (!server || !sessionId) return;

      // Execute code that creates variables
      const executeResult1 = await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: `
import math
import json

numbers = [1, 2, 3, 4, 5]
squared = [x**2 for x in numbers]
pi_value = math.pi

print(f"Numbers: {numbers}")
print(f"Squared: {squared}")
print(f"Pi: {pi_value}")
`,
      });

      expect(executeResult1.success).toBe(true);
      expect(executeResult1.hasError).toBe(false);

      // Execute code that uses the variables
      const executeResult2 = await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: `
# Use variables from previous cell
total = sum(squared)
result_dict = {
    "original": numbers,
    "squared": squared,
    "sum_of_squares": total,
    "pi": round(pi_value, 4)
}

print(json.dumps(result_dict, indent=2))
`,
      });

      expect(executeResult2.success).toBe(true);
      expect(executeResult2.hasError).toBe(false);

      const output = executeResult2.outputs.find(o => o.type === 'stream');
      expect(output?.text).toContain('"sum_of_squares": 55');
    });

    it('should handle code errors gracefully', async () => {
      if (!server || !sessionId) return;

      const executeResult = await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: `
# This will cause an error
undefined_variable + 5
print("This should not execute")
`,
      });

      expect(executeResult.success).toBe(true);
      expect(executeResult.hasError).toBe(true);

      const errorOutput = executeResult.outputs.find(o => o.type === 'error');
      expect(errorOutput).toBeDefined();
      expect(errorOutput.ename).toBe('NameError');
      expect(errorOutput.evalue).toContain('undefined_variable');
    });

    it('should execute markdown cells', async () => {
      if (!server || !sessionId) return;

      const executeResult = await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: `# Test Markdown Cell

This is a **markdown** cell with:
- Lists
- *Italic text*
- \`code snippets\`

## Math
The formula is: $E = mc^2$
`,
        cellType: 'markdown',
      });

      expect(executeResult.success).toBe(true);
      expect(executeResult.cellId).toBeDefined();
      expect(executeResult.type).toBe('markdown');
    });

    it('should get variable values', async () => {
      if (!server || !sessionId) return;

      // First create some variables
      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: `
test_string = "Hello World"
test_number = 42
test_list = [1, 2, 3, 4, 5]
test_dict = {"key1": "value1", "key2": 123}

import numpy as np
test_array = np.array([1, 2, 3, 4, 5])
`,
      });

      // Get string variable
      const stringResult = await server.executeTool('jupyter_get_variable', {
        notebookId: sessionId,
        variableName: 'test_string',
      });

      expect(stringResult.name).toBe('test_string');
      expect(stringResult.type).toBe('str');
      expect(stringResult.value).toContain('Hello World');

      // Get number variable
      const numberResult = await server.executeTool('jupyter_get_variable', {
        notebookId: sessionId,
        variableName: 'test_number',
      });

      expect(numberResult.name).toBe('test_number');
      expect(numberResult.type).toBe('int');
      expect(numberResult.value).toBe('42');

      // Get list variable
      const listResult = await server.executeTool('jupyter_get_variable', {
        notebookId: sessionId,
        variableName: 'test_list',
      });

      expect(listResult.name).toBe('test_list');
      expect(listResult.type).toBe('list');
      expect(listResult.length).toBe(5);

      // Get numpy array
      const arrayResult = await server.executeTool('jupyter_get_variable', {
        notebookId: sessionId,
        variableName: 'test_array',
      });

      expect(arrayResult.name).toBe('test_array');
      expect(arrayResult.type).toBe('ndarray');
      expect(arrayResult.shape).toEqual([5]);
    });

    it('should handle non-existent variables', async () => {
      if (!server || !sessionId) return;

      await expect(
        server.executeTool('jupyter_get_variable', {
          notebookId: sessionId,
          variableName: 'non_existent_variable',
        })
      ).rejects.toThrow('Variable not found');
    });
  });

  describe('Plotting and Visualization', () => {
    let sessionId: string;

    beforeEach(async () => {
      if (!server) return;

      // Create and open a notebook for testing
      const notebookName = 'test-plotting-notebook';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      sessionId = openResult.sessionId;
      activeSessions.push(sessionId);

      // Install matplotlib if not available
      try {
        await server.executeTool('jupyter_execute_cell', {
          notebookId: sessionId,
          code: 'import matplotlib.pyplot as plt',
        });
      } catch (error) {
        console.log('⚠️  matplotlib not available, skipping plotting tests');
        return;
      }
    });

    it('should create line plots', async () => {
      if (!server || !sessionId) return;

      const plotResult = await server.executeTool('jupyter_plot', {
        notebookId: sessionId,
        plotType: 'line',
        data: {
          x: [1, 2, 3, 4, 5],
          y: [2, 4, 6, 8, 10],
        },
        options: {
          title: 'Linear Growth',
          xlabel: 'X Values',
          ylabel: 'Y Values',
          figsize: [8, 6],
        },
      });

      expect(plotResult.success).toBe(true);
      expect(plotResult.cellId).toBeDefined();
      expect(plotResult.plotType).toBe('line');
      expect(plotResult.hasPlot).toBe(true);
    });

    it('should create scatter plots', async () => {
      if (!server || !sessionId) return;

      const plotResult = await server.executeTool('jupyter_plot', {
        notebookId: sessionId,
        plotType: 'scatter',
        data: {
          x: [1, 2, 3, 4, 5, 6],
          y: [1, 4, 9, 16, 25, 36],
        },
        options: {
          title: 'Quadratic Relationship',
          xlabel: 'X',
          ylabel: 'X²',
        },
      });

      expect(plotResult.success).toBe(true);
      expect(plotResult.plotType).toBe('scatter');
      expect(plotResult.hasPlot).toBe(true);
    });

    it('should create bar charts', async () => {
      if (!server || !sessionId) return;

      const plotResult = await server.executeTool('jupyter_plot', {
        notebookId: sessionId,
        plotType: 'bar',
        data: {
          labels: ['A', 'B', 'C', 'D'],
          y: [10, 25, 15, 30],
        },
        options: {
          title: 'Category Data',
          xlabel: 'Categories',
          ylabel: 'Values',
        },
      });

      expect(plotResult.success).toBe(true);
      expect(plotResult.plotType).toBe('bar');
      expect(plotResult.hasPlot).toBe(true);
    });

    it('should create histograms', async () => {
      if (!server || !sessionId) return;

      const plotResult = await server.executeTool('jupyter_plot', {
        notebookId: sessionId,
        plotType: 'hist',
        data: {
          y: [1, 2, 2, 3, 3, 3, 4, 4, 5, 5, 5, 5, 6, 6, 7],
        },
        options: {
          title: 'Distribution',
          xlabel: 'Values',
          ylabel: 'Frequency',
        },
      });

      expect(plotResult.success).toBe(true);
      expect(plotResult.plotType).toBe('hist');
      expect(plotResult.hasPlot).toBe(true);
    });
  });

  describe('Kernel Management', () => {
    let sessionId: string;

    beforeEach(async () => {
      if (!server) return;

      // Create and open a notebook for testing
      const notebookName = 'test-kernel-notebook';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      sessionId = openResult.sessionId;
      activeSessions.push(sessionId);
    });

    it('should restart kernel', async () => {
      if (!server || !sessionId) return;

      // Create a variable
      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: 'test_variable = "before_restart"',
      });

      // Verify variable exists
      const beforeRestart = await server.executeTool('jupyter_get_variable', {
        notebookId: sessionId,
        variableName: 'test_variable',
      });
      expect(beforeRestart.value).toContain('before_restart');

      // Restart kernel
      const restartResult = await server.executeTool('jupyter_kernel_control', {
        notebookId: sessionId,
        command: 'restart',
      });

      expect(restartResult.success).toBe(true);
      expect(restartResult.command).toBe('restart');

      // Wait a moment for restart to complete
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Variable should no longer exist
      await expect(
        server.executeTool('jupyter_get_variable', {
          notebookId: sessionId,
          variableName: 'test_variable',
        })
      ).rejects.toThrow('Variable not found');
    });

    it('should interrupt kernel', async () => {
      if (!server || !sessionId) return;

      // Start a long-running operation (this is just a test, so we'll interrupt immediately)
      const interruptResult = await server.executeTool('jupyter_kernel_control', {
        notebookId: sessionId,
        command: 'interrupt',
      });

      expect(interruptResult.success).toBe(true);
      expect(interruptResult.command).toBe('interrupt');
    });

    it('should shutdown kernel', async () => {
      if (!server || !sessionId) return;

      const shutdownResult = await server.executeTool('jupyter_kernel_control', {
        notebookId: sessionId,
        command: 'shutdown',
      });

      expect(shutdownResult.success).toBe(true);
      expect(shutdownResult.command).toBe('shutdown');

      // Remove from active sessions since it's shutdown
      const index = activeSessions.indexOf(sessionId);
      if (index > -1) {
        activeSessions.splice(index, 1);
      }

      // Session should no longer exist
      const sessions = await server.executeTool('jupyter_list_sessions', {});
      expect(sessions.sessions.find(s => s.id === sessionId)).toBeUndefined();
    });
  });

  describe('Notebook Execution', () => {
    it('should execute entire notebook', async () => {
      if (!server) return;

      // Create a notebook with multiple cells
      const notebookName = 'test-full-execution';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      // Create notebook with some cells
      const notebook = {
        cells: [
          {
            cell_type: 'code',
            source: ['# Setup\nimport math\nx = 10'],
          },
          {
            cell_type: 'code',
            source: ['# Calculation\ny = x * 2\nz = math.sqrt(y)'],
          },
          {
            cell_type: 'code',
            source: ['# Output\nprint(f"x = {x}")\nprint(f"y = {y}")\nprint(f"z = {z}")'],
          },
        ],
        metadata: {
          kernelspec: {
            display_name: 'Python 3',
            language: 'python',
            name: 'python3',
          },
        },
        nbformat: 4,
        nbformat_minor: 5,
      };

      await fs.writeFile(notebookPath, JSON.stringify(notebook, null, 2));
      createdFiles.push(notebookPath);

      // Execute the entire notebook
      const executeResult = await server.executeTool('jupyter_execute_notebook', {
        path: notebookPath,
        parameters: {
          x: 20, // Override x value
        },
        timeout: 60,
      });

      expect(executeResult.success).toBe(true);
      expect(executeResult.path).toBe(notebookPath);
      expect(executeResult.cellsExecuted).toBe(3);
      expect(executeResult.hasErrors).toBe(false);
      expect(executeResult.results).toHaveLength(3);

      // Check that all cells executed successfully
      expect(executeResult.results.every(r => r.success)).toBe(true);

      // Check output from the last cell
      const lastCellResult = executeResult.results[2];
      const output = lastCellResult.outputs?.find(o => o.type === 'stream');
      expect(output?.text).toContain('x = 20'); // Should use our parameter
      expect(output?.text).toContain('y = 40'); // x * 2
    });

    it('should handle notebook execution with errors', async () => {
      if (!server) return;

      // Create a notebook with an error
      const notebookName = 'test-error-execution';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      const notebook = {
        cells: [
          {
            cell_type: 'code',
            source: ['# Good cell\nprint("This works")'],
          },
          {
            cell_type: 'code',
            source: ['# Bad cell\nundefined_variable + 5'],
          },
          {
            cell_type: 'code',
            source: ['# This should still execute\nprint("After error")'],
          },
        ],
        metadata: {
          kernelspec: { name: 'python3' },
        },
        nbformat: 4,
        nbformat_minor: 5,
      };

      await fs.writeFile(notebookPath, JSON.stringify(notebook, null, 2));
      createdFiles.push(notebookPath);

      const executeResult = await server.executeTool('jupyter_execute_notebook', {
        path: notebookPath,
      });

      expect(executeResult.success).toBe(true);
      expect(executeResult.cellsExecuted).toBe(3);
      expect(executeResult.hasErrors).toBe(true);

      // First cell should succeed
      expect(executeResult.results[0].success).toBe(true);
      
      // Second cell should fail
      expect(executeResult.results[1].success).toBe(false);
      expect(executeResult.results[1].error).toBeDefined();
      
      // Third cell should still execute and succeed
      expect(executeResult.results[2].success).toBe(true);
    });
  });

  describe('Session Management', () => {
    it('should list and manage sessions', async () => {
      if (!server) return;

      // Create multiple notebooks and sessions
      const sessions = [];
      for (let i = 1; i <= 3; i++) {
        const notebookName = `test-session-${i}`;
        const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

        await server.executeTool('jupyter_create_notebook', {
          name: notebookName,
          directory: testNotebooksDir,
        });

        createdFiles.push(notebookPath);

        const openResult = await server.executeTool('jupyter_open_notebook', {
          path: notebookPath,
        });

        sessions.push(openResult.sessionId);
        activeSessions.push(openResult.sessionId);
      }

      // List sessions
      const listResult = await server.executeTool('jupyter_list_sessions', {});

      expect(listResult.sessions).toHaveLength(3);
      expect(listResult.count).toBe(3);

      // Each session should have the expected properties
      for (const session of listResult.sessions) {
        expect(session.id).toBeDefined();
        expect(session.path).toContain('test-session-');
        expect(session.kernelId).toBeDefined();
        expect(session.cellCount).toBe(0);
      }
    });

    it('should save notebook state', async () => {
      if (!server) return;

      // Create and open a notebook
      const notebookName = 'test-save-notebook';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      const sessionId = openResult.sessionId;
      activeSessions.push(sessionId);

      // Execute some cells
      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: '# First cell\nprint("Hello from first cell")',
      });

      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: 'x = 42\nprint(f"The answer is {x}")',
      });

      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: '# Markdown cell\nThis is **markdown** content',
        cellType: 'markdown',
      });

      // Save the notebook
      const saveResult = await server.executeTool('jupyter_save_notebook', {
        notebookId: sessionId,
      });

      expect(saveResult.success).toBe(true);
      expect(saveResult.path).toBe(notebookPath);
      expect(saveResult.cellCount).toBe(3);

      // Verify the saved notebook contains our cells
      const content = await fs.readFile(notebookPath, 'utf-8');
      const savedNotebook = JSON.parse(content);

      expect(savedNotebook.cells).toHaveLength(3);
      expect(savedNotebook.cells[0].cell_type).toBe('code');
      expect(savedNotebook.cells[0].source.join('')).toContain('First cell');
      expect(savedNotebook.cells[2].cell_type).toBe('markdown');
      expect(savedNotebook.cells[2].source.join('')).toContain('markdown');
    });
  });

  describe('Error Handling', () => {
    it('should handle non-existent notebook operations', async () => {
      if (!server) return;

      // Try to open non-existent notebook
      await expect(
        server.executeTool('jupyter_open_notebook', {
          path: '/non/existent/path.ipynb',
        })
      ).rejects.toThrow();

      // Try to execute in non-existent session
      await expect(
        server.executeTool('jupyter_execute_cell', {
          notebookId: 'non-existent-session',
          code: 'print("test")',
        })
      ).rejects.toThrow('not found');
    });

    it('should handle invalid notebook creation', async () => {
      if (!server) return;

      // Try to create notebook in non-existent directory
      await expect(
        server.executeTool('jupyter_create_notebook', {
          name: 'test',
          directory: '/non/existent/directory',
        })
      ).rejects.toThrow();

      // Try to create notebook with existing name
      const notebookName = 'duplicate-test';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      await expect(
        server.executeTool('jupyter_create_notebook', {
          name: notebookName,
          directory: testNotebooksDir,
        })
      ).rejects.toThrow('already exists');
    });

    it('should handle kernel management errors', async () => {
      if (!server) return;

      // Try to control non-existent session
      await expect(
        server.executeTool('jupyter_kernel_control', {
          notebookId: 'non-existent-session',
          command: 'restart',
        })
      ).rejects.toThrow('not found');
    });
  });

  describe('Export Functionality', () => {
    it('should export notebook to different formats', async () => {
      if (!server) return;

      // Create and populate a notebook
      const notebookName = 'test-export-notebook';
      const notebookPath = path.join(testNotebooksDir, `${notebookName}.ipynb`);

      await server.executeTool('jupyter_create_notebook', {
        name: notebookName,
        directory: testNotebooksDir,
      });

      createdFiles.push(notebookPath);

      const openResult = await server.executeTool('jupyter_open_notebook', {
        path: notebookPath,
      });

      const sessionId = openResult.sessionId;
      activeSessions.push(sessionId);

      // Add some content
      await server.executeTool('jupyter_execute_cell', {
        notebookId: sessionId,
        code: '# Test Export\nprint("This notebook will be exported")',
      });

      // Save the notebook first
      await server.executeTool('jupyter_save_notebook', {
        notebookId: sessionId,
      });

      // Try to export (this might fail if nbconvert is not available)
      try {
        const exportPath = path.join(testNotebooksDir, 'exported-notebook.html');
        const exportResult = await server.executeTool('jupyter_export', {
          notebookId: sessionId,
          format: 'html',
          outputPath: exportPath,
        });

        expect(exportResult.success).toBe(true);
        expect(exportResult.format).toBe('html');
        expect(exportResult.outputPath).toBe(exportPath);

        createdFiles.push(exportPath);
      } catch (error: any) {
        // nbconvert might not be available
        if (error.message.includes('Export failed')) {
          console.log('⚠️  nbconvert not available for export testing');
        } else {
          throw error;
        }
      }
    });
  });
});