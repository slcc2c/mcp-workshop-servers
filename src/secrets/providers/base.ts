/**
 * Base secret provider implementation
 */

import { ISecretProvider, Secret, SecretMetadata, SecretProvider, SecretError } from '../types';
import { Logger } from '../../types/logger';
import { createLogger } from '../../utils/logger';

export abstract class BaseSecretProvider implements ISecretProvider {
  protected logger: Logger;
  protected initialized = false;

  constructor(
    public readonly name: SecretProvider,
    protected config: Record<string, any> = {}
  ) {
    this.logger = createLogger(`secrets:${name}`);
  }

  async initialize(): Promise<void> {
    if (this.initialized) {
      return;
    }

    this.logger.info('Initializing secret provider', { provider: this.name });

    try {
      await this.doInitialize();
      this.initialized = true;
      this.logger.info('Secret provider initialized', { provider: this.name });
    } catch (error) {
      this.logger.error('Failed to initialize secret provider', { 
        provider: this.name, 
        error 
      });
      throw new SecretError(
        `Failed to initialize ${this.name} provider`,
        this.name,
        'INIT_ERROR',
        error as Error
      );
    }
  }

  async shutdown(): Promise<void> {
    if (!this.initialized) {
      return;
    }

    this.logger.info('Shutting down secret provider', { provider: this.name });

    try {
      await this.doShutdown();
      this.initialized = false;
      this.logger.info('Secret provider shut down', { provider: this.name });
    } catch (error) {
      this.logger.error('Error during secret provider shutdown', { 
        provider: this.name, 
        error 
      });
    }
  }

  async isAvailable(): Promise<boolean> {
    try {
      return await this.checkAvailability();
    } catch (error) {
      this.logger.warn('Secret provider not available', { 
        provider: this.name, 
        error 
      });
      return false;
    }
  }

  // Abstract methods to be implemented by providers
  abstract getSecret(path: string, field?: string): Promise<Secret>;
  protected abstract doInitialize(): Promise<void>;
  protected abstract doShutdown(): Promise<void>;
  protected abstract checkAvailability(): Promise<boolean>;

  // Optional methods with default implementations
  async setSecret(_path: string, _value: string, _field?: string): Promise<void> {
    throw new SecretError(
      `${this.name} provider does not support setting secrets`,
      this.name,
      'NOT_SUPPORTED'
    );
  }

  async deleteSecret(_path: string, _field?: string): Promise<void> {
    throw new SecretError(
      `${this.name} provider does not support deleting secrets`,
      this.name,
      'NOT_SUPPORTED'
    );
  }

  async listSecrets(_prefix?: string): Promise<SecretMetadata[]> {
    throw new SecretError(
      `${this.name} provider does not support listing secrets`,
      this.name,
      'NOT_SUPPORTED'
    );
  }

  async rotateSecret(_path: string, _field?: string): Promise<Secret> {
    throw new SecretError(
      `${this.name} provider does not support rotating secrets`,
      this.name,
      'NOT_SUPPORTED'
    );
  }

  /**
   * Create secret metadata
   */
  protected createSecretMetadata(
    name: string,
    additionalData?: Partial<SecretMetadata>
  ): SecretMetadata {
    return {
      name,
      provider: this.name,
      lastUpdated: new Date(),
      ...additionalData,
    };
  }

  /**
   * Create secret object
   */
  protected createSecret(
    value: string,
    metadata: SecretMetadata,
    ttl?: number
  ): Secret {
    const secret: Secret = {
      value,
      metadata,
    };

    if (ttl && ttl > 0) {
      secret.expiresAt = new Date(Date.now() + ttl * 1000);
    }

    return secret;
  }

  /**
   * Sanitize secret value for logging
   */
  protected sanitizeForLogging(value: string): string {
    if (!value) return '<empty>';
    if (value.length <= 8) return '<redacted>';
    return `${value.substring(0, 4)}...<redacted>`;
  }
}