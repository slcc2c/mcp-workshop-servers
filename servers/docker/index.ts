/**
 * Docker MCP Server
 * Provides container management with resource limits and isolation
 */

import { z } from 'zod';
import Docker from 'dockerode';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { config } from '../../src/utils/config';
import { ResourceLimitError, ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const ContainerCreateSchema = z.object({
  name: z.string().optional().describe('Container name (auto-generated if not provided)'),
  image: z.string().describe('Docker image to use'),
  command: z.array(z.string()).optional().describe('Command to run in container'),
  env: z.record(z.string()).default({}).describe('Environment variables'),
  ports: z.record(z.string()).default({}).describe('Port mappings (container:host)'),
  volumes: z.record(z.string()).default({}).describe('Volume mounts (host:container)'),
  workingDir: z.string().optional().describe('Working directory in container'),
  user: z.string().optional().describe('User to run as'),
  memory: z.string().default('2GB').describe('Memory limit (e.g., 1GB, 512MB)'),
  cpus: z.string().default('1.0').describe('CPU limit (e.g., 0.5, 2.0)'),
  autoRemove: z.boolean().default(true).describe('Remove container when it stops'),
  detach: z.boolean().default(true).describe('Run container in background'),
});

const ContainerActionSchema = z.object({
  containerId: z.string().describe('Container ID or name'),
});

const ContainerLogsSchema = z.object({
  containerId: z.string().describe('Container ID or name'),
  follow: z.boolean().default(false).describe('Follow log output'),
  tail: z.number().default(100).describe('Number of lines to show from end'),
  since: z.string().optional().describe('Show logs since timestamp'),
  timestamps: z.boolean().default(false).describe('Show timestamps'),
});

const ContainerExecSchema = z.object({
  containerId: z.string().describe('Container ID or name'),
  command: z.array(z.string()).describe('Command to execute'),
  user: z.string().optional().describe('User to run as'),
  workingDir: z.string().optional().describe('Working directory'),
  env: z.array(z.string()).default([]).describe('Environment variables (KEY=value format)'),
  detach: z.boolean().default(false).describe('Run in background'),
});

const ImageBuildSchema = z.object({
  tag: z.string().describe('Image tag'),
  dockerfile: z.string().optional().describe('Dockerfile content (if not using context)'),
  context: z.string().optional().describe('Build context directory'),
  buildArgs: z.record(z.string()).default({}).describe('Build arguments'),
  labels: z.record(z.string()).default({}).describe('Image labels'),
  target: z.string().optional().describe('Build target stage'),
});

const ImagePullSchema = z.object({
  image: z.string().describe('Image name to pull'),
  tag: z.string().default('latest').describe('Image tag'),
  platform: z.string().optional().describe('Platform (e.g., linux/amd64)'),
});

const VolumeCreateSchema = z.object({
  name: z.string().describe('Volume name'),
  driver: z.string().default('local').describe('Volume driver'),
  labels: z.record(z.string()).default({}).describe('Volume labels'),
  options: z.record(z.string()).default({}).describe('Driver-specific options'),
});

const NetworkCreateSchema = z.object({
  name: z.string().describe('Network name'),
  driver: z.string().default('bridge').describe('Network driver'),
  options: z.record(z.string()).default({}).describe('Driver options'),
  labels: z.record(z.string()).default({}).describe('Network labels'),
});

interface ContainerInfo {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  created: Date;
  ports: any[];
  mounts: any[];
}

export class DockerServer extends BaseMCPServer {
  private docker: Docker;
  private defaultLimits: {
    memory: string;
    cpus: string;
  };
  private allowedImages: string[];
  private trackOperations: boolean = true;

  constructor() {
    super('docker', '1.0.0', 'Docker container management with resource limits');
    
    this.defaultLimits = {
      memory: '2GB',
      cpus: '1.0',
    };
    
    // Default allowed images - in production, this should be configurable
    this.allowedImages = [
      'node:*',
      'python:*',
      'nginx:*',
      'redis:*',
      'postgres:*',
      'mysql:*',
      'ubuntu:*',
      'alpine:*',
      'mongo:*',
      'hello-world:*',
    ];
  }

  protected async onInitialize(): Promise<void> {
    const dockerConfig = config.getDatabaseUrl('docker') || 'unix:///var/run/docker.sock';
    
    try {
      this.docker = new Docker({
        socketPath: dockerConfig.startsWith('unix://') ? dockerConfig.replace('unix://', '') : undefined,
        host: dockerConfig.startsWith('tcp://') ? dockerConfig.replace('tcp://', '').split(':')[0] : undefined,
        port: dockerConfig.startsWith('tcp://') ? parseInt(dockerConfig.replace('tcp://', '').split(':')[1]) : undefined,
      });

      // Test Docker connection
      await this.docker.ping();
      
      const version = await this.docker.version();
      this.logger.info('Docker connection established', {
        version: version.Version,
        apiVersion: version.ApiVersion,
      });
    } catch (error) {
      this.logger.error('Failed to connect to Docker', { error });
      throw new Error('Docker daemon not available. Ensure Docker is running and accessible.');
    }
  }

  protected async onShutdown(): Promise<void> {
    // Cleanup any resources if needed
    this.logger.info('Docker server shut down');
  }

  protected async registerTools(): Promise<void> {
    // Container lifecycle
    this.registerTool(
      'docker_create_container',
      'Create a new Docker container',
      ContainerCreateSchema,
      createToolHandler(async (params) => {
        return this.createContainer(params);
      })
    );

    this.registerTool(
      'docker_start_container',
      'Start a Docker container',
      ContainerActionSchema,
      createToolHandler(async ({ containerId }) => {
        return this.startContainer(containerId);
      })
    );

    this.registerTool(
      'docker_stop_container',
      'Stop a Docker container',
      z.object({
        containerId: z.string().describe('Container ID or name'),
        timeout: z.number().default(10).describe('Timeout in seconds'),
      }),
      createToolHandler(async ({ containerId, timeout }) => {
        return this.stopContainer(containerId, timeout);
      })
    );

    this.registerTool(
      'docker_remove_container',
      'Remove a Docker container',
      z.object({
        containerId: z.string().describe('Container ID or name'),
        force: z.boolean().default(false).describe('Force remove running container'),
        volumes: z.boolean().default(false).describe('Remove associated volumes'),
      }),
      createToolHandler(async ({ containerId, force, volumes }) => {
        return this.removeContainer(containerId, force, volumes);
      })
    );

    this.registerTool(
      'docker_restart_container',
      'Restart a Docker container',
      z.object({
        containerId: z.string().describe('Container ID or name'),
        timeout: z.number().default(10).describe('Timeout in seconds'),
      }),
      createToolHandler(async ({ containerId, timeout }) => {
        return this.restartContainer(containerId, timeout);
      })
    );

    // Container information
    this.registerTool(
      'docker_list_containers',
      'List Docker containers',
      z.object({
        all: z.boolean().default(false).describe('Show all containers (including stopped)'),
        filters: z.record(z.string()).default({}).describe('Filters to apply'),
      }),
      createToolHandler(async ({ all, filters }) => {
        return this.listContainers(all, filters);
      })
    );

    this.registerTool(
      'docker_inspect_container',
      'Get detailed container information',
      ContainerActionSchema,
      createToolHandler(async ({ containerId }) => {
        return this.inspectContainer(containerId);
      })
    );

    this.registerTool(
      'docker_container_logs',
      'Get container logs',
      ContainerLogsSchema,
      createToolHandler(async (params) => {
        return this.getContainerLogs(params);
      })
    );

    this.registerTool(
      'docker_container_stats',
      'Get container resource usage statistics',
      z.object({
        containerId: z.string().describe('Container ID or name'),
        stream: z.boolean().default(false).describe('Stream stats continuously'),
      }),
      createToolHandler(async ({ containerId, stream }) => {
        return this.getContainerStats(containerId, stream);
      })
    );

    // Container execution
    this.registerTool(
      'docker_exec',
      'Execute command in running container',
      ContainerExecSchema,
      createToolHandler(async (params) => {
        return this.execInContainer(params);
      })
    );

    // Image management
    this.registerTool(
      'docker_list_images',
      'List Docker images',
      z.object({
        all: z.boolean().default(false).describe('Show all images (including intermediates)'),
        filters: z.record(z.string()).default({}).describe('Filters to apply'),
      }),
      createToolHandler(async ({ all, filters }) => {
        return this.listImages(all, filters);
      })
    );

    this.registerTool(
      'docker_pull_image',
      'Pull Docker image from registry',
      ImagePullSchema,
      createToolHandler(async (params) => {
        return this.pullImage(params);
      })
    );

    this.registerTool(
      'docker_build_image',
      'Build Docker image',
      ImageBuildSchema,
      createToolHandler(async (params) => {
        return this.buildImage(params);
      })
    );

    this.registerTool(
      'docker_remove_image',
      'Remove Docker image',
      z.object({
        imageId: z.string().describe('Image ID or name'),
        force: z.boolean().default(false).describe('Force remove image'),
        noPrune: z.boolean().default(false).describe('Do not delete untagged parents'),
      }),
      createToolHandler(async ({ imageId, force, noPrune }) => {
        return this.removeImage(imageId, force, noPrune);
      })
    );

    // Volume management
    this.registerTool(
      'docker_create_volume',
      'Create Docker volume',
      VolumeCreateSchema,
      createToolHandler(async (params) => {
        return this.createVolume(params);
      })
    );

    this.registerTool(
      'docker_list_volumes',
      'List Docker volumes',
      z.object({
        filters: z.record(z.string()).default({}).describe('Filters to apply'),
      }),
      createToolHandler(async ({ filters }) => {
        return this.listVolumes(filters);
      })
    );

    this.registerTool(
      'docker_remove_volume',
      'Remove Docker volume',
      z.object({
        volumeName: z.string().describe('Volume name'),
        force: z.boolean().default(false).describe('Force remove volume'),
      }),
      createToolHandler(async ({ volumeName, force }) => {
        return this.removeVolume(volumeName, force);
      })
    );

    // Network management
    this.registerTool(
      'docker_create_network',
      'Create Docker network',
      NetworkCreateSchema,
      createToolHandler(async (params) => {
        return this.createNetwork(params);
      })
    );

    this.registerTool(
      'docker_list_networks',
      'List Docker networks',
      z.object({
        filters: z.record(z.string()).default({}).describe('Filters to apply'),
      }),
      createToolHandler(async ({ filters }) => {
        return this.listNetworks(filters);
      })
    );

    this.registerTool(
      'docker_remove_network',
      'Remove Docker network',
      z.object({
        networkId: z.string().describe('Network ID or name'),
      }),
      createToolHandler(async ({ networkId }) => {
        return this.removeNetwork(networkId);
      })
    );

    // System operations
    this.registerTool(
      'docker_system_info',
      'Get Docker system information',
      z.object({}),
      createToolHandler(async () => {
        return this.getSystemInfo();
      })
    );

    this.registerTool(
      'docker_system_prune',
      'Clean up unused Docker resources',
      z.object({
        volumes: z.boolean().default(false).describe('Prune volumes'),
        all: z.boolean().default(false).describe('Remove all unused images'),
        filters: z.record(z.string()).default({}).describe('Filters to apply'),
      }),
      createToolHandler(async ({ volumes, all, filters }) => {
        return this.systemPrune(volumes, all, filters);
      })
    );
  }

  private validateImage(image: string): void {
    const isAllowed = this.allowedImages.some(pattern => {
      if (pattern.endsWith('*')) {
        const prefix = pattern.slice(0, -1);
        return image.startsWith(prefix);
      }
      return image === pattern;
    });

    if (!isAllowed) {
      throw new InvalidParamsError(`Image '${image}' is not in the allowed list. Allowed patterns: ${this.allowedImages.join(', ')}`);
    }
  }

  private parseResourceLimit(limit: string, type: 'memory' | 'cpu'): number | string {
    if (type === 'memory') {
      const units: Record<string, number> = {
        'b': 1,
        'k': 1024,
        'kb': 1024,
        'm': 1024 * 1024,
        'mb': 1024 * 1024,
        'g': 1024 * 1024 * 1024,
        'gb': 1024 * 1024 * 1024,
      };

      const match = limit.toLowerCase().match(/^(\d+(?:\.\d+)?)\s*([a-z]+)?$/);
      if (!match) {
        throw new InvalidParamsError(`Invalid memory limit format: ${limit}`);
      }

      const value = parseFloat(match[1]);
      const unit = match[2] || 'b';
      const multiplier = units[unit];

      if (!multiplier) {
        throw new InvalidParamsError(`Invalid memory unit: ${unit}`);
      }

      return Math.floor(value * multiplier);
    } else {
      // CPU limit as string for Docker API
      return limit;
    }
  }

  private async createContainer(params: z.infer<typeof ContainerCreateSchema>) {
    this.validateImage(params.image);

    const memoryLimit = this.parseResourceLimit(params.memory, 'memory') as number;
    const cpuLimit = params.cpus;

    // Generate name if not provided
    const containerName = params.name || `mcp-container-${Date.now()}`;

    const createOptions: any = {
      Image: params.image,
      name: containerName,
      Env: Object.entries(params.env).map(([key, value]) => `${key}=${value}`),
      WorkingDir: params.workingDir,
      User: params.user,
      HostConfig: {
        Memory: memoryLimit,
        CpuQuota: Math.floor(parseFloat(cpuLimit) * 100000),
        CpuPeriod: 100000,
        AutoRemove: params.autoRemove,
        PortBindings: {},
        Binds: [],
      },
      ExposedPorts: {},
    };

    // Set up port mappings
    for (const [containerPort, hostPort] of Object.entries(params.ports)) {
      createOptions.ExposedPorts[`${containerPort}/tcp`] = {};
      createOptions.HostConfig.PortBindings[`${containerPort}/tcp`] = [{ HostPort: hostPort }];
    }

    // Set up volume mounts
    for (const [hostPath, containerPath] of Object.entries(params.volumes)) {
      createOptions.HostConfig.Binds.push(`${hostPath}:${containerPath}`);
    }

    // Set command if provided
    if (params.command && params.command.length > 0) {
      createOptions.Cmd = params.command;
    }

    try {
      const container = await this.docker.createContainer(createOptions);
      
      if (this.trackOperations) {
        await this.trackOperation('create', containerName, { image: params.image, limits: { memory: params.memory, cpus: params.cpus } });
      }

      return {
        id: container.id,
        name: containerName,
        image: params.image,
        created: true,
      };
    } catch (error: any) {
      this.logger.error('Failed to create container', { error, params });
      throw new Error(`Failed to create container: ${error.message}`);
    }
  }

  private async startContainer(containerId: string) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.start();

      if (this.trackOperations) {
        await this.trackOperation('start', containerId);
      }

      return {
        containerId,
        started: true,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to start container: ${error.message}`);
    }
  }

  private async stopContainer(containerId: string, timeout: number) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.stop({ t: timeout });

      if (this.trackOperations) {
        await this.trackOperation('stop', containerId, { timeout });
      }

      return {
        containerId,
        stopped: true,
        timeout,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to stop container: ${error.message}`);
    }
  }

  private async removeContainer(containerId: string, force: boolean, volumes: boolean) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.remove({ force, v: volumes });

      if (this.trackOperations) {
        await this.trackOperation('remove', containerId, { force, volumes });
      }

      return {
        containerId,
        removed: true,
        force,
        volumes,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to remove container: ${error.message}`);
    }
  }

  private async restartContainer(containerId: string, timeout: number) {
    try {
      const container = this.docker.getContainer(containerId);
      await container.restart({ t: timeout });

      if (this.trackOperations) {
        await this.trackOperation('restart', containerId, { timeout });
      }

      return {
        containerId,
        restarted: true,
        timeout,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to restart container: ${error.message}`);
    }
  }

  private async listContainers(all: boolean, filters: Record<string, string>) {
    try {
      const containers = await this.docker.listContainers({ all, filters });
      
      const result = containers.map(container => ({
        id: container.Id,
        names: container.Names.map(name => name.startsWith('/') ? name.slice(1) : name),
        image: container.Image,
        imageId: container.ImageID,
        command: container.Command,
        created: new Date(container.Created * 1000),
        state: container.State,
        status: container.Status,
        ports: container.Ports,
        labels: container.Labels,
        sizeRw: container.SizeRw,
        sizeRootFs: container.SizeRootFs,
      }));

      return {
        containers: result,
        count: result.length,
      };
    } catch (error: any) {
      throw new Error(`Failed to list containers: ${error.message}`);
    }
  }

  private async inspectContainer(containerId: string) {
    try {
      const container = this.docker.getContainer(containerId);
      const info = await container.inspect();

      return {
        id: info.Id,
        name: info.Name.startsWith('/') ? info.Name.slice(1) : info.Name,
        image: info.Image,
        state: {
          status: info.State.Status,
          running: info.State.Running,
          paused: info.State.Paused,
          restarting: info.State.Restarting,
          oomKilled: info.State.OOMKilled,
          dead: info.State.Dead,
          pid: info.State.Pid,
          exitCode: info.State.ExitCode,
          error: info.State.Error,
          startedAt: info.State.StartedAt,
          finishedAt: info.State.FinishedAt,
        },
        config: {
          hostname: info.Config.Hostname,
          user: info.Config.User,
          workingDir: info.Config.WorkingDir,
          env: info.Config.Env,
          cmd: info.Config.Cmd,
          entrypoint: info.Config.Entrypoint,
        },
        hostConfig: {
          memory: info.HostConfig.Memory,
          cpuQuota: info.HostConfig.CpuQuota,
          cpuPeriod: info.HostConfig.CpuPeriod,
          autoRemove: info.HostConfig.AutoRemove,
        },
        networkSettings: info.NetworkSettings,
        mounts: info.Mounts,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to inspect container: ${error.message}`);
    }
  }

  private async getContainerLogs(params: z.infer<typeof ContainerLogsSchema>) {
    try {
      const container = this.docker.getContainer(params.containerId);
      
      const logOptions: any = {
        stdout: true,
        stderr: true,
        tail: params.tail,
        timestamps: params.timestamps,
      };

      if (params.since) {
        logOptions.since = params.since;
      }

      if (params.follow) {
        // For streaming logs, we'd need to implement a different approach
        // For now, just get current logs
        logOptions.follow = false;
      }

      const logs = await container.logs(logOptions);
      
      return {
        containerId: params.containerId,
        logs: logs.toString(),
        tail: params.tail,
        timestamps: params.timestamps,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${params.containerId}'`);
      }
      throw new Error(`Failed to get container logs: ${error.message}`);
    }
  }

  private async getContainerStats(containerId: string, stream: boolean) {
    try {
      const container = this.docker.getContainer(containerId);
      
      // For streaming stats, we'd need to implement a different approach
      // For now, just get current stats
      const stats = await container.stats({ stream: false });
      
      return {
        containerId,
        stats,
        timestamp: new Date(),
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${containerId}'`);
      }
      throw new Error(`Failed to get container stats: ${error.message}`);
    }
  }

  private async execInContainer(params: z.infer<typeof ContainerExecSchema>) {
    try {
      const container = this.docker.getContainer(params.containerId);
      
      const execOptions: any = {
        Cmd: params.command,
        AttachStdout: true,
        AttachStderr: true,
        User: params.user,
        WorkingDir: params.workingDir,
        Env: params.env,
      };

      const exec = await container.exec(execOptions);
      const stream = await exec.start({ Detach: params.detach });
      
      if (params.detach) {
        return {
          containerId: params.containerId,
          execId: exec.id,
          detached: true,
        };
      } else {
        // For non-detached execution, collect output
        let output = '';
        if (stream && typeof stream.on === 'function') {
          await new Promise((resolve, reject) => {
            stream.on('data', (chunk: Buffer) => {
              output += chunk.toString();
            });
            stream.on('end', resolve);
            stream.on('error', reject);
          });
        }

        const inspectData = await exec.inspect();
        
        return {
          containerId: params.containerId,
          execId: exec.id,
          output,
          exitCode: inspectData.ExitCode,
        };
      }
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Container '${params.containerId}'`);
      }
      throw new Error(`Failed to execute command: ${error.message}`);
    }
  }

  private async listImages(all: boolean, filters: Record<string, string>) {
    try {
      const images = await this.docker.listImages({ all, filters });
      
      const result = images.map(image => ({
        id: image.Id,
        parentId: image.ParentId,
        repoTags: image.RepoTags || [],
        repoDigests: image.RepoDigests || [],
        created: new Date(image.Created * 1000),
        size: image.Size,
        virtualSize: image.VirtualSize,
        sharedSize: image.SharedSize,
        labels: image.Labels,
        containers: image.Containers,
      }));

      return {
        images: result,
        count: result.length,
      };
    } catch (error: any) {
      throw new Error(`Failed to list images: ${error.message}`);
    }
  }

  private async pullImage(params: z.infer<typeof ImagePullSchema>) {
    const imageRef = `${params.image}:${params.tag}`;
    this.validateImage(imageRef);

    try {
      const stream = await this.docker.pull(imageRef, {
        platform: params.platform,
      });

      // Wait for pull to complete
      await new Promise((resolve, reject) => {
        this.docker.modem.followProgress(stream, (err: any, res: any) => {
          if (err) reject(err);
          else resolve(res);
        });
      });

      if (this.trackOperations) {
        await this.trackOperation('pull', imageRef);
      }

      return {
        image: imageRef,
        pulled: true,
        platform: params.platform,
      };
    } catch (error: any) {
      throw new Error(`Failed to pull image: ${error.message}`);
    }
  }

  private async buildImage(params: z.infer<typeof ImageBuildSchema>) {
    try {
      let buildContext: any;

      if (params.dockerfile && !params.context) {
        // Build from Dockerfile content
        const tar = await import('tar-stream');
        const pack = tar.pack();
        
        pack.entry({ name: 'Dockerfile' }, params.dockerfile);
        pack.finalize();
        
        buildContext = pack;
      } else if (params.context) {
        // Build from directory context
        buildContext = params.context;
      } else {
        throw new InvalidParamsError('Either dockerfile content or context directory must be provided');
      }

      const buildOptions: any = {
        t: params.tag,
        buildargs: params.buildArgs,
        labels: params.labels,
        target: params.target,
      };

      const stream = await this.docker.buildImage(buildContext, buildOptions);

      // Wait for build to complete and collect output
      const buildOutput: string[] = [];
      await new Promise((resolve, reject) => {
        this.docker.modem.followProgress(stream, (err: any, res: any) => {
          if (err) reject(err);
          else resolve(res);
        }, (event: any) => {
          if (event.stream) {
            buildOutput.push(event.stream);
          }
        });
      });

      if (this.trackOperations) {
        await this.trackOperation('build', params.tag, { buildArgs: params.buildArgs });
      }

      return {
        tag: params.tag,
        built: true,
        output: buildOutput.join(''),
      };
    } catch (error: any) {
      throw new Error(`Failed to build image: ${error.message}`);
    }
  }

  private async removeImage(imageId: string, force: boolean, noPrune: boolean) {
    try {
      const image = this.docker.getImage(imageId);
      const result = await image.remove({ force, noprune: noPrune });

      if (this.trackOperations) {
        await this.trackOperation('removeImage', imageId, { force, noPrune });
      }

      return {
        imageId,
        removed: true,
        result,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Image '${imageId}'`);
      }
      throw new Error(`Failed to remove image: ${error.message}`);
    }
  }

  private async createVolume(params: z.infer<typeof VolumeCreateSchema>) {
    try {
      const volume = await this.docker.createVolume({
        Name: params.name,
        Driver: params.driver,
        Labels: params.labels,
        DriverOpts: params.options,
      });

      if (this.trackOperations) {
        await this.trackOperation('createVolume', params.name, { driver: params.driver });
      }

      return {
        name: volume.Name,
        driver: volume.Driver,
        mountpoint: volume.Mountpoint,
        created: true,
      };
    } catch (error: any) {
      throw new Error(`Failed to create volume: ${error.message}`);
    }
  }

  private async listVolumes(filters: Record<string, string>) {
    try {
      const result = await this.docker.listVolumes({ filters });
      
      return {
        volumes: result.Volumes || [],
        warnings: result.Warnings || [],
      };
    } catch (error: any) {
      throw new Error(`Failed to list volumes: ${error.message}`);
    }
  }

  private async removeVolume(volumeName: string, force: boolean) {
    try {
      const volume = this.docker.getVolume(volumeName);
      await volume.remove({ force });

      if (this.trackOperations) {
        await this.trackOperation('removeVolume', volumeName, { force });
      }

      return {
        volumeName,
        removed: true,
        force,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Volume '${volumeName}'`);
      }
      throw new Error(`Failed to remove volume: ${error.message}`);
    }
  }

  private async createNetwork(params: z.infer<typeof NetworkCreateSchema>) {
    try {
      const network = await this.docker.createNetwork({
        Name: params.name,
        Driver: params.driver,
        Options: params.options,
        Labels: params.labels,
      });

      if (this.trackOperations) {
        await this.trackOperation('createNetwork', params.name, { driver: params.driver });
      }

      return {
        id: network.id,
        name: params.name,
        driver: params.driver,
        created: true,
      };
    } catch (error: any) {
      throw new Error(`Failed to create network: ${error.message}`);
    }
  }

  private async listNetworks(filters: Record<string, string>) {
    try {
      const networks = await this.docker.listNetworks({ filters });
      
      return {
        networks: networks.map(network => ({
          id: network.Id,
          name: network.Name,
          driver: network.Driver,
          scope: network.Scope,
          created: network.Created,
          labels: network.Labels,
        })),
        count: networks.length,
      };
    } catch (error: any) {
      throw new Error(`Failed to list networks: ${error.message}`);
    }
  }

  private async removeNetwork(networkId: string) {
    try {
      const network = this.docker.getNetwork(networkId);
      await network.remove();

      if (this.trackOperations) {
        await this.trackOperation('removeNetwork', networkId);
      }

      return {
        networkId,
        removed: true,
      };
    } catch (error: any) {
      if (error.statusCode === 404) {
        throw new ResourceNotFoundError(`Network '${networkId}'`);
      }
      throw new Error(`Failed to remove network: ${error.message}`);
    }
  }

  private async getSystemInfo() {
    try {
      const info = await this.docker.info();
      
      return {
        containers: info.Containers,
        containersRunning: info.ContainersRunning,
        containersPaused: info.ContainersPaused,
        containersStopped: info.ContainersStopped,
        images: info.Images,
        serverVersion: info.ServerVersion,
        kernelVersion: info.KernelVersion,
        operatingSystem: info.OperatingSystem,
        architecture: info.Architecture,
        memTotal: info.MemTotal,
        cpus: info.NCPU,
        name: info.Name,
      };
    } catch (error: any) {
      throw new Error(`Failed to get system info: ${error.message}`);
    }
  }

  private async systemPrune(volumes: boolean, all: boolean, filters: Record<string, string>) {
    try {
      const result = await this.docker.pruneSystem({
        filters: {
          ...filters,
          volumes: volumes ? 'true' : 'false',
          all: all ? 'true' : 'false',
        },
      });

      if (this.trackOperations) {
        await this.trackOperation('systemPrune', 'system', { volumes, all });
      }

      return {
        containersDeleted: result.ContainersDeleted || [],
        spaceReclaimed: result.SpaceReclaimed || 0,
        volumesDeleted: result.VolumesDeleted || [],
        imagesDeleted: result.ImagesDeleted || [],
        networksDeleted: result.NetworksDeleted || [],
      };
    } catch (error: any) {
      throw new Error(`Failed to prune system: ${error.message}`);
    }
  }

  private async trackOperation(operation: string, target: string, metadata: any = {}) {
    try {
      const operationRecord = {
        operation,
        target,
        timestamp: new Date().toISOString(),
        metadata,
        server: 'docker',
      };

      this.logger.debug('Docker operation tracked', operationRecord);

      // In a real implementation, this would integrate with Memory server
      return operationRecord;
    } catch (error) {
      this.logger.error('Failed to track Docker operation', { error, operation, target });
    }
  }

  protected getCustomMethods(): string[] {
    return ['getOperationHistory', 'toggleOperationTracking', 'updateResourceLimits'];
  }

  protected async handleCustomMethod(method: string, params: unknown): Promise<unknown> {
    switch (method) {
      case 'getOperationHistory':
        return this.getOperationHistory();
      case 'toggleOperationTracking':
        return this.toggleOperationTracking(params as any);
      case 'updateResourceLimits':
        return this.updateResourceLimits(params as any);
      default:
        return super.handleCustomMethod(method, params);
    }
  }

  private async getOperationHistory() {
    return {
      message: 'Docker operation tracking is active',
      trackingEnabled: this.trackOperations,
      defaultLimits: this.defaultLimits,
      allowedImages: this.allowedImages,
      note: 'Detailed operation history would be retrieved from Memory server'
    };
  }

  private async toggleOperationTracking(params: { enabled?: boolean } = {}) {
    if (params.enabled !== undefined) {
      this.trackOperations = params.enabled;
    } else {
      this.trackOperations = !this.trackOperations;
    }

    return {
      trackingEnabled: this.trackOperations,
      changed: true,
    };
  }

  private async updateResourceLimits(params: { memory?: string; cpus?: string }) {
    if (params.memory) {
      this.defaultLimits.memory = params.memory;
    }
    if (params.cpus) {
      this.defaultLimits.cpus = params.cpus;
    }

    return {
      defaultLimits: this.defaultLimits,
      updated: true,
    };
  }
}