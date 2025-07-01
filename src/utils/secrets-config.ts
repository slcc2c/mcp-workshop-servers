/**
 * Secrets-aware configuration utilities
 */

import { config as dotenvConfig } from 'dotenv';
import { EnvConfigSchema, EnvConfig, ServerConfig, SecretsConfig } from '../types/config';
import { SecretsManager, SecretProvider } from '../secrets';
import { createLogger } from './logger';
// import fs from 'fs/promises';
// import path from 'path';

const logger = createLogger('config:secrets');

// Load environment variables
dotenvConfig();

/**
 * Configuration manager with secrets integration
 */
export class SecureConfigManager {
  private secretsManager?: SecretsManager;
  private envConfig: EnvConfig;
  private serverConfig?: ServerConfig;
  private secretCache = new Map<string, string>();

  constructor() {
    // Load initial environment config
    this.envConfig = this.loadEnvConfig();
  }

  /**
   * Initialize with secrets manager
   */
  async initialize(serverConfig?: ServerConfig): Promise<void> {
    this.serverConfig = serverConfig;
    
    // Create secrets configuration from environment
    const secretsConfig = this.buildSecretsConfig();
    
    // Initialize secrets manager
    this.secretsManager = new SecretsManager(secretsConfig);
    await this.secretsManager.initialize();
    
    logger.info('Secure configuration manager initialized');
  }

  /**
   * Get configuration value with secrets resolution
   */
  async get<T = string>(key: string, defaultValue?: T): Promise<T> {
    // Check cache first
    if (this.secretCache.has(key)) {
      return this.secretCache.get(key) as T;
    }

    // Check if it's a secret reference
    const value = process.env[key];
    if (value && this.isSecretReference(value)) {
      try {
        const secretValue = await this.resolveSecret(value);
        this.secretCache.set(key, secretValue);
        return secretValue as T;
      } catch (error) {
        logger.error('Failed to resolve secret', { key, error });
        if (defaultValue !== undefined) {
          return defaultValue;
        }
        throw error;
      }
    }

    // Return regular environment value
    if (value !== undefined) {
      try {
        return JSON.parse(value) as T;
      } catch {
        return value as T;
      }
    }

    // Return default value
    if (defaultValue !== undefined) {
      return defaultValue;
    }

    throw new Error(`Configuration key not found: ${key}`);
  }

  /**
   * Get GitHub token with secrets resolution
   */
  async getGitHubToken(): Promise<string | undefined> {
    const token = await this.get('GITHUB_TOKEN');
    if (token) return token;
    
    // Try 1Password if configured
    if (this.secretsManager && await this.secretsManager.isProviderAvailable(SecretProvider.ONEPASSWORD)) {
      try {
        return await this.secretsManager.getSecret({
          provider: SecretProvider.ONEPASSWORD,
          path: 'GitHub',
          field: 'token'
        });
      } catch (error) {
        logger.warn('Failed to get GitHub token from 1Password', { error });
      }
    }
    
    return undefined;
  }

  /**
   * Get database URL with secrets resolution
   */
  async getDatabaseUrl(db: 'postgres' | 'redis' | 'mongodb' | 'neo4j'): Promise<string | undefined> {
    const urlMap = {
      postgres: 'POSTGRES_URL',
      redis: 'REDIS_URL',
      mongodb: 'MONGODB_URL',
      neo4j: 'NEO4J_URL',
    };
    
    const url = await this.get(urlMap[db]);
    if (url) return url;
    
    // Try 1Password if configured
    if (this.secretsManager && await this.secretsManager.isProviderAvailable(SecretProvider.ONEPASSWORD)) {
      try {
        return await this.secretsManager.getSecret({
          provider: SecretProvider.ONEPASSWORD,
          path: `Database/${db}`,
          field: 'url'
        });
      } catch (error) {
        logger.warn(`Failed to get ${db} URL from 1Password`, { error });
      }
    }
    
    return undefined;
  }

  /**
   * Get all secrets for a server
   */
  async getServerSecrets(serverName: string): Promise<Record<string, string>> {
    const secrets: Record<string, string> = {};
    
    // Get server-specific environment variables
    const serverEnvPrefix = `${serverName.toUpperCase()}_`;
    for (const [key, value] of Object.entries(process.env)) {
      if (key.startsWith(serverEnvPrefix)) {
        try {
          secrets[key] = await this.get(key, value);
        } catch (error) {
          logger.warn(`Failed to resolve secret for ${key}`, { error });
        }
      }
    }
    
    // Get common secrets based on server type
    switch (serverName.toLowerCase()) {
      case 'github':
        const githubToken = await this.getGitHubToken();
        if (githubToken) {
          secrets.GITHUB_TOKEN = githubToken;
        }
        break;
        
      case 'postgres':
      case 'redis':
      case 'mongodb':
      case 'neo4j':
        const dbUrl = await this.getDatabaseUrl(serverName.toLowerCase() as any);
        if (dbUrl) {
          secrets[`${serverName.toUpperCase()}_URL`] = dbUrl;
        }
        break;
    }
    
    return secrets;
  }

