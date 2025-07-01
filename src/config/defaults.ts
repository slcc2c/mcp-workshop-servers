/**
 * Default configuration values
 */

import { ServerConfig } from '../types/config';
import { SecretProvider } from '../secrets/types';

export const defaultConfig: ServerConfig = {
  gateway: {
    port: 3000,
    host: 'localhost',
    cors: {
      enabled: true,
      origins: ['*'],
    },
    rateLimit: {
      enabled: true,
      windowMs: 60000, // 1 minute
      max: 100,
    },
  },
  servers: {
    memory: {
      enabled: true,
      command: 'node',
      args: ['servers/memory/index.js'],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    github: {
      enabled: true,
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-github'],
      env: {
        GITHUB_PERSONAL_ACCESS_TOKEN: process.env.GITHUB_TOKEN || '',
      },
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    filesystem: {
      enabled: true,
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem', process.cwd()],
      autoStart: true,
      restartOnFailure: true,
      maxRestarts: 3,
    },
    docker: {
      enabled: true,
      command: 'node',
      args: ['servers/docker/index.js'],
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
      enabled: false,
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
      enabled: false,
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