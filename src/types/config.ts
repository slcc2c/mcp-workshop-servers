/**
 * Configuration types for MCP Workshop Servers
 */

import { z } from 'zod';

// Environment configuration
export const EnvConfigSchema = z.object({
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.string().default('3000'),
  LOG_LEVEL: z.enum(['error', 'warn', 'info', 'debug']).default('info'),
  
  // GitHub configuration
  GITHUB_TOKEN: z.string().optional(),
  GITHUB_API_URL: z.string().default('https://api.github.com'),
  
  // Database configuration
  POSTGRES_URL: z.string().optional(),
  REDIS_URL: z.string().optional(),
  MONGODB_URL: z.string().optional(),
  NEO4J_URL: z.string().optional(),
  
  // Docker configuration
  DOCKER_HOST: z.string().default('unix:///var/run/docker.sock'),
  DOCKER_API_VERSION: z.string().optional(),
  
  // Security configuration
  AUTH_SECRET: z.string().optional(),
  ALLOWED_PATHS: z.string().optional(), // Comma-separated list
  MAX_FILE_SIZE: z.string().default('10485760'), // 10MB default
  
  // Performance configuration
  MAX_CONCURRENT_OPERATIONS: z.string().default('10'),
  REQUEST_TIMEOUT: z.string().default('30000'), // 30 seconds
  CACHE_TTL: z.string().default('3600'), // 1 hour
});

export type EnvConfig = z.infer<typeof EnvConfigSchema>;

// Server configuration
export interface ServerConfig {
  gateway: GatewayConfig;
  servers: Record<string, MCPServerInstanceConfig>;
  security: SecurityConfig;
  performance: PerformanceConfig;
}

export interface GatewayConfig {
  port: number;
  host: string;
  cors: {
    enabled: boolean;
    origins: string[];
  };
  rateLimit: {
    enabled: boolean;
    windowMs: number;
    max: number;
  };
}

export interface MCPServerInstanceConfig {
  enabled: boolean;
  command: string;
  args?: string[];
  env?: Record<string, string>;
  autoStart: boolean;
  restartOnFailure: boolean;
  maxRestarts: number;
}

export interface SecurityConfig {
  authentication: {
    enabled: boolean;
    type: 'token' | 'oauth' | 'none';
  };
  encryption: {
    enabled: boolean;
    algorithm: string;
  };
  audit: {
    enabled: boolean;
    logPath: string;
  };
}

export interface PerformanceConfig {
  maxConcurrentRequests: number;
  requestTimeout: number;
  caching: {
    enabled: boolean;
    ttl: number;
    maxSize: number;
  };
  monitoring: {
    enabled: boolean;
    metricsPort: number;
  };
}

// File system configuration
export interface FileSystemConfig {
  allowedPaths: string[];
  blockedPaths: string[];
  maxFileSize: number;
  allowedExtensions?: string[];
  blockedExtensions?: string[];
}

// Docker configuration
export interface DockerConfig {
  socketPath: string;
  apiVersion?: string;
  defaultLimits: {
    memory: string;
    cpus: string;
  };
  allowedImages: string[];
  networks: string[];
}

// Memory server configuration
export interface MemoryConfig {
  storageType: 'in-memory' | 'persistent';
  storagePath?: string;
  maxEntries: number;
  maxSizeBytes: number;
  ttl: number;
}

// Default configuration
export const defaultConfig: ServerConfig = {
  gateway: {
    port: 3000,
    host: '0.0.0.0',
    cors: {
      enabled: true,
      origins: ['http://localhost:*'],
    },
    rateLimit: {
      enabled: true,
      windowMs: 60000, // 1 minute
      max: 100,
    },
  },
  servers: {
    github: {
      enabled: true,
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-github'],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    filesystem: {
      enabled: true,
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem'],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    memory: {
      enabled: true,
      command: 'node',
      args: ['./dist/servers/memory/index.js'],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    docker: {
      enabled: true,
      command: 'node',
      args: ['./dist/servers/docker/index.js'],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
  },
  security: {
    authentication: {
      enabled: false,
      type: 'none',
    },
    encryption: {
      enabled: false,
      algorithm: 'aes-256-gcm',
    },
    audit: {
      enabled: true,
      logPath: './logs/audit.log',
    },
  },
  performance: {
    maxConcurrentRequests: 100,
    requestTimeout: 30000,
    caching: {
      enabled: true,
      ttl: 3600,
      maxSize: 1000,
    },
    monitoring: {
      enabled: true,
      metricsPort: 9090,
    },
  },
};