/**
 * Central secrets manager that coordinates multiple providers
 */

import { 
  ISecretProvider, 
  Secret, 
  SecretProvider, 
  SecretReference,
  SecretsConfig,
  SecretError,
  SecretProviderError,
  SecretAuditEvent,
  SecretMetadata,
  // OnePasswordConfig,
  OnePasswordConfigSchema,
} from './types';
import { EnvironmentSecretProvider } from './providers/environment';
import { OnePasswordSecretProvider } from './providers/onepassword';
import { SecretCache } from './cache';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';
import { EventEmitter } from 'events';

export class SecretsManager extends EventEmitter {
  private providers = new Map<SecretProvider, ISecretProvider>();
  private cache: SecretCache;
  private logger: Logger;
  private auditLog: SecretAuditEvent[] = [];
  
  constructor(private config: SecretsConfig) {
    super();
    this.logger = createLogger('secrets:manager');
    this.cache = new SecretCache(config.cache);
  }

  /**
   * Initialize all configured providers
   */
  async initialize(): Promise<void> {
    this.logger.info('Initializing secrets manager');

    // Always initialize environment provider as fallback
    const envProvider = new EnvironmentSecretProvider();
    await this.initializeProvider(envProvider);

    // Initialize configured providers
    for (const providerConfig of this.config.providers) {
      if (!providerConfig.enabled) {
        continue;
      }

      try {
        const provider = await this.createProvider(providerConfig.type, providerConfig.config);
        await this.initializeProvider(provider);
      } catch (error) {
        this.logger.error('Failed to initialize provider', { 
          provider: providerConfig.type, 
          error 
        });
        // Continue with other providers
      }
    }

    this.logger.info('Secrets manager initialized', { 
      providers: Array.from(this.providers.keys()) 
    });
  }

  /**
   * Get a secret value
   */
  async getSecret(reference: string | SecretReference): Promise<string> {
    const ref = this.parseReference(reference);
    const cacheKey = SecretCache.createKey(ref.provider, ref.path, ref.field);

    // Check cache first
    const cached = this.cache.get(cacheKey);
    if (cached) {
      this.auditAccess(ref.path, ref.provider, true);
      return cached.value;
    }

    // Get from provider
    const provider = this.getProvider(ref.provider);
    if (!provider) {
      throw new SecretProviderError(
        `Provider not available: ${ref.provider}`,
        ref.provider
      );
    }

    try {
      const secret = await provider.getSecret(ref.path, ref.field);
      
      // Cache the secret
      this.cache.set(cacheKey, secret);
      
      // Audit the access
      this.auditAccess(ref.path, ref.provider, true);
      
      return secret.value;
    } catch (error) {
      this.auditAccess(ref.path, ref.provider, false, error as Error);
      throw error;
    }
  }

  /**
   * Get multiple secrets
   */
  async getSecrets(references: Array<string | SecretReference>): Promise<Map<string, string>> {
    const results = new Map<string, string>();
    
    // Fetch in parallel
    const promises = references.map(async (ref) => {
      try {
        const value = await this.getSecret(ref);
        const key = typeof ref === 'string' ? ref : `${ref.path}${ref.field ? `.${ref.field}` : ''}`;
        results.set(key, value);
      } catch (error) {
        this.logger.error('Failed to get secret', { reference: ref, error });
        // Continue with other secrets
      }
    });

    await Promise.all(promises);
    return results;
  }

  /**
   * Set a secret value
   */
  async setSecret(
    reference: string | SecretReference, 
    value: string
  ): Promise<void> {
    const ref = this.parseReference(reference);
    const provider = this.getProvider(ref.provider);

    if (!provider) {
      throw new SecretProviderError(
        `Provider not available: ${ref.provider}`,
        ref.provider
      );
    }

    if (!provider.setSecret) {
      throw new SecretProviderError(
        `Provider does not support setting secrets: ${ref.provider}`,
        ref.provider
      );
    }

    await provider.setSecret(ref.path, value, ref.field);
    
    // Invalidate cache
    const cacheKey = SecretCache.createKey(ref.provider, ref.path, ref.field);
    this.cache.invalidate(cacheKey);
    
    // Audit the action
    this.auditAction('create', ref.path, ref.provider, true);
  }

  /**
   * Delete a secret
   */
  async deleteSecret(reference: string | SecretReference): Promise<void> {
    const ref = this.parseReference(reference);
    const provider = this.getProvider(ref.provider);

    if (!provider) {
      throw new SecretProviderError(
        `Provider not available: ${ref.provider}`,
        ref.provider
      );
    }

    if (!provider.deleteSecret) {
      throw new SecretProviderError(
        `Provider does not support deleting secrets: ${ref.provider}`,
        ref.provider
      );
    }

    await provider.deleteSecret(ref.path, ref.field);
    
    // Invalidate cache
    const cacheKey = SecretCache.createKey(ref.provider, ref.path, ref.field);
    this.cache.invalidate(cacheKey);
    
    // Audit the action
    this.auditAction('delete', ref.path, ref.provider, true);
  }

  /**
   * List available secrets
   */
  async listSecrets(
    provider?: SecretProvider, 
    prefix?: string
  ): Promise<SecretMetadata[]> {
    const targetProvider = provider || this.config.defaultProvider;
    const providerInstance = this.getProvider(targetProvider);

    if (!providerInstance) {
      throw new SecretProviderError(
        `Provider not available: ${targetProvider}`,
        targetProvider
      );
    }

    if (!providerInstance.listSecrets) {
      throw new SecretProviderError(
        `Provider does not support listing secrets: ${targetProvider}`,
        targetProvider
      );
    }

    return providerInstance.listSecrets(prefix);
  }

