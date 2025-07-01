/**
 * Redis MCP Server
 * Provides Redis operations with pub/sub support and connection pooling
 */

import { z } from 'zod';
import Redis, { RedisOptions } from 'ioredis';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const KeyValueSchema = z.object({
  key: z.string().describe('Redis key'),
  value: z.string().describe('Value to store'),
  ttl: z.number().optional().describe('Time to live in seconds'),
});

const KeySchema = z.object({
  key: z.string().describe('Redis key'),
});

const KeysSchema = z.object({
  pattern: z.string().default('*').describe('Pattern to match keys (e.g., "user:*")'),
  count: z.number().default(100).describe('Maximum number of keys to return'),
});

const HashSchema = z.object({
  key: z.string().describe('Hash key'),
  field: z.string().describe('Hash field'),
  value: z.string().describe('Field value'),
});

const HashGetSchema = z.object({
  key: z.string().describe('Hash key'),
  field: z.string().optional().describe('Hash field (omit to get all fields)'),
});

const ListPushSchema = z.object({
  key: z.string().describe('List key'),
  values: z.array(z.string()).describe('Values to push'),
  direction: z.enum(['left', 'right']).default('right').describe('Push direction'),
});

const ListRangeSchema = z.object({
  key: z.string().describe('List key'),
  start: z.number().default(0).describe('Start index'),
  stop: z.number().default(-1).describe('Stop index (-1 for end)'),
});

const SetSchema = z.object({
  key: z.string().describe('Set key'),
  members: z.array(z.string()).describe('Members to add'),
});

const SetOperationSchema = z.object({
  operation: z.enum(['union', 'intersect', 'diff']).describe('Set operation'),
  keys: z.array(z.string()).min(2).describe('Keys to operate on'),
});

const SortedSetSchema = z.object({
  key: z.string().describe('Sorted set key'),
  members: z.array(z.object({
    score: z.number(),
    member: z.string(),
  })).describe('Members with scores'),
});

const SortedSetRangeSchema = z.object({
  key: z.string().describe('Sorted set key'),
  start: z.number().default(0).describe('Start rank'),
  stop: z.number().default(-1).describe('Stop rank (-1 for end)'),
  withScores: z.boolean().default(false).describe('Include scores in result'),
});

const PublishSchema = z.object({
  channel: z.string().describe('Channel name'),
  message: z.string().describe('Message to publish'),
});

const SubscribeSchema = z.object({
  channels: z.array(z.string()).describe('Channels to subscribe to'),
  timeout: z.number().default(10000).describe('Timeout in milliseconds'),
});

const ExpireSchema = z.object({
  key: z.string().describe('Key to set expiration on'),
  seconds: z.number().describe('Expiration time in seconds'),
});

const DeleteKeysSchema = z.object({
  keys: z.array(z.string()).describe('Keys to delete'),
});

const ExistsKeysSchema = z.object({
  keys: z.array(z.string()).describe('Keys to check'),
});

const InfoSchema = z.object({
  section: z.string().optional().describe('Info section (e.g., "server", "clients", "memory")'),
});

const PipelineSchema = z.object({
  commands: z.array(z.object({
    command: z.string().describe('Redis command (e.g., "set", "get", "hset")'),
    args: z.array(z.any()).describe('Command arguments'),
  })).describe('Commands to execute in pipeline'),
});

export class RedisServer extends BaseMCPServer {
  private client!: Redis;
  private pubClient!: Redis;
  private subClient!: Redis;
  private subscribers: Map<string, (message: string) => void> = new Map();

  constructor() {
    super('redis', '1.0.0', 'Redis key-value store operations with pub/sub support');
  }


