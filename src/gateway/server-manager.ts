/**
 * Manages MCP server lifecycle and connections
 */

import { spawn, ChildProcess } from 'child_process';
import { MCPServerStatus, MCPServerConfig, IMCPServer } from '../types/mcp';
import { ServerConfig } from '../types/config';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { EventEmitter } from 'events';

interface ManagedServer {
  config: MCPServerConfig;
  process?: ChildProcess;
  status: MCPServerStatus;
  instance?: IMCPServer;
  restartCount: number;
  lastError?: string;
}

export class ServerManager extends EventEmitter {
  private servers: Map<string, ManagedServer>;
  private logger: Logger;

  constructor(private config: ServerConfig) {
    super();
    this.logger = createLogger('server-manager');
    this.servers = new Map();
    
    // Initialize server configurations
    for (const [name, serverConfig] of Object.entries(config.servers)) {
      if (serverConfig.enabled) {
        this.servers.set(name, {
          config: {
            name,
            command: serverConfig.command,
            args: serverConfig.args,
            env: serverConfig.env,
          },
          status: {
            name,
            status: 'stopped',
          },
          restartCount: 0,
        });
      }
    }
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing server manager');
    
    // Start servers configured for auto-start
    const promises: Promise<void>[] = [];
    
    for (const [name] of this.servers) {
      const serverConfig = this.config.servers[name];
      if (serverConfig?.autoStart) {
        promises.push(this.startServer(name));
      }
    }
    
    await Promise.allSettled(promises);
    this.logger.info('Server manager initialized');
  }

  async startServer(name: string): Promise<void> {
    const server = this.servers.get(name);
    if (!server) {
      throw new Error(`Server '${name}' not found`);
    }
    
    if (server.status.status === 'running') {
      this.logger.warn('Server already running', { server: name });
      return;
    }
    
    this.logger.info('Starting server', { server: name });
    server.status.status = 'starting';
    
    try {
      // For built-in servers, load them directly
      if (this.isBuiltInServer(name)) {
        await this.startBuiltInServer(name, server);
      } else {
        // For external servers, spawn process
        await this.spawnServerProcess(name, server);
      }
      
      server.status.status = 'running';
      server.status.startTime = new Date();
      server.status.error = undefined;
      server.restartCount = 0;
      
      this.emit('server:started', { name, status: server.status });
      this.logger.info('Server started', { server: name });
    } catch (error) {
      server.status.status = 'error';
      server.status.error = error instanceof Error ? error.message : String(error);
      server.lastError = server.status.error;
      
      this.emit('server:error', { name, error });
      this.logger.error('Failed to start server', { server: name, error });
      
      // Handle restart logic
      await this.handleServerRestart(name, server);
      
      throw error;
    }
  }

  async stopServer(name: string): Promise<void> {
    const server = this.servers.get(name);
    if (!server) {
      throw new Error(`Server '${name}' not found`);
    }
    
    if (server.status.status === 'stopped') {
      this.logger.warn('Server already stopped', { server: name });
      return;
    }
    
    this.logger.info('Stopping server', { server: name });
    
    try {
      if (server.instance) {
        await server.instance.shutdown();
        server.instance = undefined;
      }
      
      if (server.process) {
        await this.stopProcess(server.process);
        server.process = undefined;
      }
      
      server.status.status = 'stopped';
      server.status.startTime = undefined;
      
      this.emit('server:stopped', { name });
      this.logger.info('Server stopped', { server: name });
    } catch (error) {
      this.logger.error('Error stopping server', { server: name, error });
      throw error;
    }
  }

  async restartServer(name: string): Promise<void> {
    await this.stopServer(name);
    await this.startServer(name);
  }

  getServerStatus(name: string): MCPServerStatus | undefined {
    return this.servers.get(name)?.status;
  }

  getServerStatuses(): MCPServerStatus[] {
    return Array.from(this.servers.values()).map(s => s.status);
  }

  getServer(name: string): IMCPServer | undefined {
    return this.servers.get(name)?.instance;
  }

  async shutdown(): Promise<void> {
    this.logger.info('Shutting down all servers');
    
    const promises: Promise<void>[] = [];
    for (const name of this.servers.keys()) {
      promises.push(this.stopServer(name));
    }
    
    await Promise.allSettled(promises);
    this.logger.info('All servers shut down');
  }

