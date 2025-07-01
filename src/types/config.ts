/**
 * Configuration types for MCP Workshop Servers
 */

import { z } from 'zod';
import { SecretProvider, SecretsConfigSchema } from '../secrets/types';

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
  
  // 1Password configuration
  ONEPASSWORD_VAULT: z.string().optional(),
  ONEPASSWORD_ALLOWED_VAULTS: z.string().optional(), // Comma-separated list
  ONEPASSWORD_SERVICE_ACCOUNT_TOKEN: z.string().optional(),
  ONEPASSWORD_CONNECT_HOST: z.string().optional(),
  ONEPASSWORD_CONNECT_TOKEN: z.string().optional(),
  
  // Secrets management
  SECRETS_DEFAULT_PROVIDER: z.nativeEnum(SecretProvider).default(SecretProvider.ENVIRONMENT),
  SECRETS_CACHE_ENABLED: z.string().default('true'),
  SECRETS_CACHE_TTL: z.string().default('300'), // 5 minutes
});

export type EnvConfig = z.infer<typeof EnvConfigSchema>;

// Server configuration
export interface ServerConfig {
  gateway: GatewayConfig;
  servers: Record<string, MCPServerInstanceConfig>;
  security: SecurityConfig;
  performance: PerformanceConfig;
  secrets: SecretsConfig;
}

// Import the SecretsConfig type
export type SecretsConfig = z.infer<typeof SecretsConfigSchema>;

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
      command: 'node',
      args: ['./dist/servers/filesystem/index.js'],
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
    postgresql: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/postgresql/index.js'],
      autoStart: false,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    redis: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/redis/index.js'],
      autoStart: false,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    mongodb: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/mongodb/index.js'],
      autoStart: false,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    kubernetes: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/kubernetes/index.js'],
      autoStart: false,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    neo4j: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/neo4j/index.js'],
      autoStart: false,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    jupyter: {
      enabled: false,
      command: 'node',
      args: ['./dist/servers/jupyter/index.js'],
      autoStart: false,
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
  secrets: {
    defaultProvider: SecretProvider.ENVIRONMENT,
    providers: [],
    cache: {
      enabled: true,
      maxSize: 100,
      ttl: 300,
    },
    audit: {
      enabled: false,
      logAccess: false,
      logRotation: true,
    },
  },
};