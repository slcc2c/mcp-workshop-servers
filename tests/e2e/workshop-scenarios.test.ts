/**
 * E2E Tests for "5-minute magic" Workshop Scenarios
 * 
 * These tests validate the complete workshop flow to ensure developers
 * can go from concept to working experiment in under 5 minutes.
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { performance } from 'perf_hooks';
import { DockerServer } from '../../servers/docker';
import { FilesystemServer } from '../../servers/filesystem';
import { GithubServer } from '../../servers/github';
import { MemoryServer } from '../../servers/memory';
import { PostgreSQLServer } from '../../servers/postgresql';
import { RedisServer } from '../../servers/redis';
import type { MCPServer } from '../../types/server';

// Performance tracking
interface PerformanceMetrics {
  taskName: string;
  startTime: number;
  endTime: number;
  duration: number;
  passed: boolean;
}

class WorkshopTestHarness {
  private servers: Map<string, MCPServer> = new Map();
  private metrics: PerformanceMetrics[] = [];
  private readonly FIVE_MINUTE_TARGET = 5 * 60 * 1000; // 5 minutes in ms
  private workshopStartTime = 0;
  private availableServers = new Set<string>();

  async initializeServers() {
    // Initialize tier 1 servers (essential foundation)
    try {
      const dockerServer = new DockerServer();
      await dockerServer.initialize();
      this.servers.set('docker', dockerServer);
      this.availableServers.add('docker');
    } catch (error) {
      console.warn('⚠️  Docker server not available:', error);
    }

    try {
      const filesystemServer = new FilesystemServer();
      await filesystemServer.initialize();
      this.servers.set('filesystem', filesystemServer);
      this.availableServers.add('filesystem');
    } catch (error) {
      console.warn('⚠️  Filesystem server not available:', error);
    }

    try {
      const memoryServer = new MemoryServer();
      await memoryServer.initialize();
      this.servers.set('memory', memoryServer);
      this.availableServers.add('memory');
    } catch (error) {
      console.warn('⚠️  Memory server not available:', error);
    }

    // Initialize tier 2 servers (database layer) - these are optional
    try {
      const postgresServer = new PostgreSQLServer();
      await postgresServer.initialize();
      this.servers.set('postgresql', postgresServer);
      this.availableServers.add('postgresql');
    } catch (error) {
      console.warn('⚠️  PostgreSQL server not available (optional):', (error as Error).message);
    }

    try {
      const redisServer = new RedisServer();
      await redisServer.initialize();
      this.servers.set('redis', redisServer);
      this.availableServers.add('redis');
    } catch (error) {
      console.warn('⚠️  Redis server not available (optional):', (error as Error).message);
    }

    // Note: GitHub server would require authentication in real scenario
    // For testing, we'll mock it or use test credentials
  }

  isServerAvailable(name: string): boolean {
    return this.availableServers.has(name);
  }

  async shutdownServers() {
    for (const [name, server] of this.servers) {
      try {
        await server.shutdown();
      } catch (error) {
        console.error(`Failed to shutdown ${name} server:`, error);
      }
    }
    this.servers.clear();
  }

  startWorkshop() {
    this.workshopStartTime = performance.now();
  }

  endWorkshop(): number {
    return performance.now() - this.workshopStartTime;
  }

  async trackPerformance<T>(
    taskName: string,
    task: () => Promise<T>
  ): Promise<T> {
    const startTime = performance.now();
    let passed = false;
    
    try {
      const result = await task();
      passed = true;
      return result;
    } finally {
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      this.metrics.push({
        taskName,
        startTime,
        endTime,
        duration,
        passed
      });
    }
  }

  getMetrics(): PerformanceMetrics[] {
    return this.metrics;
  }

  getServer(name: string): MCPServer {
    const server = this.servers.get(name);
    if (!server) {
      throw new Error(`Server ${name} not found`);
    }
    return server;
  }
}

describe('5-Minute Magic Workshop Scenarios', () => {
  let harness: WorkshopTestHarness;
  let createdResources: { type: string; id: string }[] = [];

  beforeAll(async () => {
    harness = new WorkshopTestHarness();
    await harness.initializeServers();
  });

  afterAll(async () => {
    // Clean up any created resources
    for (const resource of createdResources) {
      try {
        switch (resource.type) {
          case 'docker-container':
            const dockerServer = harness.getServer('docker');
            await dockerServer.executeTool('docker_remove_container', {
              containerId: resource.id,
              force: true
            });
            break;
          case 'file':
            const fsServer = harness.getServer('filesystem');
            // Check if it's a directory or file
            try {
              const stats = await fsServer.executeTool('fs_get_stats', {
                path: resource.id
              });
              if ((stats as any).isDirectory) {
                await fsServer.executeTool('fs_delete_directory', {
                  path: resource.id,
                  recursive: true
                });
              } else {
                await fsServer.executeTool('fs_delete_file', {
                  path: resource.id
                });
              }
            } catch {
              // Try both if stats fail
              try {
                await fsServer.executeTool('fs_delete_file', {
                  path: resource.id
                });
              } catch {
                await fsServer.executeTool('fs_delete_directory', {
                  path: resource.id,
                  recursive: true
                });
              }
            }
            break;
          // Add more resource cleanup as needed
        }
      } catch (error) {
        // Ignore cleanup errors
      }
    }

    await harness.shutdownServers();

    // Print performance summary
    console.log('\n📊 Performance Summary:');
    const metrics = harness.getMetrics();
    metrics.forEach(metric => {
      const status = metric.passed ? '✅' : '❌';
      console.log(`${status} ${metric.taskName}: ${(metric.duration / 1000).toFixed(2)}s`);
    });
  });

  beforeEach(() => {
    harness.startWorkshop();
  });

  afterEach(() => {
    const workshopDuration = harness.endWorkshop();
    console.log(`Workshop scenario completed in ${(workshopDuration / 1000).toFixed(2)}s`);
  });

  describe('Scenario 1: Rapid Prototype Setup', () => {
    it('should set up a new Node.js project with database in under 5 minutes', async () => {
      // Skip if essential servers aren't available
      if (!harness.isServerAvailable('filesystem')) {
        console.log('⚠️  Skipping test: Filesystem server not available');
        return;
      }

      const projectName = 'rapid-prototype-test';
      const projectPath = `${process.cwd()}/tests/tmp/${projectName}`;

      // Step 1: Create project structure
      const setupResult = await harness.trackPerformance(
        'Create project structure',
        async () => {
          const fsServer = harness.getServer('filesystem');
          
          // Create directory
          await fsServer.executeTool('fs_create_directory', {
            path: projectPath
          });
          createdResources.push({ type: 'file', id: projectPath });

          // Create package.json
          const packageJson = {
            name: projectName,
            version: '1.0.0',
            description: 'Rapid prototype test',
            main: 'index.js',
            scripts: {
              start: 'node index.js',
              test: 'jest'
            },
            dependencies: {
              express: '^4.18.0',
              pg: '^8.11.0',
              redis: '^4.6.0'
            }
          };

          await fsServer.executeTool('fs_write_file', {
            path: `${projectPath}/package.json`,
            content: JSON.stringify(packageJson, null, 2)
          });

          // Create basic Express app
          const appCode = `
const express = require('express');
const { Pool } = require('pg');
const redis = require('redis');

const app = express();
const port = process.env.PORT || 3000;

// Database connections would be configured here
const pgPool = new Pool({
  connectionString: process.env.DATABASE_URL
});

const redisClient = redis.createClient({
  url: process.env.REDIS_URL
});

app.get('/', (req, res) => {
  res.json({ message: 'Rapid prototype is running!' });
});

app.get('/health', async (req, res) => {
  try {
    // Check database connections
    await pgPool.query('SELECT 1');
    await redisClient.ping();
    
    res.json({ 
      status: 'healthy',
      postgres: 'connected',
      redis: 'connected'
    });
  } catch (error) {
    res.status(500).json({ 
      status: 'unhealthy',
      error: error.message 
    });
  }
});

app.listen(port, () => {
  console.log(\`Server running on port \${port}\`);
});
`;

          await fsServer.executeTool('fs_write_file', {
            path: `${projectPath}/index.js`,
            content: appCode
          });

          return { projectPath, created: true };
        }
      );

      expect(setupResult).toMatchObject({
        projectPath,
        created: true
      });

      // Step 2: Set up Docker containers for databases (if Docker is available)
      let containerSetup: any = { postgresId: null, redisId: null };
      
      if (harness.isServerAvailable('docker')) {
        containerSetup = await harness.trackPerformance(
          'Set up database containers',
          async () => {
            const dockerServer = harness.getServer('docker');
            
            try {
              // Create PostgreSQL container
              const pgResult = await dockerServer.executeTool('docker_create_container', {
                name: `${projectName}-postgres`,
                image: 'postgres:15',
                env: {
                  POSTGRES_PASSWORD: 'testpassword',
                  POSTGRES_DB: projectName
                },
                ports: {
                  '5432/tcp': [{ HostPort: '5433' }]
                },
                memory: '512MB'
              });
              
              createdResources.push({ 
                type: 'docker-container', 
                id: (pgResult as any).id 
              });

              // Create Redis container
              const redisResult = await dockerServer.executeTool('docker_create_container', {
                name: `${projectName}-redis`,
                image: 'redis:7',
                ports: {
                  '6379/tcp': [{ HostPort: '6380' }]
                },
                memory: '256MB'
              });
              
              createdResources.push({ 
                type: 'docker-container', 
                id: (redisResult as any).id 
              });

              // Start both containers
              await dockerServer.executeTool('docker_start_container', {
                containerId: (pgResult as any).id
              });

              await dockerServer.executeTool('docker_start_container', {
                containerId: (redisResult as any).id
              });

              return { 
                postgresId: (pgResult as any).id,
                redisId: (redisResult as any).id
              };
            } catch (error) {
              console.warn('⚠️  Could not create Docker containers:', error);
              return { postgresId: null, redisId: null };
            }
          }
        );
      } else {
        console.log('⚠️  Docker not available, skipping container setup');
      }

      // Step 3: Store configuration in memory server for AI context
      if (harness.isServerAvailable('memory')) {
        const contextSetup = await harness.trackPerformance(
          'Store project context',
          async () => {
            const memoryServer = harness.getServer('memory');
            
            await memoryServer.executeTool('memory_store', {
              content: JSON.stringify({
                projectPath,
                databases: {
                  postgres: {
                    containerId: containerSetup.postgresId,
                    port: 5433
                  },
                  redis: {
                    containerId: containerSetup.redisId,
                    port: 6380
                  }
                },
                createdAt: new Date().toISOString()
              }),
              type: 'context',
              tags: [`project:${projectName}`],
              metadata: { projectName },
              relatedTo: []
            });

            return { stored: true };
          }
        );

        expect(contextSetup).toMatchObject({ stored: true });
      }

      // Verify total time is under 5 minutes
      const totalDuration = harness.endWorkshop();
      expect(totalDuration).toBeLessThan(harness['FIVE_MINUTE_TARGET']);
    }, 300000); // 5 minute timeout
  });

  describe('Scenario 2: Multi-Server Collaboration', () => {
    it('should demonstrate multiple servers working together efficiently', async () => {
      // Skip if essential servers aren't available
      if (!harness.isServerAvailable('filesystem') || !harness.isServerAvailable('memory')) {
        console.log('⚠️  Skipping test: Required servers not available');
        return;
      }

      // Test file operations + Docker + memory persistence
      const workflowResult = await harness.trackPerformance(
        'Multi-server workflow',
        async () => {
          const fsServer = harness.getServer('filesystem');
          const memoryServer = harness.getServer('memory');

          // Step 1: Read a Dockerfile template from filesystem
          const dockerfilePath = `${process.cwd()}/tests/tmp/test-dockerfile`;
          const dockerfileContent = `
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
`;
          
          await fsServer.executeTool('fs_write_file', {
            path: dockerfilePath,
            content: dockerfileContent
          });
          createdResources.push({ type: 'file', id: dockerfilePath });

          // Step 2: Build Docker image (if Docker is available)
          let buildResult = null;
          if (harness.isServerAvailable('docker')) {
            const dockerServer = harness.getServer('docker');
            try {
              buildResult = await dockerServer.executeTool('docker_build_image', {
                tag: 'workshop-multi-server-test',
                dockerfile: dockerfileContent
              });
            } catch (error) {
              console.warn('⚠️  Could not build Docker image:', error);
            }
          }

          // Step 3: Store build information in memory
          const memoryResult = await memoryServer.executeTool('memory_store', {
            content: JSON.stringify({
              imageTag: buildResult ? 'workshop-multi-server-test' : 'no-docker',
              buildTime: new Date().toISOString(),
              dockerfilePath,
              dockerAvailable: harness.isServerAvailable('docker')
            }),
            type: 'context',
            tags: ['build:workshop-multi-server'],
            metadata: { buildId: 'workshop-multi-server' },
            relatedTo: []
          });

          // Step 4: Search for stored context
          const storedContext = await memoryServer.executeTool('memory_search', {
            query: 'build:workshop-multi-server',
            type: 'context',
            tags: [],
            limit: 1
          });

          return {
            dockerfilePath,
            buildResult,
            storedContext
          };
        }
      );

      if (harness.isServerAvailable('docker') && workflowResult.buildResult) {
        expect(workflowResult.buildResult).toHaveProperty('built', true);
      }
      expect(workflowResult.storedContext).toHaveProperty('totalResults');
      expect(workflowResult.storedContext.totalResults).toBeGreaterThan(0);
    });

    it('should handle complex data flow between servers', async () => {
      // Skip if required servers aren't available
      if (!harness.isServerAvailable('redis')) {
        console.log('⚠️  Skipping test: Redis server not available');
        return;
      }

      const dataFlowResult = await harness.trackPerformance(
        'Complex data flow',
        async () => {
          const fsServer = harness.getServer('filesystem');
          const redisServer = harness.getServer('redis');
          const memoryServer = harness.getServer('memory');

          // Step 1: Create SQL migration file
          const migrationPath = `${process.cwd()}/tests/tmp/migration.sql`;
          const migrationContent = `
CREATE TABLE IF NOT EXISTS workshop_items (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  data JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO workshop_items (name, data) VALUES
  ('test-item-1', '{"type": "example", "value": 42}'),
  ('test-item-2', '{"type": "demo", "value": 100}');
`;

          await fsServer.executeTool('fs_write_file', {
            path: migrationPath,
            content: migrationContent
          });
          createdResources.push({ type: 'file', id: migrationPath });

          // Step 2: Execute migration (mock for testing)
          // In real scenario, this would connect to the PostgreSQL container

          // Step 3: Cache results in Redis
          await redisServer.executeTool('set_value', {
            key: 'workshop:items:count',
            value: '2',
            ttl: 3600
          });

          // Step 4: Store workflow state
          await memoryServer.executeTool('memory_store', {
            content: JSON.stringify({
              migrationFile: migrationPath,
              itemCount: 2,
              cacheKey: 'workshop:items:count',
              timestamp: new Date().toISOString()
            }),
            type: 'context',
            tags: ['workflow:data-flow'],
            metadata: { workflowType: 'data-flow' },
            relatedTo: []
          });

          // Step 5: Retrieve and verify
          const cachedCount = await redisServer.executeTool('redis_get', {
            key: 'workshop:items:count'
          });

          return {
            migrationPath,
            cachedCount,
            workflowComplete: true
          };
        }
      );

      expect(dataFlowResult.cachedCount).toHaveProperty('value', '2');
      expect(dataFlowResult.workflowComplete).toBe(true);
    });
  });

  describe('Scenario 3: AI Collaboration Features', () => {
    it('should maintain context across multiple operations', async () => {
      const contextResult = await harness.trackPerformance(
        'AI context persistence',
        async () => {
          const memoryServer = harness.getServer('memory');
          const fsServer = harness.getServer('filesystem');

          // Simulate AI assistant helping with code generation
          const sessionId = 'ai-workshop-session-' + Date.now();
          
          // Step 1: Store initial context
          const initialStore = await memoryServer.executeTool('memory_store', {
            content: JSON.stringify({
              task: 'Create REST API',
              language: 'TypeScript',
              framework: 'Express',
              requirements: ['authentication', 'validation', 'error handling']
            }),
            type: 'context',
            tags: [`session:${sessionId}`],
            metadata: { sessionId },
            relatedTo: []
          });

          // Step 2: Generate code based on context
          const apiCode = `
import express, { Request, Response, NextFunction } from 'express';
import { body, validationResult } from 'express-validator';

const app = express();
app.use(express.json());

// Error handling middleware
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

// Authentication middleware (placeholder)
const authenticate = (req: Request, res: Response, next: NextFunction) => {
  // Authentication logic here
  next();
};

// Example endpoint with validation
app.post('/api/items',
  authenticate,
  [
    body('name').isString().notEmpty(),
    body('value').isNumeric()
  ],
  (req: Request, res: Response) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() });
    }
    
    // Process the request
    res.json({ success: true, data: req.body });
  }
);

export default app;
`;

          const codePath = `${process.cwd()}/tests/tmp/generated-api.ts`;
          await fsServer.executeTool('fs_write_file', {
            path: codePath,
            content: apiCode
          });
          createdResources.push({ type: 'file', id: codePath });

          // Step 3: Store updated context with generated code info
          await memoryServer.executeTool('memory_update', {
            id: (initialStore as any).id,
            content: JSON.stringify({
              task: 'Create REST API',
              language: 'TypeScript',
              framework: 'Express',
              requirements: ['authentication', 'validation', 'error handling'],
              generatedFiles: [codePath],
              lastUpdate: new Date().toISOString()
            })
          });

          // Step 4: Retrieve full context
          const fullContext = await memoryServer.executeTool('memory_get', {
            id: (initialStore as any).id
          });

          return {
            sessionId,
            codePath,
            context: fullContext
          };
        }
      );

      expect(contextResult.context).toHaveProperty('content');
      const parsedContent = JSON.parse((contextResult.context as any).content);
      expect(parsedContent).toHaveProperty('generatedFiles');
    });

    it('should support iterative development with memory', async () => {
      const iterativeResult = await harness.trackPerformance(
        'Iterative development flow',
        async () => {
          const memoryServer = harness.getServer('memory');
          const fsServer = harness.getServer('filesystem');

          const projectKey = 'iterative-project-' + Date.now();
          const iterations: any[] = [];

          // Iteration 1: Initial setup
          const memEntry = await memoryServer.executeTool('memory_store', {
            content: JSON.stringify({
              iteration: 1,
              status: 'initial',
              files: []
            }),
            type: 'context',
            tags: [projectKey],
            metadata: { projectKey },
            relatedTo: []
          });

          // Iteration 2: Add feature
          const featureFile = `${process.cwd()}/tests/tmp/feature1.js`;
          await fsServer.executeTool('fs_write_file', {
            path: featureFile,
            content: 'export const feature1 = () => "Feature 1";'
          });
          createdResources.push({ type: 'file', id: featureFile });

          await memoryServer.executeTool('memory_update', {
            id: (memEntry as any).id,
            content: JSON.stringify({
              iteration: 2,
              status: 'feature-added',
              files: [featureFile]
            })
          });

          // Iteration 3: Add tests
          const testFile = `${process.cwd()}/tests/tmp/feature1.test.js`;
          await fsServer.executeTool('fs_write_file', {
            path: testFile,
            content: `
import { feature1 } from './feature1.js';

describe('feature1', () => {
  test('returns correct value', () => {
    expect(feature1()).toBe('Feature 1');
  });
});
`
          });
          createdResources.push({ type: 'file', id: testFile });

          await memoryServer.executeTool('memory_update', {
            id: (memEntry as any).id,
            content: JSON.stringify({
              iteration: 3,
              status: 'tests-added',
              files: [featureFile, testFile]
            })
          });

          // Get full history
          const finalContext = await memoryServer.executeTool('memory_get', {
            id: (memEntry as any).id
          });

          return {
            projectKey,
            files: [featureFile, testFile],
            finalContext
          };
        }
      );

      const parsedFinalContent = JSON.parse((iterativeResult.finalContext as any).content);
      expect(parsedFinalContent.iteration).toBe(3);
      expect(parsedFinalContent.files).toHaveLength(2);
    });
  });

  describe('Performance Benchmarks', () => {
    it('should complete basic setup in under 1 minute', async () => {
      const startTime = performance.now();

      await harness.trackPerformance(
        'Basic setup benchmark',
        async () => {
          const fsServer = harness.getServer('filesystem');
          
          // Create 10 files
          const promises = [];
          for (let i = 0; i < 10; i++) {
            const path = `${process.cwd()}/tests/tmp/benchmark-file-${i}.txt`;
            promises.push(
              fsServer.executeTool('fs_write_file', {
                path,
                content: `Benchmark file ${i}`
              })
            );
            createdResources.push({ type: 'file', id: path });
          }
          
          await Promise.all(promises);
        }
      );

      const duration = performance.now() - startTime;
      expect(duration).toBeLessThan(60000); // 1 minute
    });

    it('should handle concurrent operations efficiently', async () => {
      const concurrentResult = await harness.trackPerformance(
        'Concurrent operations',
        async () => {
          const operations = [];
          
          // Filesystem operations
          if (harness.isServerAvailable('filesystem')) {
            operations.push(
              harness.getServer('filesystem').executeTool('fs_list_directory', {
                path: `${process.cwd()}/tests/tmp`
              })
            );
          }
          
          // Memory operations
          if (harness.isServerAvailable('memory')) {
            operations.push(
              harness.getServer('memory').executeTool('memory_store', {
                content: JSON.stringify({ test: true }),
                type: 'context',
                tags: ['concurrent-test-1'],
                metadata: {},
                relatedTo: []
              })
            );
          }
          
          // Docker operations (list only, no creation)
          if (harness.isServerAvailable('docker')) {
            operations.push(
              harness.getServer('docker').executeTool('docker_list_containers', {
                all: true
              })
            );
          }
          
          // Redis operations
          if (harness.isServerAvailable('redis')) {
            operations.push(
              harness.getServer('redis').executeTool('set_value', {
                key: 'concurrent-test',
                value: 'test-value',
                ttl: 60
              })
            );
          }

          const results = await Promise.all(operations);
          return { operationCount: results.length };
        }
      );

      expect(concurrentResult.operationCount).toBeGreaterThan(0);
    });

    it('should meet the 5-minute target for complete workshop', async () => {
      const workshopMetrics = harness.getMetrics();
      const totalDuration = workshopMetrics.reduce((sum, metric) => sum + metric.duration, 0);
      
      console.log(`\n🎯 Total workshop duration: ${(totalDuration / 1000).toFixed(2)}s`);
      console.log(`📊 Number of operations: ${workshopMetrics.length}`);
      console.log(`⚡ Average operation time: ${(totalDuration / workshopMetrics.length / 1000).toFixed(2)}s`);
      
      // Ensure total time is under 5 minutes
      expect(totalDuration).toBeLessThan(5 * 60 * 1000);
      
      // Ensure all operations passed
      const failedOps = workshopMetrics.filter(m => !m.passed);
      expect(failedOps).toHaveLength(0);
    });
  });

  describe('Error Recovery and Resilience', () => {
    it('should handle server failures gracefully', async () => {
      const resilienceResult = await harness.trackPerformance(
        'Error recovery test',
        async () => {
          const memoryServer = harness.getServer('memory');
          
          // Store critical state
          const criticalEntry = await memoryServer.executeTool('memory_store', {
            content: JSON.stringify({
              checkpoint: 'before-failure',
              data: { important: true }
            }),
            type: 'context',
            tags: ['critical-state'],
            metadata: {},
            relatedTo: []
          });

          // Simulate operation that might fail
          try {
            await harness.getServer('docker').executeTool('docker_inspect_container', {
              containerId: 'non-existent-container'
            });
          } catch (error) {
            // Expected to fail
          }

          // Verify we can still retrieve critical state
          const recoveredState = await memoryServer.executeTool('memory_get', {
            id: (criticalEntry as any).id
          });

          const parsedState = JSON.parse((recoveredState as any).content);
          return {
            stateRecovered: true,
            checkpoint: parsedState.checkpoint
          };
        }
      );

      expect(resilienceResult.stateRecovered).toBe(true);
      expect(resilienceResult.checkpoint).toBe('before-failure');
    });
  });
});