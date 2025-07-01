/**
 * Environment variable secret provider
 */

import { BaseSecretProvider } from './base';
import { Secret, SecretProvider, SecretNotFoundError } from '../types';

export class EnvironmentSecretProvider extends BaseSecretProvider {
  constructor(config: Record<string, any> = {}) {
    super(SecretProvider.ENVIRONMENT, config);
  }

  async getSecret(path: string, field?: string): Promise<Secret> {
    const envKey = field || path;
    const value = process.env[envKey];

    if (value === undefined) {
      throw new SecretNotFoundError(envKey, this.name);
    }

    this.logger.debug('Retrieved secret from environment', { 
      key: envKey,
      hasValue: !!value 
    });

    const metadata = this.createSecretMetadata(envKey, {
      path: envKey,
    });

    return this.createSecret(value, metadata);
  }

  protected async doInitialize(): Promise<void> {
    // No initialization needed for environment provider
  }

  protected async doShutdown(): Promise<void> {
    // No shutdown needed for environment provider
  }

  protected async checkAvailability(): Promise<boolean> {
    // Environment provider is always available
    return true;
  }
}