  protected async onInitialize(): Promise<void> {
    // Get connection string from environment
    const redisUrl = process.env.REDIS_URL || process.env.REDIS_HOST || 'redis://localhost:6379';
    
    const redisOptions: RedisOptions = {
      retryStrategy: (times) => Math.min(times * 50, 2000),
      maxRetriesPerRequest: 3,
      enableReadyCheck: true,
      lazyConnect: false,
    };

    // Parse Redis URL if provided
    if (redisUrl.startsWith('redis://') || redisUrl.startsWith('rediss://')) {
      // Use URL directly
      this.client = new Redis(redisUrl, redisOptions);
      this.pubClient = new Redis(redisUrl, redisOptions);
      this.subClient = new Redis(redisUrl, redisOptions);
    } else {
      // Assume it's just a host
      const [host, port] = redisUrl.split(':');
      const config = {
        host,
        port: parseInt(port || '6379'),
        ...redisOptions,
      };
      this.client = new Redis(config);
      this.pubClient = new Redis(config);
      this.subClient = new Redis(config);
    }

    // Test connection
    await this.client.ping();
    
    // Set up error handlers
    this.client.on('error', (err) => {
      this.logger.error('Redis client error', { error: err.message });
    });

    this.logger.info('Redis server initialized', {
      host: this.client.options.host,
      port: this.client.options.port,
    });
  }

  protected async onShutdown(): Promise<void> {
    // Unsubscribe from all channels
    await this.subClient.unsubscribe();
    this.subscribers.clear();

    // Close all connections
    await Promise.all([
      this.client.quit(),
      this.pubClient.quit(),
      this.subClient.quit(),
    ]);
    
    this.logger.info('Redis connections closed');
  }

