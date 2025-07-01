/**
 * Secret caching implementation
 */

import { Secret, SecretCacheEntry } from './types';
import { Logger } from '../types/logger';
import { createLogger } from '../utils/logger';

interface CacheConfig {
  enabled: boolean;
  maxSize: number;
  ttl: number; // Default TTL in seconds
}

export class SecretCache {
  private cache = new Map<string, SecretCacheEntry>();
  private logger: Logger;

  constructor(private config: CacheConfig) {
    this.logger = createLogger('secrets:cache');
  }

  /**
   * Get secret from cache
   */
  get(key: string): Secret | null {
    if (!this.config.enabled) {
      return null;
    }

    const entry = this.cache.get(key);
    if (!entry) {
      this.logger.debug('Cache miss', { key });
      return null;
    }

    // Check if secret has expired
    if (entry.secret.expiresAt && entry.secret.expiresAt < new Date()) {
      this.logger.debug('Cache entry expired', { key });
      this.cache.delete(key);
      return null;
    }

    // Check cache TTL
    const age = Date.now() - entry.fetchedAt.getTime();
    const ttl = entry.secret.metadata.ttl || this.config.ttl;
    if (age > ttl * 1000) {
      this.logger.debug('Cache entry TTL exceeded', { key, age, ttl });
      this.cache.delete(key);
      return null;
    }

    entry.accessCount++;
    this.logger.debug('Cache hit', { 
      key, 
      accessCount: entry.accessCount,
      age: Math.round(age / 1000) 
    });

    return entry.secret;
  }

  /**
   * Set secret in cache
   */
  set(key: string, secret: Secret): void {
    if (!this.config.enabled) {
      return;
    }

    // Enforce max cache size
    if (this.cache.size >= this.config.maxSize && !this.cache.has(key)) {
      this.evictOldest();
    }

    const entry: SecretCacheEntry = {
      secret,
      fetchedAt: new Date(),
      accessCount: 0,
    };

    this.cache.set(key, entry);
    this.logger.debug('Cached secret', { 
      key,
      ttl: secret.metadata.ttl || this.config.ttl 
    });
  }

  /**
   * Invalidate cache entry
   */
  invalidate(key: string): void {
    if (this.cache.delete(key)) {
      this.logger.debug('Invalidated cache entry', { key });
    }
  }

  /**
   * Clear entire cache
   */
  clear(): void {
    const size = this.cache.size;
    this.cache.clear();
    this.logger.info('Cleared cache', { entriesRemoved: size });
  }

  /**
   * Get cache statistics
   */
  getStats(): {
    size: number;
    maxSize: number;
    enabled: boolean;
    entries: Array<{
      key: string;
      provider: string;
      fetchedAt: Date;
      accessCount: number;
      expiresAt?: Date;
    }>;
  } {
    const entries = Array.from(this.cache.entries()).map(([key, entry]) => ({
      key,
      provider: entry.secret.metadata.provider,
      fetchedAt: entry.fetchedAt,
      accessCount: entry.accessCount,
      expiresAt: entry.secret.expiresAt,
    }));

    return {
      size: this.cache.size,
      maxSize: this.config.maxSize,
      enabled: this.config.enabled,
      entries,
    };
  }

  /**
   * Evict oldest entry from cache
   */
  private evictOldest(): void {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;

    for (const [key, entry] of this.cache.entries()) {
      if (entry.fetchedAt.getTime() < oldestTime) {
        oldestTime = entry.fetchedAt.getTime();
        oldestKey = key;
      }
    }

    if (oldestKey) {
      this.cache.delete(oldestKey);
      this.logger.debug('Evicted oldest cache entry', { key: oldestKey });
    }
  }

  /**
   * Create cache key from path and field
   */
  static createKey(provider: string, path: string, field?: string): string {
    return field ? `${provider}:${path}:${field}` : `${provider}:${path}`;
  }
}