/**
 * Integration tests for Docker Server
 * Note: These tests require Docker to be running
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll } from 'vitest';
import { DockerServer } from '../../servers/docker';

describe('DockerServer Integration', () => {
  let server: DockerServer;
  let createdContainers: string[] = [];
  let createdImages: string[] = [];
  let createdVolumes: string[] = [];
  let createdNetworks: string[] = [];

  beforeAll(async () => {
    // Check if Docker is available
    try {
      const Docker = await import('dockerode');
      const docker = new Docker();
      await docker.ping();
    } catch (error) {
      console.log('⚠️  Docker not available, skipping Docker tests');
      return;
    }
  });

  beforeEach(async () => {
    server = new DockerServer();
    
    try {
      await server.initialize();
    } catch (error) {
      // Skip tests if Docker is not available
      if (error instanceof Error && error.message.includes('Docker daemon not available')) {
        console.log('⚠️  Docker daemon not available, skipping test');
        return;
      }
      throw error;
    }
  });

  afterEach(async () => {
    if (!server) return;

    try {
      // Clean up created resources
      for (const containerId of createdContainers) {
        try {
          await server.executeTool('docker_remove_container', {
            containerId,
            force: true,
            volumes: true
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const imageId of createdImages) {
        try {
          await server.executeTool('docker_remove_image', {
            imageId,
            force: true
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const volumeName of createdVolumes) {
        try {
          await server.executeTool('docker_remove_volume', {
            volumeName,
            force: true
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const networkId of createdNetworks) {
        try {
          await server.executeTool('docker_remove_network', {
            networkId
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      await server.shutdown();
      
      // Reset arrays
      createdContainers = [];
      createdImages = [];
      createdVolumes = [];
      createdNetworks = [];
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  describe('System Information', () => {
    it('should get Docker system information', async () => {
      if (!server) return;

      const systemInfo = await server.executeTool('docker_system_info', {});

      expect(systemInfo).toMatchObject({
        containers: expect.any(Number),
        containersRunning: expect.any(Number),
        containersPaused: expect.any(Number),
        containersStopped: expect.any(Number),
        images: expect.any(Number),
        serverVersion: expect.any(String),
        architecture: expect.any(String),
      });
    });
  });

  describe('Image Management', () => {
    it('should list Docker images', async () => {
      if (!server) return;

      const result = await server.executeTool('docker_list_images', {
        all: false
      });

      expect(result).toMatchObject({
        images: expect.any(Array),
        count: expect.any(Number)
      });
    });

    it('should pull a Docker image', async () => {
      if (!server) return;

      const image = 'hello-world';
      const tag = 'latest';

      const result = await server.executeTool('docker_pull_image', {
        image,
        tag
      });

      expect(result).toMatchObject({
        image: `${image}:${tag}`,
        pulled: true
      });

      createdImages.push(`${image}:${tag}`);
    }, 30000); // 30 second timeout for image pull

    it('should build a Docker image from Dockerfile', async () => {
      if (!server) return;

      const tag = 'mcp-test-image';
      const dockerfile = `
FROM alpine:latest
RUN echo "Hello from MCP Docker server!"
CMD ["echo", "Container is running"]
`;

      const result = await server.executeTool('docker_build_image', {
        tag,
        dockerfile,
        labels: {
          'mcp.test': 'true'
        }
      });

      expect(result).toMatchObject({
        tag,
        built: true,
        output: expect.any(String)
      });

      createdImages.push(tag);
    }, 30000); // 30 second timeout for image build
  });

  describe('Container Lifecycle', () => {
    it('should create, start, and manage a container', async () => {
      if (!server) return;

      // First ensure we have the hello-world image
      try {
        await server.executeTool('docker_pull_image', {
          image: 'hello-world',
          tag: 'latest'
        });
      } catch (error) {
        // Image might already exist
      }

      // Create container
      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-container',
        image: 'hello-world:latest',
        memory: '128MB',
        cpus: '0.5',
        autoRemove: false // Don't auto-remove for testing
      });

      expect(createResult).toMatchObject({
        id: expect.any(String),
        name: 'mcp-test-container',
        image: 'hello-world:latest',
        created: true
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      // Start container
      const startResult = await server.executeTool('docker_start_container', {
        containerId
      });

      expect(startResult).toMatchObject({
        containerId,
        started: true
      });

      // Wait a moment for container to run
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Get container info
      const inspectResult = await server.executeTool('docker_inspect_container', {
        containerId
      });

      expect(inspectResult).toMatchObject({
        id: containerId,
        name: 'mcp-test-container',
        state: expect.objectContaining({
          status: expect.any(String)
        })
      });

      // Get container logs
      const logsResult = await server.executeTool('docker_container_logs', {
        containerId,
        tail: 50
      });

      expect(logsResult).toMatchObject({
        containerId,
        logs: expect.any(String),
        tail: 50
      });
    }, 30000);

    it('should stop and remove a container', async () => {
      if (!server) return;

      // Create a long-running container for testing
      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-long-running',
        image: 'alpine:latest',
        command: ['sleep', '30'],
        autoRemove: false
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      // Start container
      await server.executeTool('docker_start_container', {
        containerId
      });

      // Stop container
      const stopResult = await server.executeTool('docker_stop_container', {
        containerId,
        timeout: 5
      });

      expect(stopResult).toMatchObject({
        containerId,
        stopped: true,
        timeout: 5
      });

      // Remove container
      const removeResult = await server.executeTool('docker_remove_container', {
        containerId,
        force: false,
        volumes: false
      });

      expect(removeResult).toMatchObject({
        containerId,
        removed: true
      });

      // Remove from tracking since it's already deleted
      createdContainers = createdContainers.filter(id => id !== containerId);
    }, 30000);

    it('should restart a container', async () => {
      if (!server) return;

      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-restart',
        image: 'alpine:latest',
        command: ['sleep', '30'],
        autoRemove: false
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      // Start container
      await server.executeTool('docker_start_container', {
        containerId
      });

      // Restart container
      const restartResult = await server.executeTool('docker_restart_container', {
        containerId,
        timeout: 5
      });

      expect(restartResult).toMatchObject({
        containerId,
        restarted: true,
        timeout: 5
      });
    }, 30000);
  });

  describe('Container Execution', () => {
    it('should execute commands in a running container', async () => {
      if (!server) return;

      // Create and start a container
      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-exec',
        image: 'alpine:latest',
        command: ['sleep', '30'],
        autoRemove: false
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      await server.executeTool('docker_start_container', {
        containerId
      });

      // Execute command
      const execResult = await server.executeTool('docker_exec', {
        containerId,
        command: ['echo', 'Hello from exec!'],
        detach: false
      });

      expect(execResult).toMatchObject({
        containerId,
        execId: expect.any(String),
        output: expect.stringContaining('Hello from exec!'),
        exitCode: 0
      });
    }, 30000);
  });

  describe('Container Listing and Filtering', () => {
    it('should list containers with filters', async () => {
      if (!server) return;

      // List all containers
      const allContainers = await server.executeTool('docker_list_containers', {
        all: true
      });

      expect(allContainers).toMatchObject({
        containers: expect.any(Array),
        count: expect.any(Number)
      });

      // List running containers only
      const runningContainers = await server.executeTool('docker_list_containers', {
        all: false
      });

      expect(runningContainers).toMatchObject({
        containers: expect.any(Array),
        count: expect.any(Number)
      });
    });
  });

  describe('Volume Management', () => {
    it('should create, list, and remove volumes', async () => {
      if (!server) return;

      const volumeName = 'mcp-test-volume';

      // Create volume
      const createResult = await server.executeTool('docker_create_volume', {
        name: volumeName,
        driver: 'local',
        labels: {
          'test': 'mcp'
        }
      });

      expect(createResult).toMatchObject({
        name: volumeName,
        driver: 'local',
        created: true
      });

      createdVolumes.push(volumeName);

      // List volumes
      const listResult = await server.executeTool('docker_list_volumes', {});

      expect(listResult).toMatchObject({
        volumes: expect.arrayContaining([
          expect.objectContaining({
            Name: volumeName
          })
        ])
      });

      // Remove volume
      const removeResult = await server.executeTool('docker_remove_volume', {
        volumeName,
        force: false
      });

      expect(removeResult).toMatchObject({
        volumeName,
        removed: true
      });

      // Remove from tracking since it's deleted
      createdVolumes = createdVolumes.filter(name => name !== volumeName);
    });
  });

  describe('Network Management', () => {
    it('should create, list, and remove networks', async () => {
      if (!server) return;

      const networkName = 'mcp-test-network';

      // Create network
      const createResult = await server.executeTool('docker_create_network', {
        name: networkName,
        driver: 'bridge',
        labels: {
          'test': 'mcp'
        }
      });

      expect(createResult).toMatchObject({
        id: expect.any(String),
        name: networkName,
        driver: 'bridge',
        created: true
      });

      const networkId = (createResult as any).id;
      createdNetworks.push(networkId);

      // List networks
      const listResult = await server.executeTool('docker_list_networks', {});

      expect(listResult).toMatchObject({
        networks: expect.arrayContaining([
          expect.objectContaining({
            name: networkName
          })
        ]),
        count: expect.any(Number)
      });

      // Remove network
      const removeResult = await server.executeTool('docker_remove_network', {
        networkId
      });

      expect(removeResult).toMatchObject({
        networkId,
        removed: true
      });

      // Remove from tracking since it's deleted
      createdNetworks = createdNetworks.filter(id => id !== networkId);
    });
  });

  describe('Resource Management', () => {
    it('should enforce resource limits', async () => {
      if (!server) return;

      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-limits',
        image: 'alpine:latest',
        command: ['sleep', '10'],
        memory: '256MB',
        cpus: '0.25'
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      // Inspect container to verify limits
      const inspectResult = await server.executeTool('docker_inspect_container', {
        containerId
      });

      expect((inspectResult as any).hostConfig.memory).toBeGreaterThan(0);
      expect((inspectResult as any).hostConfig.cpuQuota).toBeGreaterThan(0);
    });

    it('should get container statistics', async () => {
      if (!server) return;

      const createResult = await server.executeTool('docker_create_container', {
        name: 'mcp-test-stats',
        image: 'alpine:latest',
        command: ['sleep', '10']
      });

      const containerId = (createResult as any).id;
      createdContainers.push(containerId);

      await server.executeTool('docker_start_container', {
        containerId
      });

      // Get stats
      const statsResult = await server.executeTool('docker_container_stats', {
        containerId,
        stream: false
      });

      expect(statsResult).toMatchObject({
        containerId,
        stats: expect.any(Object),
        timestamp: expect.any(String)
      });
    }, 30000);
  });

  describe('Security and Validation', () => {
    it('should prevent unauthorized image usage', async () => {
      if (!server) return;

      await expect(
        server.executeTool('docker_create_container', {
          image: 'unauthorized:latest',
          name: 'test-unauthorized'
        })
      ).rejects.toThrow('not in the allowed list');
    });

    it('should validate resource limits', async () => {
      if (!server) return;

      await expect(
        server.executeTool('docker_create_container', {
          image: 'alpine:latest',
          memory: 'invalid-format'
        })
      ).rejects.toThrow('Invalid memory limit format');
    });
  });

  describe('Operation Tracking', () => {
    it('should track Docker operations', async () => {
      if (!server) return;

      // Check tracking status
      const statusResult = await server.executeTool('getOperationHistory', {});
      expect((statusResult as any).trackingEnabled).toBe(true);

      // Toggle tracking
      const toggleResult = await server.executeTool('toggleOperationTracking', {
        enabled: false
      });

      expect(toggleResult).toMatchObject({
        trackingEnabled: false,
        changed: true
      });
    });

    it('should update resource limits', async () => {
      if (!server) return;

      const updateResult = await server.executeTool('updateResourceLimits', {
        memory: '4GB',
        cpus: '2.0'
      });

      expect(updateResult).toMatchObject({
        defaultLimits: {
          memory: '4GB',
          cpus: '2.0'
        },
        updated: true
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle non-existent containers gracefully', async () => {
      if (!server) return;

      await expect(
        server.executeTool('docker_start_container', {
          containerId: 'non-existent-container'
        })
      ).rejects.toThrow("Resource 'non-existent-container' not found");
    });

    it('should handle non-existent images gracefully', async () => {
      if (!server) return;

      await expect(
        server.executeTool('docker_remove_image', {
          imageId: 'non-existent-image'
        })
      ).rejects.toThrow("Resource 'non-existent-image' not found");
    });
  });
});