  protected async registerTools(): Promise<void> {
    // String operations
    this.registerTool(
      'redis_set',
      'Set a key-value pair with optional TTL',
      KeyValueSchema,
      createToolHandler<z.infer<typeof KeyValueSchema>>(async (params) => {
        if (params.ttl) {
          await this.client.setex(params.key, params.ttl, params.value);
        } else {
          await this.client.set(params.key, params.value);
        }
        
        return {
          success: true,
          key: params.key,
          ttl: params.ttl,
        };
      })
    );

    this.registerTool(
      'redis_get',
      'Get value by key',
      KeySchema,
      createToolHandler<z.infer<typeof KeySchema>>(async (params) => {
        const value = await this.client.get(params.key);
        
        if (value === null) {
          throw new ResourceNotFoundError(`Key "${params.key}" not found`);
        }
        
        return {
          key: params.key,
          value,
          ttl: await this.client.ttl(params.key),
        };
      })
    );

    this.registerTool(
      'redis_delete',
      'Delete one or more keys',
      DeleteKeysSchema,
      createToolHandler<z.infer<typeof DeleteKeysSchema>>(async (params) => {
        const deleted = await this.client.del(...params.keys);
        
        return {
          success: true,
          deleted,
          keys: params.keys,
        };
      })
    );

    this.registerTool(
      'redis_exists',
      'Check if keys exist',
      ExistsKeysSchema,
      createToolHandler<z.infer<typeof ExistsKeysSchema>>(async (params) => {
        const results: Record<string, boolean> = {};
        
        for (const key of params.keys) {
          results[key] = (await this.client.exists(key)) === 1;
        }
        
        return {
          results,
          existingCount: Object.values(results).filter(v => v).length,
        };
      })
    );

    this.registerTool(
      'redis_keys',
      'Find keys matching a pattern',
      KeysSchema,
      createToolHandler<z.infer<typeof KeysSchema>>(async (params) => {
        // Use SCAN for better performance with large datasets
        const stream = this.client.scanStream({
          match: params.pattern,
          count: 100,
        });

        const keys: string[] = [];
        
        return new Promise((resolve, reject) => {
          stream.on('data', (resultKeys) => {
            keys.push(...resultKeys);
            if (keys.length >= params.count) {
              stream.destroy();
            }
          });

          stream.on('end', () => {
            resolve({
              keys: keys.slice(0, params.count),
              count: keys.length,
              pattern: params.pattern,
            });
          });

          stream.on('error', reject);
        });
      })
    );

    // Hash operations
    this.registerTool(
      'redis_hset',
      'Set hash field value',
      HashSchema,
      createToolHandler<z.infer<typeof HashSchema>>(async (params) => {
        await this.client.hset(params.key, params.field, params.value);
        
        return {
          success: true,
          key: params.key,
          field: params.field,
        };
      })
    );

    this.registerTool(
      'redis_hget',
      'Get hash field value or all fields',
      HashGetSchema,
      createToolHandler<z.infer<typeof HashGetSchema>>(async (params) => {
        if (params.field) {
          const value = await this.client.hget(params.key, params.field);
          
          if (value === null) {
            throw new ResourceNotFoundError(`Field "${params.field}" not found in hash "${params.key}"`);
          }
          
          return {
            key: params.key,
            field: params.field,
            value,
          };
        } else {
          const hash = await this.client.hgetall(params.key);
          
          if (Object.keys(hash).length === 0) {
            throw new ResourceNotFoundError(`Hash "${params.key}" not found or empty`);
          }
          
          return {
            key: params.key,
            hash,
            fieldCount: Object.keys(hash).length,
          };
        }
      })
    );

    // List operations
    this.registerTool(
      'redis_list_push',
      'Push values to a list',
      ListPushSchema,
      createToolHandler<z.infer<typeof ListPushSchema>>(async (params) => {
        const length = params.direction === 'left'
          ? await this.client.lpush(params.key, ...params.values)
          : await this.client.rpush(params.key, ...params.values);
        
        return {
          success: true,
          key: params.key,
          length,
          direction: params.direction,
        };
      })
    );

    this.registerTool(
      'redis_list_range',
      'Get list elements in range',
      ListRangeSchema,
      createToolHandler<z.infer<typeof ListRangeSchema>>(async (params) => {
        const values = await this.client.lrange(params.key, params.start, params.stop);
        
        return {
          key: params.key,
          values,
          length: values.length,
          totalLength: await this.client.llen(params.key),
        };
      })
    );

    // Set operations
    this.registerTool(
      'redis_set_add',
      'Add members to a set',
      SetSchema,
      createToolHandler<z.infer<typeof SetSchema>>(async (params) => {
        const added = await this.client.sadd(params.key, ...params.members);
        
        return {
          success: true,
          key: params.key,
          added,
          totalMembers: await this.client.scard(params.key),
        };
      })
    );

    this.registerTool(
      'redis_set_members',
      'Get all members of a set',
      KeySchema,
      createToolHandler<z.infer<typeof KeySchema>>(async (params) => {
        const members = await this.client.smembers(params.key);
        
        return {
          key: params.key,
          members,
          count: members.length,
        };
      })
    );

    this.registerTool(
      'redis_set_operations',
      'Perform set operations (union, intersect, diff)',
      SetOperationSchema,
      createToolHandler<z.infer<typeof SetOperationSchema>>(async (params) => {
        let result: string[];
        
        switch (params.operation) {
          case 'union':
            result = await this.client.sunion(...params.keys);
            break;
          case 'intersect':
            result = await this.client.sinter(...params.keys);
            break;
          case 'diff':
            result = await this.client.sdiff(...params.keys);
            break;
        }
        
        return {
          operation: params.operation,
          keys: params.keys,
          result,
          count: result.length,
        };
      })
    );

    // Sorted set operations
    this.registerTool(
      'redis_zadd',
      'Add members to a sorted set',
      SortedSetSchema,
      createToolHandler<z.infer<typeof SortedSetSchema>>(async (params) => {
        const args: (string | number)[] = [];
        params.members.forEach(m => {
          args.push(m.score, m.member);
        });
        
        const added = await this.client.zadd(params.key, ...args);
        
        return {
          success: true,
          key: params.key,
          added,
          totalMembers: await this.client.zcard(params.key),
        };
      })
    );

    this.registerTool(
      'redis_zrange',
      'Get sorted set members by rank',
      SortedSetRangeSchema,
      createToolHandler<z.infer<typeof SortedSetRangeSchema>>(async (params) => {
        const result = params.withScores
          ? await this.client.zrange(params.key, params.start, params.stop, 'WITHSCORES')
          : await this.client.zrange(params.key, params.start, params.stop);
        
        if (params.withScores) {
          const members: Array<{ member: string; score: number }> = [];
          for (let i = 0; i < result.length; i += 2) {
            members.push({
              member: result[i],
              score: parseFloat(result[i + 1]),
            });
          }
          
          return {
            key: params.key,
            members,
            count: members.length,
          };
        } else {
          return {
            key: params.key,
            members: result,
            count: result.length,
          };
        }
      })
    );

    // Pub/Sub operations
    this.registerTool(
      'redis_publish',
      'Publish message to a channel',
      PublishSchema,
      createToolHandler<z.infer<typeof PublishSchema>>(async (params) => {
        const subscribers = await this.pubClient.publish(params.channel, params.message);
        
        return {
          success: true,
          channel: params.channel,
          subscribers,
          messageLength: params.message.length,
        };
      })
    );

    this.registerTool(
      'redis_subscribe',
      'Subscribe to channels and receive messages',
      SubscribeSchema,
      createToolHandler<z.infer<typeof SubscribeSchema>>(async (params) => {
        const messages: Array<{ channel: string; message: string; timestamp: Date }> = [];
        
        return new Promise((resolve, reject) => {
          const timeout = setTimeout(() => {
            params.channels.forEach(channel => {
              this.subClient.unsubscribe(channel);
            });
            resolve({
              channels: params.channels,
              messages,
              messageCount: messages.length,
              timedOut: true,
            });
          }, params.timeout);

          const messageHandler = (channel: string, message: string) => {
            messages.push({
              channel,
              message,
              timestamp: new Date(),
            });
          };

          this.subClient.on('message', messageHandler);

          Promise.all(params.channels.map(channel => this.subClient.subscribe(channel)))
            .then(() => {
              this.logger.info('Subscribed to channels', { channels: params.channels });
            })
            .catch(error => {
              clearTimeout(timeout);
              reject(error);
            });
        });
      })
    );

    // Expiration operations
    this.registerTool(
      'redis_expire',
      'Set key expiration',
      ExpireSchema,
      createToolHandler<z.infer<typeof ExpireSchema>>(async (params) => {
        const result = await this.client.expire(params.key, params.seconds);
        
        if (result === 0) {
          throw new ResourceNotFoundError(`Key "${params.key}" not found`);
        }
        
        return {
          success: true,
          key: params.key,
          expiresIn: params.seconds,
          expiresAt: new Date(Date.now() + params.seconds * 1000),
        };
      })
    );

    this.registerTool(
      'redis_ttl',
      'Get remaining time to live for a key',
      KeySchema,
      createToolHandler<z.infer<typeof KeySchema>>(async (params) => {
        const ttl = await this.client.ttl(params.key);
        
        if (ttl === -2) {
          throw new ResourceNotFoundError(`Key "${params.key}" not found`);
        }
        
        return {
          key: params.key,
          ttl: ttl === -1 ? null : ttl,
          expires: ttl === -1 ? false : true,
          expiresAt: ttl > 0 ? new Date(Date.now() + ttl * 1000) : null,
        };
      })
    );

    // Server info
    this.registerTool(
      'redis_info',
      'Get Redis server information',
      InfoSchema,
      createToolHandler<z.infer<typeof InfoSchema>>(async (params) => {
        const info = params.section ? await this.client.info(params.section) : await this.client.info();
        
        // Parse info string into object
        const infoObj: Record<string, any> = {};
        const sections = info.split('\r\n\r\n');
        
        sections.forEach(section => {
          const lines = section.split('\r\n');
          const sectionName = lines[0].replace(/^# /, '');
          
          if (!lines[0].startsWith('#')) return;
          
          infoObj[sectionName] = {};
          
          lines.slice(1).forEach(line => {
            if (line && line.includes(':')) {
              const [key, value] = line.split(':');
              infoObj[sectionName][key] = value;
            }
          });
        });
        
        return params.section ? infoObj[params.section] || {} : infoObj;
      })
    );

    // Pipeline operations
    this.registerTool(
      'redis_pipeline',
      'Execute multiple commands in a pipeline',
      PipelineSchema,
      createToolHandler<z.infer<typeof PipelineSchema>>(async (params) => {
        const pipeline = this.client.pipeline();
        
        params.commands.forEach(cmd => {
          (pipeline as any)[cmd.command](...cmd.args);
        });
        
        const results = await pipeline.exec();
        
        if (!results) {
          throw new InvalidParamsError('Pipeline execution failed');
        }
        
        return {
          success: true,
          results: results.map((r, i) => ({
            command: params.commands[i].command,
            args: params.commands[i].args,
            error: r[0],
            result: r[1],
          })),
          commandCount: params.commands.length,
        };
      })
    );
  }
}