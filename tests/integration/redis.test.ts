import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { RedisServer } from '../../servers/redis';
import Redis from 'ioredis';

describe('Redis MCP Server Integration Tests', () => {
  let server: any; // RedisServer with any cast for testing
  let testClient: Redis;
  const testKeyPrefix = 'mcp_test:';

  beforeAll(async () => {
    // Set up Redis connection
    process.env.REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
    
    // Initialize test client for cleanup
    testClient = new Redis(process.env.REDIS_URL);

    // Initialize server
    server = new RedisServer();
    await server.initialize();
  });

  afterAll(async () => {
    // Clean up all test keys
    const keys = await testClient.keys(`${testKeyPrefix}*`);
    if (keys.length > 0) {
      await testClient.del(...keys);
    }

    await server.shutdown();
    await testClient.quit();
  });

  beforeEach(async () => {
    // Clean up test keys before each test
    const keys = await testClient.keys(`${testKeyPrefix}*`);
    if (keys.length > 0) {
      await testClient.del(...keys);
    }
  });

  describe('String Operations', () => {
    it('should set and get a value', async () => {
      const key = `${testKeyPrefix}string:1`;
      
      const setResult = await server.executeTool('redis_set', {
        key,
        value: 'Hello, Redis!',
      });

      expect(setResult.success).toBe(true);
      expect(setResult.key).toBe(key);

      const getResult = await server.executeTool('redis_get', {
        key,
      });

      expect(getResult.value).toBe('Hello, Redis!');
      expect(getResult.key).toBe(key);
    });

    it('should set value with TTL', async () => {
      const key = `${testKeyPrefix}string:ttl`;
      
      await server.executeTool('redis_set', {
        key,
        value: 'Temporary value',
        ttl: 60,
      });

      const ttlResult = await server.executeTool('redis_ttl', {
        key,
      });

      expect(ttlResult.expires).toBe(true);
      expect(ttlResult.ttl).toBeGreaterThan(0);
      expect(ttlResult.ttl).toBeLessThanOrEqual(60);
    });

    it('should handle non-existent keys', async () => {
      await expect(
        server.executeTool('redis_get', {
          key: `${testKeyPrefix}nonexistent`,
        })
      ).rejects.toThrow('not found');
    });

    it('should delete keys', async () => {
      const keys = [
        `${testKeyPrefix}del:1`,
        `${testKeyPrefix}del:2`,
        `${testKeyPrefix}del:3`,
      ];

      // Set values
      for (const key of keys) {
        await server.executeTool('redis_set', { key, value: 'test' });
      }

      const deleteResult = await server.executeTool('redis_delete', {
        keys,
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.deleted).toBe(3);

      // Verify deletion
      const existsResult = await server.executeTool('redis_exists', {
        keys,
      });

      expect(existsResult.existingCount).toBe(0);
    });

    it('should check key existence', async () => {
      const existingKey = `${testKeyPrefix}exists:1`;
      const nonExistingKey = `${testKeyPrefix}exists:2`;

      await server.executeTool('redis_set', {
        key: existingKey,
        value: 'exists',
      });

      const result = await server.executeTool('redis_exists', {
        keys: [existingKey, nonExistingKey],
      });

      expect(result.results[existingKey]).toBe(true);
      expect(result.results[nonExistingKey]).toBe(false);
      expect(result.existingCount).toBe(1);
    });

    it('should find keys by pattern', async () => {
      // Set multiple keys
      await server.executeTool('redis_set', {
        key: `${testKeyPrefix}user:1`,
        value: 'Alice',
      });
      await server.executeTool('redis_set', {
        key: `${testKeyPrefix}user:2`,
        value: 'Bob',
      });
      await server.executeTool('redis_set', {
        key: `${testKeyPrefix}admin:1`,
        value: 'Charlie',
      });

      const result = await server.executeTool('redis_keys', {
        pattern: `${testKeyPrefix}user:*`,
        count: 10,
      });

      expect(result.keys).toHaveLength(2);
      expect(result.keys).toContain(`${testKeyPrefix}user:1`);
      expect(result.keys).toContain(`${testKeyPrefix}user:2`);
    });
  });

  describe('Hash Operations', () => {
    it('should set and get hash fields', async () => {
      const key = `${testKeyPrefix}hash:user:1`;

      await server.executeTool('redis_hset', {
        key,
        field: 'name',
        value: 'John Doe',
      });

      await server.executeTool('redis_hset', {
        key,
        field: 'email',
        value: 'john@example.com',
      });

      // Get single field
      const fieldResult = await server.executeTool('redis_hget', {
        key,
        field: 'name',
      });

      expect(fieldResult.value).toBe('John Doe');

      // Get all fields
      const allResult = await server.executeTool('redis_hget', {
        key,
      });

      expect(allResult.hash).toEqual({
        name: 'John Doe',
        email: 'john@example.com',
      });
      expect(allResult.fieldCount).toBe(2);
    });

    it('should handle non-existent hash fields', async () => {
      const key = `${testKeyPrefix}hash:empty`;

      await expect(
        server.executeTool('redis_hget', {
          key,
          field: 'nonexistent',
        })
      ).rejects.toThrow('not found');
    });
  });

  describe('List Operations', () => {
    it('should push and retrieve list values', async () => {
      const key = `${testKeyPrefix}list:1`;

      // Push to right
      const pushResult = await server.executeTool('redis_list_push', {
        key,
        values: ['first', 'second', 'third'],
        direction: 'right',
      });

      expect(pushResult.success).toBe(true);
      expect(pushResult.length).toBe(3);

      // Push to left
      await server.executeTool('redis_list_push', {
        key,
        values: ['zero'],
        direction: 'left',
      });

      // Get range
      const rangeResult = await server.executeTool('redis_list_range', {
        key,
        start: 0,
        stop: -1,
      });

      expect(rangeResult.values).toEqual(['zero', 'first', 'second', 'third']);
      expect(rangeResult.totalLength).toBe(4);
    });

    it('should handle list range operations', async () => {
      const key = `${testKeyPrefix}list:range`;

      await server.executeTool('redis_list_push', {
        key,
        values: ['a', 'b', 'c', 'd', 'e'],
        direction: 'right',
      });

      const result = await server.executeTool('redis_list_range', {
        key,
        start: 1,
        stop: 3,
      });

      expect(result.values).toEqual(['b', 'c', 'd']);
    });
  });

  describe('Set Operations', () => {
    it('should add and retrieve set members', async () => {
      const key = `${testKeyPrefix}set:1`;

      const addResult = await server.executeTool('redis_set_add', {
        key,
        members: ['apple', 'banana', 'cherry', 'apple'], // Duplicate
      });

      expect(addResult.success).toBe(true);
      expect(addResult.added).toBe(3); // Only 3 unique members
      expect(addResult.totalMembers).toBe(3);

      const membersResult = await server.executeTool('redis_set_members', {
        key,
      });

      expect(membersResult.members).toHaveLength(3);
      expect(membersResult.members).toContain('apple');
      expect(membersResult.members).toContain('banana');
      expect(membersResult.members).toContain('cherry');
    });

    it('should perform set operations', async () => {
      const set1 = `${testKeyPrefix}set:op:1`;
      const set2 = `${testKeyPrefix}set:op:2`;
      const set3 = `${testKeyPrefix}set:op:3`;

      // Create sets
      await server.executeTool('redis_set_add', {
        key: set1,
        members: ['a', 'b', 'c'],
      });

      await server.executeTool('redis_set_add', {
        key: set2,
        members: ['b', 'c', 'd'],
      });

      await server.executeTool('redis_set_add', {
        key: set3,
        members: ['c', 'd', 'e'],
      });

      // Union
      const unionResult = await server.executeTool('redis_set_operations', {
        operation: 'union',
        keys: [set1, set2, set3],
      });

      expect(unionResult.result).toHaveLength(5);
      expect(unionResult.result).toContain('a');
      expect(unionResult.result).toContain('e');

      // Intersection
      const intersectResult = await server.executeTool('redis_set_operations', {
        operation: 'intersect',
        keys: [set1, set2, set3],
      });

      expect(intersectResult.result).toEqual(['c']);

      // Difference
      const diffResult = await server.executeTool('redis_set_operations', {
        operation: 'diff',
        keys: [set1, set2],
      });

      expect(diffResult.result).toEqual(['a']);
    });
  });

  describe('Sorted Set Operations', () => {
    it('should add and retrieve sorted set members', async () => {
      const key = `${testKeyPrefix}zset:scores`;

      await server.executeTool('redis_zadd', {
        key,
        members: [
          { score: 100, member: 'Alice' },
          { score: 85, member: 'Bob' },
          { score: 95, member: 'Charlie' },
          { score: 90, member: 'David' },
        ],
      });

      // Get range without scores
      const rangeResult = await server.executeTool('redis_zrange', {
        key,
        start: 0,
        stop: 2,
        withScores: false,
      });

      expect(rangeResult.members).toEqual(['Bob', 'David', 'Charlie']);

      // Get range with scores
      const scoresResult = await server.executeTool('redis_zrange', {
        key,
        start: 0,
        stop: -1,
        withScores: true,
      });

      expect(scoresResult.members).toHaveLength(4);
      expect(scoresResult.members[0]).toEqual({ member: 'Bob', score: 85 });
      expect(scoresResult.members[3]).toEqual({ member: 'Alice', score: 100 });
    });
  });

  describe('Expiration Operations', () => {
    it('should set and check expiration', async () => {
      const key = `${testKeyPrefix}expire:1`;

      await server.executeTool('redis_set', {
        key,
        value: 'Will expire',
      });

      const expireResult = await server.executeTool('redis_expire', {
        key,
        seconds: 300,
      });

      expect(expireResult.success).toBe(true);
      expect(expireResult.expiresIn).toBe(300);

      const ttlResult = await server.executeTool('redis_ttl', {
        key,
      });

      expect(ttlResult.expires).toBe(true);
      expect(ttlResult.ttl).toBeGreaterThan(290);
      expect(ttlResult.ttl).toBeLessThanOrEqual(300);
    });

    it('should handle keys without expiration', async () => {
      const key = `${testKeyPrefix}persist:1`;

      await server.executeTool('redis_set', {
        key,
        value: 'Persistent',
      });

      const ttlResult = await server.executeTool('redis_ttl', {
        key,
      });

      expect(ttlResult.expires).toBe(false);
      expect(ttlResult.ttl).toBeNull();
    });
  });

  describe('Pub/Sub Operations', () => {
    it('should publish messages', async () => {
      const channel = `${testKeyPrefix}channel:1`;

      const result = await server.executeTool('redis_publish', {
        channel,
        message: 'Hello, subscribers!',
      });

      expect(result.success).toBe(true);
      expect(result.channel).toBe(channel);
      expect(result.messageLength).toBe(18);
      // subscribers will be 0 unless someone is actively subscribed
    });

    it('should handle subscription timeout', async () => {
      const channels = [`${testKeyPrefix}sub:1`, `${testKeyPrefix}sub:2`];

      const result = await server.executeTool('redis_subscribe', {
        channels,
        timeout: 100, // Very short timeout
      });

      expect(result.channels).toEqual(channels);
      expect(result.messages).toEqual([]);
      expect(result.timedOut).toBe(true);
    });
  });

  describe('Pipeline Operations', () => {
    it('should execute pipeline commands', async () => {
      const keyPrefix = `${testKeyPrefix}pipeline:`;

      const result = await server.executeTool('redis_pipeline', {
        commands: [
          { command: 'set', args: [`${keyPrefix}1`, 'value1'] },
          { command: 'set', args: [`${keyPrefix}2`, 'value2'] },
          { command: 'expire', args: [`${keyPrefix}1`, 60] },
          { command: 'get', args: [`${keyPrefix}1`] },
          { command: 'get', args: [`${keyPrefix}2`] },
        ],
      });

      expect(result.success).toBe(true);
      expect(result.commandCount).toBe(5);
      expect(result.results[0].result).toBe('OK');
      expect(result.results[1].result).toBe('OK');
      expect(result.results[2].result).toBe(1); // expire returns 1 on success
      expect(result.results[3].result).toBe('value1');
      expect(result.results[4].result).toBe('value2');
    });

    it('should handle pipeline errors', async () => {
      const result = await server.executeTool('redis_pipeline', {
        commands: [
          { command: 'set', args: [`${testKeyPrefix}pipe:1`, 'value'] },
          { command: 'get', args: [] }, // Invalid - missing key
          { command: 'set', args: [`${testKeyPrefix}pipe:2`, 'value2'] },
        ],
      });

      expect(result.success).toBe(true);
      expect(result.results[0].error).toBeNull();
      expect(result.results[1].error).toBeDefined(); // Should have error
      expect(result.results[2].error).toBeNull(); // Should still execute
    });
  });

  describe('Server Information', () => {
    it('should get server info', async () => {
      const result = await server.executeTool('redis_info', {});

      expect(result).toBeDefined();
      expect(result.Server).toBeDefined();
      expect(result.Server.redis_version).toBeDefined();
    });

    it('should get specific info section', async () => {
      const result = await server.executeTool('redis_info', {
        section: 'memory',
      });

      expect(result.used_memory).toBeDefined();
      expect(result.used_memory_human).toBeDefined();
    });
  });
});