/**
 * Unit tests for secrets cache
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SecretCache } from '../../../src/secrets/cache';
import { Secret, SecretProvider } from '../../../src/secrets/types';

describe('SecretCache', () => {
  let cache: SecretCache;
  const mockSecret: Secret = {
    value: 'test-secret-value',
    metadata: {
      name: 'test-secret',
      provider: SecretProvider.ENVIRONMENT,
      lastUpdated: new Date(),
      ttl: 60, // 1 minute
    }
  };

  beforeEach(() => {
    cache = new SecretCache({
      enabled: true,
      maxSize: 3,
      ttl: 300, // 5 minutes default
    });
  });

  it('should cache and retrieve secrets', () => {
    const key = SecretCache.createKey('env', 'TEST_SECRET');
    
    cache.set(key, mockSecret);
    const retrieved = cache.get(key);
    
    expect(retrieved).toBeDefined();
    expect(retrieved?.value).toBe('test-secret-value');
  });

  it('should return null for cache miss', () => {
    const key = SecretCache.createKey('env', 'NON_EXISTENT');
    const retrieved = cache.get(key);
    
    expect(retrieved).toBeNull();
  });

  it('should respect TTL', () => {
    const expiredSecret: Secret = {
      ...mockSecret,
      metadata: {
        ...mockSecret.metadata,
        ttl: -1, // Already expired
      },
      expiresAt: new Date(Date.now() - 1000), // 1 second ago
    };
    
    const key = SecretCache.createKey('env', 'EXPIRED');
    cache.set(key, expiredSecret);
    
    const retrieved = cache.get(key);
    expect(retrieved).toBeNull();
  });

  it('should evict oldest entry when cache is full', () => {
    // Fill cache to capacity
    cache.set('key1', { ...mockSecret, metadata: { ...mockSecret.metadata, name: 'secret1' } });
    cache.set('key2', { ...mockSecret, metadata: { ...mockSecret.metadata, name: 'secret2' } });
    cache.set('key3', { ...mockSecret, metadata: { ...mockSecret.metadata, name: 'secret3' } });
    
    // Add one more - should evict oldest (key1)
    cache.set('key4', { ...mockSecret, metadata: { ...mockSecret.metadata, name: 'secret4' } });
    
    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')).toBeDefined();
    expect(cache.get('key3')).toBeDefined();
    expect(cache.get('key4')).toBeDefined();
  });

  it('should invalidate specific entries', () => {
    const key = SecretCache.createKey('env', 'TEST_SECRET');
    
    cache.set(key, mockSecret);
    expect(cache.get(key)).toBeDefined();
    
    cache.invalidate(key);
    expect(cache.get(key)).toBeNull();
  });

  it('should clear entire cache', () => {
    cache.set('key1', mockSecret);
    cache.set('key2', mockSecret);
    
    cache.clear();
    
    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')).toBeNull();
    expect(cache.getStats().size).toBe(0);
  });

  it('should provide accurate statistics', () => {
    cache.set('key1', mockSecret);
    cache.set('key2', mockSecret);
    
    // Access key1 multiple times
    cache.get('key1');
    cache.get('key1');
    
    const stats = cache.getStats();
    
    expect(stats.size).toBe(2);
    expect(stats.maxSize).toBe(3);
    expect(stats.enabled).toBe(true);
    expect(stats.entries).toHaveLength(2);
    
    const key1Entry = stats.entries.find(e => e.key === 'key1');
    expect(key1Entry?.accessCount).toBe(2);
  });

  it('should create proper cache keys', () => {
    expect(SecretCache.createKey('env', 'TEST')).toBe('env:TEST');
    expect(SecretCache.createKey('1password', 'item', 'field')).toBe('1password:item:field');
  });

  it('should respect disabled cache', () => {
    const disabledCache = new SecretCache({
      enabled: false,
      maxSize: 10,
      ttl: 300,
    });
    
    const key = 'test-key';
    disabledCache.set(key, mockSecret);
    
    expect(disabledCache.get(key)).toBeNull();
    expect(disabledCache.getStats().enabled).toBe(false);
  });

  it('should update access count on cache hits', () => {
    const key = 'test-key';
    cache.set(key, mockSecret);
    
    // Multiple accesses
    cache.get(key);
    cache.get(key);
    cache.get(key);
    
    const stats = cache.getStats();
    const entry = stats.entries.find(e => e.key === key);
    
    expect(entry?.accessCount).toBe(3);
  });
});