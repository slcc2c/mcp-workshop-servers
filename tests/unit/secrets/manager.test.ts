/**
 * Unit tests for secrets manager
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SecretsManager } from '../../../src/secrets/manager';
import { 
  SecretProvider, 
  SecretsConfig,
  SecretNotFoundError,
  SecretProviderError
} from '../../../src/secrets/types';

describe('SecretsManager', () => {
  let manager: SecretsManager;
  const config: SecretsConfig = {
    defaultProvider: SecretProvider.ENVIRONMENT,
    providers: [
      {
        type: SecretProvider.ENVIRONMENT,
        enabled: true,
      }
    ],
    cache: {
      enabled: true,
      maxSize: 100,
      ttl: 300,
    },
    audit: {
      enabled: true,
      logAccess: true,
      logRotation: true,
    },
  };

  beforeEach(async () => {
    // Set up test environment
    process.env.TEST_SECRET = 'test-value';
    process.env.ANOTHER_SECRET = 'another-value';
    
    manager = new SecretsManager(config);
    await manager.initialize();
  });

  afterEach(async () => {
    await manager.shutdown();
    delete process.env.TEST_SECRET;
    delete process.env.ANOTHER_SECRET;
  });

  describe('Secret Resolution', () => {
    it('should resolve environment variables', async () => {
      const value = await manager.getSecret('TEST_SECRET');
      expect(value).toBe('test-value');
    });

    it('should parse string references', async () => {
      const value = await manager.getSecret('env:TEST_SECRET');
      expect(value).toBe('test-value');
    });

    it('should parse object references', async () => {
      const value = await manager.getSecret({
        provider: SecretProvider.ENVIRONMENT,
        path: 'TEST_SECRET',
      });
      expect(value).toBe('test-value');
    });

    it('should throw error for non-existent secrets', async () => {
      await expect(manager.getSecret('NON_EXISTENT'))
        .rejects.toThrow(SecretNotFoundError);
    });

    it('should get multiple secrets', async () => {
      const secrets = await manager.getSecrets([
        'TEST_SECRET',
        'env:ANOTHER_SECRET',
      ]);
      
      expect(secrets.size).toBe(2);
      expect(secrets.get('TEST_SECRET')).toBe('test-value');
      expect(secrets.get('env:ANOTHER_SECRET')).toBe('another-value');
    });
  });

  describe('Provider Management', () => {
    it('should list available providers', () => {
      const providers = manager.getAvailableProviders();
      expect(providers).toContain(SecretProvider.ENVIRONMENT);
    });

    it('should check provider availability', async () => {
      const available = await manager.isProviderAvailable(SecretProvider.ENVIRONMENT);
      expect(available).toBe(true);
    });

    it('should handle unavailable providers', async () => {
      await expect(manager.getSecret('aws:test:secret'))
        .rejects.toThrow('Provider not available: aws-secrets-manager');
    });
  });

  describe('Cache Management', () => {
    it('should cache secrets', async () => {
      // First call - not cached
      const value1 = await manager.getSecret('TEST_SECRET');
      
      // Second call - should be cached
      const value2 = await manager.getSecret('TEST_SECRET');
      
      expect(value1).toBe(value2);
      
      const stats = manager.getCacheStats();
      expect(stats.size).toBeGreaterThan(0);
    });

    it('should clear cache', async () => {
      await manager.getSecret('TEST_SECRET');
      
      const statsBefore = manager.getCacheStats();
      expect(statsBefore.size).toBeGreaterThan(0);
      
      manager.clearCache();
      
      const statsAfter = manager.getCacheStats();
      expect(statsAfter.size).toBe(0);
    });
  });

  describe('Audit Logging', () => {
    it('should log secret access', async () => {
      await manager.getSecret('TEST_SECRET');
      
      const auditLog = manager.getAuditLog();
      expect(auditLog).toHaveLength(1);
      expect(auditLog[0]).toMatchObject({
        action: 'access',
        secretName: 'TEST_SECRET',
        provider: SecretProvider.ENVIRONMENT,
        success: true,
      });
    });

    it('should log failed access', async () => {
      try {
        await manager.getSecret('NON_EXISTENT');
      } catch {
        // Expected to fail
      }
      
      const auditLog = manager.getAuditLog();
      const failedEntry = auditLog.find(e => !e.success);
      
      expect(failedEntry).toBeDefined();
      expect(failedEntry?.action).toBe('access');
      expect(failedEntry?.error).toBeDefined();
    });

    it('should clear audit log', async () => {
      await manager.getSecret('TEST_SECRET');
      expect(manager.getAuditLog()).toHaveLength(1);
      
      manager.clearAuditLog();
      expect(manager.getAuditLog()).toHaveLength(0);
    });
  });

  describe('Reference Parsing', () => {
    it('should parse simple references', async () => {
      const testCases = [
        { input: 'TEST_SECRET', expected: 'test-value' },
        { input: 'env:TEST_SECRET', expected: 'test-value' },
        { input: 'environment:TEST_SECRET', expected: 'test-value' },
      ];
      
      for (const { input, expected } of testCases) {
        const value = await manager.getSecret(input);
        expect(value).toBe(expected);
      }
    });

    it('should handle URL format references', async () => {
      const value = await manager.getSecret('secret://environment/TEST_SECRET');
      expect(value).toBe('test-value');
    });

    it('should reject invalid reference formats', async () => {
      await expect(manager.getSecret('too:many:colons:here'))
        .rejects.toThrow('Invalid secret reference format');
    });
  });

  describe('Error Handling', () => {
    it('should emit audit events', async () => {
      const events: any[] = [];
      manager.on('audit', (event) => events.push(event));
      
      await manager.getSecret('TEST_SECRET');
      
      expect(events).toHaveLength(1);
      expect(events[0].action).toBe('access');
    });

    it('should handle provider initialization failures gracefully', async () => {
      const badConfig: SecretsConfig = {
        ...config,
        providers: [
          {
            type: 'invalid-provider' as any,
            enabled: true,
          }
        ],
      };
      
      const badManager = new SecretsManager(badConfig);
      await badManager.initialize(); // Should not throw
      
      // Environment provider should still work
      const providers = badManager.getAvailableProviders();
      expect(providers).toContain(SecretProvider.ENVIRONMENT);
    });
  });
});