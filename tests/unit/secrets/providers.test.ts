/**
 * Unit tests for secret providers
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { EnvironmentSecretProvider } from '../../../src/secrets/providers/environment';
import { OnePasswordSecretProvider } from '../../../src/secrets/providers/onepassword';
import { SecretProvider, SecretNotFoundError, OnePasswordConfig } from '../../../src/secrets/types';

describe('EnvironmentSecretProvider', () => {
  let provider: EnvironmentSecretProvider;
  const originalEnv = process.env;

  beforeEach(async () => {
    process.env = { ...originalEnv };
    provider = new EnvironmentSecretProvider();
    await provider.initialize();
  });

  afterEach(async () => {
    process.env = originalEnv;
    await provider.shutdown();
  });

  it('should retrieve environment variables', async () => {
    process.env.TEST_SECRET = 'test-value';
    
    const secret = await provider.getSecret('TEST_SECRET');
    
    expect(secret.value).toBe('test-value');
    expect(secret.metadata.name).toBe('TEST_SECRET');
    expect(secret.metadata.provider).toBe(SecretProvider.ENVIRONMENT);
  });

  it('should throw error for non-existent variables', async () => {
    await expect(provider.getSecret('NON_EXISTENT_VAR'))
      .rejects.toThrow(SecretNotFoundError);
  });

  it('should always be available', async () => {
    const available = await provider.isAvailable();
    expect(available).toBe(true);
  });
});

describe('OnePasswordSecretProvider', () => {
  let provider: OnePasswordSecretProvider;
  const mockExec = vi.fn();

  beforeEach(() => {
    // Mock child_process.exec
    vi.mock('child_process', () => ({
      exec: (cmd: string, cb: any) => mockExec(cmd, cb),
      promisify: (fn: any) => (cmd: string) => 
        new Promise((resolve, reject) => {
          mockExec(cmd, (err: any, stdout: string) => {
            if (err) reject(err);
            else resolve({ stdout });
          });
        })
    }));

    const config: OnePasswordConfig = {
      vault: 'TestVault',
      cliPath: 'op',
      cacheTtl: 300,
    };
    
    provider = new OnePasswordSecretProvider(config);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should check CLI availability', async () => {
    mockExec.mockImplementation((cmd: string, cb: any) => {
      if (cmd.includes('--version')) {
        cb(null, '2.24.0');
      }
    });

    const available = await provider.isAvailable();
    expect(available).toBe(true);
    expect(mockExec).toHaveBeenCalledWith(expect.stringContaining('--version'), expect.any(Function));
  });

  it('should retrieve item fields', async () => {
    // Mock signed in check
    mockExec.mockImplementationOnce((cmd: string, cb: any) => {
      if (cmd.includes('account list')) {
        cb(null, JSON.stringify([{ email: 'test@example.com' }]));
      }
    });

    // Mock item get
    mockExec.mockImplementationOnce((cmd: string, cb: any) => {
      if (cmd.includes('item get')) {
        cb(null, 'secret-value');
      }
    });

    await provider.initialize();
    const secret = await provider.getSecret('TestItem', 'password');
    
    expect(secret.value).toBe('secret-value');
    expect(secret.metadata.provider).toBe(SecretProvider.ONEPASSWORD);
  });

  it('should handle authentication errors', async () => {
    mockExec.mockImplementation((cmd: string, cb: any) => {
      if (cmd.includes('account list')) {
        cb(new Error('Not signed in'));
      }
    });

    await provider.initialize();
    
    await expect(provider.getSecret('TestItem'))
      .rejects.toThrow('Not signed in to 1Password');
  });

  it('should list items with prefix filtering', async () => {
    // Mock signed in
    mockExec.mockImplementationOnce((cmd: string, cb: any) => {
      cb(null, JSON.stringify([{ email: 'test@example.com' }]));
    });

    // Mock item list
    mockExec.mockImplementationOnce((cmd: string, cb: any) => {
      const items = [
        { id: '1', title: 'Database/postgres', updated_at: '2024-01-01' },
        { id: '2', title: 'Database/redis', updated_at: '2024-01-02' },
        { id: '3', title: 'API/key', updated_at: '2024-01-03' },
      ];
      cb(null, JSON.stringify(items));
    });

    await provider.initialize();
    const secrets = await provider.listSecrets('Database');
    
    expect(secrets).toHaveLength(2);
    expect(secrets[0].name).toBe('Database/postgres');
    expect(secrets[1].name).toBe('Database/redis');
  });
});