  /**
   * Rotate a secret
   */
  async rotateSecret(reference: string | SecretReference): Promise<Secret> {
    const ref = this.parseReference(reference);
    const provider = this.getProvider(ref.provider);

    if (!provider) {
      throw new SecretProviderError(
        `Provider not available: ${ref.provider}`,
        ref.provider
      );
    }

    if (!provider.rotateSecret) {
      throw new SecretProviderError(
        `Provider does not support rotating secrets: ${ref.provider}`,
        ref.provider
      );
    }

    const newSecret = await provider.rotateSecret(ref.path, ref.field);
    
    // Invalidate cache
    const cacheKey = SecretCache.createKey(ref.provider, ref.path, ref.field);
    this.cache.invalidate(cacheKey);
    
    // Cache new value
    this.cache.set(cacheKey, newSecret);
    
    // Audit the action
    this.auditAction('rotate', ref.path, ref.provider, true);
    
    return newSecret;
  }

  /**
   * Clear cache
   */
  clearCache(): void {
    this.cache.clear();
    this.logger.info('Secret cache cleared');
  }

  /**
   * Get cache statistics
   */
  getCacheStats() {
    return this.cache.getStats();
  }

  /**
   * Get audit log
   */
  getAuditLog(limit?: number): SecretAuditEvent[] {
    const log = [...this.auditLog].reverse(); // Most recent first
    return limit ? log.slice(0, limit) : log;
  }

  /**
   * Clear audit log
   */
  clearAuditLog(): void {
    this.auditLog = [];
    this.logger.info('Audit log cleared');
  }

  /**
   * Get available providers
   */
  getAvailableProviders(): SecretProvider[] {
    return Array.from(this.providers.keys());
  }

  /**
   * Check if a provider is available
   */
  async isProviderAvailable(provider: SecretProvider): Promise<boolean> {
    const instance = this.providers.get(provider);
    return instance ? instance.isAvailable() : false;
  }

  /**
   * Shutdown all providers
   */
  async shutdown(): Promise<void> {
    this.logger.info('Shutting down secrets manager');
    
    const promises: Promise<void>[] = [];
    for (const provider of this.providers.values()) {
      promises.push(provider.shutdown());
    }
    
    await Promise.allSettled(promises);
    this.providers.clear();
    this.cache.clear();
    
    this.logger.info('Secrets manager shut down');
  }

  /**
   * Create a provider instance
   */
  private async createProvider(
    type: SecretProvider, 
    config?: Record<string, any>
  ): Promise<ISecretProvider> {
    switch (type) {
      case SecretProvider.ENVIRONMENT:
        return new EnvironmentSecretProvider(config);
        
      case SecretProvider.ONEPASSWORD:
        const opConfig = OnePasswordConfigSchema.parse(config || {});
        return new OnePasswordSecretProvider(opConfig);
        
      default:
        throw new SecretProviderError(
          `Unknown provider type: ${type}`,
          type
        );
    }
  }

  /**
   * Initialize a provider
   */
  private async initializeProvider(provider: ISecretProvider): Promise<void> {
    try {
      await provider.initialize();
      if (await provider.isAvailable()) {
        this.providers.set(provider.name, provider);
        this.logger.info('Provider initialized', { provider: provider.name });
      } else {
        this.logger.warn('Provider not available', { provider: provider.name });
      }
    } catch (error) {
      this.logger.error('Failed to initialize provider', { 
        provider: provider.name, 
        error 
      });
      throw error;
    }
  }

  /**
   * Get a provider instance
   */
  private getProvider(type: SecretProvider): ISecretProvider | undefined {
    return this.providers.get(type);
  }

  /**
   * Parse a secret reference
   */
  private parseReference(reference: string | SecretReference): SecretReference {
    if (typeof reference === 'string') {
      // Parse string format: provider:path:field or path
      const parts = reference.split(':');
      
      if (parts.length === 1) {
        // Just a path, use default provider
        return {
          provider: this.config.defaultProvider,
          path: parts[0],
        };
      } else if (parts.length === 2) {
        // provider:path
        return {
          provider: parts[0] as SecretProvider,
          path: parts[1],
        };
      } else if (parts.length === 3) {
        // provider:path:field
        return {
          provider: parts[0] as SecretProvider,
          path: parts[1],
          field: parts[2],
        };
      } else {
        throw new SecretError(
          `Invalid secret reference format: ${reference}`,
          SecretProvider.ENVIRONMENT,
          'INVALID_REFERENCE'
        );
      }
    }
    
    return reference;
  }

  /**
   * Audit a secret access
   */
  private auditAccess(
    secretName: string, 
    provider: SecretProvider, 
    success: boolean, 
    error?: Error
  ): void {
    if (!this.config.audit.enabled || !this.config.audit.logAccess) {
      return;
    }

    const event: SecretAuditEvent = {
      timestamp: new Date(),
      action: 'access',
      secretName,
      provider,
      success,
      error: error?.message,
    };

    this.auditLog.push(event);
    this.emit('audit', event);
  }

  /**
   * Audit a secret action
   */
  private auditAction(
    action: 'create' | 'delete' | 'rotate',
    secretName: string,
    provider: SecretProvider,
    success: boolean,
    error?: Error
  ): void {
    if (!this.config.audit.enabled) {
      return;
    }

    const event: SecretAuditEvent = {
      timestamp: new Date(),
      action,
      secretName,
      provider,
      success,
      error: error?.message,
    };

    this.auditLog.push(event);
    this.emit('audit', event);
  }
}