  /**
   * Refresh secrets cache
   */
  async refreshSecrets(): Promise<void> {
    this.secretCache.clear();
    if (this.secretsManager) {
      this.secretsManager.clearCache();
    }
    logger.info('Secrets cache refreshed');
  }

  /**
   * Get secrets manager instance
   */
  getSecretsManager(): SecretsManager | undefined {
    return this.secretsManager;
  }

  /**
   * Load environment configuration
   */
  private loadEnvConfig(): EnvConfig {
    try {
      const parsed = EnvConfigSchema.parse(process.env);
      logger.info('Environment configuration loaded');
      return parsed;
    } catch (error) {
      logger.error('Failed to parse environment configuration', { error });
      throw new Error('Invalid environment configuration');
    }
  }

  /**
   * Build secrets configuration
   */
  private buildSecretsConfig(): SecretsConfig {
    const config: SecretsConfig = {
      defaultProvider: this.envConfig.SECRETS_DEFAULT_PROVIDER,
      providers: [],
      cache: {
        enabled: this.envConfig.SECRETS_CACHE_ENABLED === 'true',
        maxSize: 100,
        ttl: parseInt(this.envConfig.SECRETS_CACHE_TTL, 10),
      },
      audit: {
        enabled: this.serverConfig?.security.audit.enabled || false,
        logAccess: false,
        logRotation: true,
      },
    };

    // Always add environment provider
    config.providers.push({
      type: SecretProvider.ENVIRONMENT,
      enabled: true,
    });

    // Add 1Password provider if configured
    if (
      this.envConfig.ONEPASSWORD_SERVICE_ACCOUNT_TOKEN ||
      this.envConfig.ONEPASSWORD_CONNECT_TOKEN
    ) {
      config.providers.push({
        type: SecretProvider.ONEPASSWORD,
        enabled: true,
        config: {
          vault: this.envConfig.ONEPASSWORD_VAULT,
          allowedVaults: this.envConfig.ONEPASSWORD_ALLOWED_VAULTS?.split(',').map(v => v.trim()),
          serviceAccountToken: this.envConfig.ONEPASSWORD_SERVICE_ACCOUNT_TOKEN,
          connectHost: this.envConfig.ONEPASSWORD_CONNECT_HOST,
          connectToken: this.envConfig.ONEPASSWORD_CONNECT_TOKEN,
          cacheTtl: parseInt(this.envConfig.SECRETS_CACHE_TTL, 10),
        },
      });
    }

    return config;
  }

  /**
   * Check if a value is a secret reference
   */
  private isSecretReference(value: string): boolean {
    // Secret references start with secret:// or have provider prefix
    return (
      value.startsWith('secret://') ||
      value.startsWith('env:') ||
      value.startsWith('1password:') ||
      value.startsWith('aws:') ||
      value.startsWith('vault:') ||
      value.startsWith('azure:')
    );
  }

  /**
   * Resolve a secret reference
   */
  private async resolveSecret(reference: string): Promise<string> {
    if (!this.secretsManager) {
      throw new Error('Secrets manager not initialized');
    }

    // Handle secret:// URLs
    if (reference.startsWith('secret://')) {
      reference = reference.substring(9);
    }

    return this.secretsManager.getSecret(reference);
  }
}

// Export singleton instance
export const secureConfig = new SecureConfigManager();

// Helper functions for backward compatibility
export const config = {
  env: secureConfig['envConfig'],
  
  isDevelopment: () => config.env.NODE_ENV === 'development',
  isProduction: () => config.env.NODE_ENV === 'production',
  isTest: () => config.env.NODE_ENV === 'test',
  
  getPort: () => parseInt(config.env.PORT, 10),
  getLogLevel: () => config.env.LOG_LEVEL,
  
  // Async versions with secrets resolution
  getGitHubToken: () => secureConfig.getGitHubToken(),
  getDatabaseUrl: (db: 'postgres' | 'redis' | 'mongodb' | 'neo4j') => 
    secureConfig.getDatabaseUrl(db),
  
  getAllowedPaths: () => {
    const paths = config.env.ALLOWED_PATHS?.split(',').map(p => p.trim()) || [];
    return paths.length > 0 ? paths : [process.cwd()];
  },
  
  getMaxFileSize: () => parseInt(config.env.MAX_FILE_SIZE, 10),
  getMaxConcurrentOps: () => parseInt(config.env.MAX_CONCURRENT_OPERATIONS, 10),
  getRequestTimeout: () => parseInt(config.env.REQUEST_TIMEOUT, 10),
  getCacheTTL: () => parseInt(config.env.CACHE_TTL, 10),
};