  private isBuiltInServer(name: string): boolean {
    // These servers are implemented in this codebase
    const builtInServers = ['memory', 'docker', 'filesystem', 'postgresql', 'redis', 'mongodb', 'kubernetes', 'neo4j', 'jupyter'];
    return builtInServers.includes(name);
  }

  private async startBuiltInServer(name: string, server: ManagedServer): Promise<void> {
    let instance: IMCPServer;
    
    switch (name) {
      case 'memory':
        const { MemoryServer } = await import('../../servers/memory');
        instance = new MemoryServer();
        break;
        
      case 'docker':
        const { DockerServer } = await import('../../servers/docker');
        instance = new DockerServer();
        break;
        
      case 'filesystem':
        const { FilesystemServer } = await import('../../servers/filesystem');
        instance = new FilesystemServer();
        break;
        
      case 'postgresql':
        const { PostgreSQLServer } = await import('../../servers/postgresql');
        instance = new PostgreSQLServer();
        break;
        
      case 'redis':
        const { RedisServer } = await import('../../servers/redis');
        instance = new RedisServer();
        break;
        
      case 'mongodb':
        const { MongoDBServer } = await import('../../servers/mongodb');
        instance = new MongoDBServer();
        break;
        
      case 'kubernetes':
        const { KubernetesServer } = await import('../../servers/kubernetes');
        instance = new KubernetesServer();
        break;
        
      case 'neo4j':
        const { Neo4jServer } = await import('../../servers/neo4j');
        instance = new Neo4jServer();
        break;
        
      case 'jupyter':
        const { JupyterServer } = await import('../../servers/jupyter');
        instance = new JupyterServer();
        break;
        
      default:
        throw new Error(`Unknown built-in server: ${name}`);
    }
    
    await instance.initialize();
    server.instance = instance;
  }

  private async spawnServerProcess(name: string, server: ManagedServer): Promise<void> {
    const env = {
      ...process.env,
      ...server.config.env,
      MCP_SERVER_NAME: name,
    };
    
    const child = spawn(server.config.command, server.config.args || [], {
      env,
      cwd: server.config.workingDirectory || process.cwd(),
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    
    server.process = child;
    
    // Handle process events
    child.on('error', (error) => {
      this.logger.error('Server process error', { server: name, error });
      server.status.status = 'error';
      server.status.error = error.message;
      this.emit('server:error', { name, error });
    });
    
    child.on('exit', (code, signal) => {
      this.logger.warn('Server process exited', { server: name, code, signal });
      server.status.status = 'stopped';
      server.process = undefined;
      
      if (code !== 0) {
        this.handleServerRestart(name, server);
      }
    });
    
    // Capture output
    child.stdout?.on('data', (data) => {
      this.logger.debug('Server output', { server: name, data: data.toString() });
    });
    
    child.stderr?.on('data', (data) => {
      this.logger.error('Server error output', { server: name, data: data.toString() });
    });
    
    // Wait for server to be ready (simplified - could be improved)
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 2000); // Give server 2 seconds to start
    });
  }

  private async stopProcess(process: ChildProcess): Promise<void> {
    return new Promise((resolve) => {
      if (!process.killed) {
        process.on('exit', () => resolve());
        process.kill('SIGTERM');
        
        // Force kill after timeout
        setTimeout(() => {
          if (!process.killed) {
            process.kill('SIGKILL');
          }
        }, 5000);
      } else {
        resolve();
      }
    });
  }

  private async handleServerRestart(name: string, server: ManagedServer): Promise<void> {
    const serverConfig = this.config.servers[name];
    
    if (serverConfig?.restartOnFailure && server.restartCount < serverConfig.maxRestarts) {
      server.restartCount++;
      this.logger.info('Attempting to restart server', { 
        server: name, 
        attempt: server.restartCount 
      });
      
      setTimeout(() => {
        this.startServer(name).catch((error) => {
          this.logger.error('Failed to restart server', { server: name, error });
        });
      }, 5000); // Wait 5 seconds before restart
    }
  }
}