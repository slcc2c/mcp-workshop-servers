/**
 * 1Password secret provider using CLI
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { BaseSecretProvider } from './base';
import { 
  Secret, 
  SecretProvider, 
  SecretNotFoundError,
  SecretProviderError,
  SecretAccessDeniedError,
  OnePasswordConfig,
  SecretMetadata
} from '../types';

const execAsync = promisify(exec);

interface OnePasswordItem {
  id: string;
  title: string;
  vault: {
    id: string;
    name: string;
  };
  category: string;
  fields?: Array<{
    id: string;
    label: string;
    value: string;
    type: string;
  }>;
  created_at: string;
  updated_at: string;
}

export class OnePasswordSecretProvider extends BaseSecretProvider {
  protected declare config: OnePasswordConfig;
  private isSignedIn = false;

  constructor(config: OnePasswordConfig) {
    super(SecretProvider.ONEPASSWORD, config);
  }

  async getSecret(path: string, field?: string): Promise<Secret> {
    await this.ensureSignedIn();

    try {
      let value: string;
      let vault: string | undefined = this.config.vault;
      let itemPath = path;
      
      // Check if path includes vault specification (vault/item format)
      if (path.includes('/') && !vault) {
        const parts = path.split('/', 2);
        vault = parts[0];
        itemPath = parts[1];
      }
      
      // Validate vault access
      if (vault && this.config.allowedVaults && this.config.allowedVaults.length > 0) {
        if (!this.config.allowedVaults.includes(vault)) {
          throw new SecretAccessDeniedError(
            `Access to vault '${vault}' is not allowed`,
            this.name
          );
        }
      }
      
      if (field) {
        // Get specific field from item
        value = await this.getItemField(itemPath, field, vault);
      } else {
        // Get entire item as JSON
        const item = await this.getItem(itemPath, vault);
        value = JSON.stringify(item);
      }

      const metadata = this.createSecretMetadata(path, {
        path,
        ttl: this.config.cacheTtl,
      });

      return this.createSecret(value, metadata, this.config.cacheTtl);
    } catch (error) {
      if (error instanceof SecretAccessDeniedError) {
        throw error;
      }
      if (error instanceof Error) {
        if (error.message.includes('not found')) {
          throw new SecretNotFoundError(path, this.name);
        }
        if (error.message.includes('unauthorized') || error.message.includes('forbidden')) {
          throw new SecretAccessDeniedError(path, this.name);
        }
      }
      throw new SecretProviderError(
        `Failed to get secret: ${path}`,
        this.name,
        error as Error
      );
    }
  }

  async setSecret(path: string, value: string, field?: string): Promise<void> {
    await this.ensureSignedIn();

    try {
      if (field) {
        await this.setItemField(path, field, value);
      } else {
        throw new SecretProviderError(
          'Setting entire items is not supported. Please specify a field.',
          this.name
        );
      }
    } catch (error) {
      if (error instanceof SecretProviderError) {
        throw error;
      }
      throw new SecretProviderError(
        `Failed to set secret: ${path}`,
        this.name,
        error as Error
      );
    }
  }

  async listSecrets(prefix?: string): Promise<SecretMetadata[]> {
    await this.ensureSignedIn();

    try {
      const items = await this.listItems(prefix);
      
      return items.map(item => this.createSecretMetadata(item.title, {
        path: item.id,
        lastUpdated: new Date(item.updated_at),
      }));
    } catch (error) {
      throw new SecretProviderError(
        'Failed to list secrets',
        this.name,
        error as Error
      );
    }
  }

  protected async doInitialize(): Promise<void> {
    // Check if 1Password CLI is installed
    try {
      await execAsync(`${this.config.cliPath} --version`);
    } catch (error) {
      throw new SecretProviderError(
        '1Password CLI not found. Please install it from https://developer.1password.com/docs/cli',
        this.name,
        error as Error
      );
    }

    // If using Connect server, validate configuration
    if (this.config.connectHost && this.config.connectToken) {
      process.env.OP_CONNECT_HOST = this.config.connectHost;
      process.env.OP_CONNECT_TOKEN = this.config.connectToken;
    } else if (this.config.serviceAccountToken) {
      process.env.OP_SERVICE_ACCOUNT_TOKEN = this.config.serviceAccountToken;
    }
  }

  protected async doShutdown(): Promise<void> {
    // Sign out if we're signed in
    if (this.isSignedIn && !this.config.serviceAccountToken && !this.config.connectToken) {
      try {
        await execAsync(`${this.config.cliPath} signout`);
      } catch (error) {
        // Ignore signout errors
      }
    }
    this.isSignedIn = false;
  }

  protected async checkAvailability(): Promise<boolean> {
    try {
      await execAsync(`${this.config.cliPath} --version`);
      return true;
    } catch {
      return false;
    }
  }

  private async ensureSignedIn(): Promise<void> {
    if (this.isSignedIn) {
      return;
    }

    // Check if already signed in or using service account/Connect
    try {
      await execAsync(`${this.config.cliPath} account list --format=json`);
      this.isSignedIn = true;
    } catch (error) {
      if (this.config.serviceAccountToken || this.config.connectToken) {
        // Service accounts and Connect don't need sign in
        this.isSignedIn = true;
      } else {
        throw new SecretProviderError(
          'Not signed in to 1Password. Please sign in using: op signin',
          this.name
        );
      }
    }
  }

  private async getItem(itemName: string, vault?: string): Promise<OnePasswordItem> {
    const vaultFlag = vault ? `--vault="${vault}"` : '';
    const command = `${this.config.cliPath} item get "${itemName}" ${vaultFlag} --format=json`;
    
    const { stdout } = await execAsync(command);
    return JSON.parse(stdout) as OnePasswordItem;
  }

  private async getItemField(itemName: string, fieldName: string, vault?: string): Promise<string> {
    const vaultFlag = vault ? `--vault="${vault}"` : '';
    const command = `${this.config.cliPath} item get "${itemName}" ${vaultFlag} --fields="${fieldName}"`;
    
    const { stdout } = await execAsync(command);
    return stdout.trim();
  }

  private async setItemField(itemName: string, fieldName: string, value: string): Promise<void> {
    const vaultFlag = this.config.vault ? `--vault="${this.config.vault}"` : '';
    
    // First check if item exists
    try {
      await this.getItem(itemName);
      // Item exists, update field
      const command = `echo '${value}' | ${this.config.cliPath} item edit "${itemName}" ${vaultFlag} "${fieldName}[password]=-"`;
      await execAsync(command);
    } catch (error) {
      // Item doesn't exist, create it
      const command = `echo '${value}' | ${this.config.cliPath} item create ${vaultFlag} --category=password --title="${itemName}" "${fieldName}[password]=-"`;
      await execAsync(command);
    }
  }

  private async listItems(prefix?: string): Promise<OnePasswordItem[]> {
    const vaultFlag = this.config.vault ? `--vault="${this.config.vault}"` : '';
    const command = `${this.config.cliPath} item list ${vaultFlag} --format=json`;
    
    const { stdout } = await execAsync(command);
    const items = JSON.parse(stdout) as OnePasswordItem[];
    
    if (prefix) {
      return items.filter(item => item.title.startsWith(prefix));
    }
    
    return items;
  }
}