/**
 * Configuration management utilities
 */

import { config as dotenvConfig } from 'dotenv';
import { EnvConfigSchema, EnvConfig, ServerConfig, defaultConfig } from '../types/config';
import { logger } from './logger';
import fs from 'fs/promises';
import path from 'path';

// Load environment variables
dotenvConfig();

// Parse and validate environment configuration
export function loadEnvConfig(): EnvConfig {
  try {
    const parsed = EnvConfigSchema.parse(process.env);
    logger.info('Environment configuration loaded successfully');
    return parsed;
  } catch (error) {
    logger.error('Failed to parse environment configuration', { error });
    throw new Error('Invalid environment configuration');
  }
}

// Load server configuration from file or use defaults
export async function loadServerConfig(configPath?: string): Promise<ServerConfig> {
  if (configPath) {
    try {
      const configFile = await fs.readFile(configPath, 'utf-8');
      const config = JSON.parse(configFile) as ServerConfig;
      logger.info('Server configuration loaded from file', { path: configPath });
      return { ...defaultConfig, ...config };
    } catch (error) {
      logger.warn('Failed to load configuration file, using defaults', { error, path: configPath });
    }
  }
  
  return defaultConfig;
}

// Get configuration value with fallback
export function getConfig<T>(key: string, fallback: T): T {
  const value = process.env[key];
  if (value === undefined) {
    return fallback;
  }
  
  // Try to parse as JSON for complex types
  try {
    return JSON.parse(value) as T;
  } catch {
    return value as unknown as T;
  }
}

// Configuration helpers
export const config = {
  env: loadEnvConfig(),
  
  isDevelopment: () => config.env.NODE_ENV === 'development',
  isProduction: () => config.env.NODE_ENV === 'production',
  isTest: () => config.env.NODE_ENV === 'test',
  
  getPort: () => parseInt(config.env.PORT, 10),
  getLogLevel: () => config.env.LOG_LEVEL,
  
  getGitHubToken: () => config.env.GITHUB_TOKEN,
  hasGitHubToken: () => !!config.env.GITHUB_TOKEN,
  
  getDatabaseUrl: (db: 'postgres' | 'redis' | 'mongodb' | 'neo4j') => {
    const urlMap = {
      postgres: config.env.POSTGRES_URL,
      redis: config.env.REDIS_URL,
      mongodb: config.env.MONGODB_URL,
      neo4j: config.env.NEO4J_URL,
    };
    return urlMap[db];
  },
  
  getAllowedPaths: () => {
    const paths = config.env.ALLOWED_PATHS?.split(',').map(p => p.trim()) || [];
    return paths.length > 0 ? paths : [process.cwd()];
  },
  
  getMaxFileSize: () => parseInt(config.env.MAX_FILE_SIZE, 10),
  getMaxConcurrentOps: () => parseInt(config.env.MAX_CONCURRENT_OPERATIONS, 10),
  getRequestTimeout: () => parseInt(config.env.REQUEST_TIMEOUT, 10),
  getCacheTTL: () => parseInt(config.env.CACHE_TTL, 10),
};

// Export singleton instance
export const envConfig = config.env;

// Create default directories
export async function ensureDirectories(): Promise<void> {
  const directories = [
    'logs',
    'tmp',
    'config',
    'data',
  ];
  
  for (const dir of directories) {
    try {
      await fs.mkdir(dir, { recursive: true });
    } catch (error) {
      logger.error('Failed to create directory', { dir, error });
    }
  }
}