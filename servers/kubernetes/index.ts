/**
 * Kubernetes MCP Server
 * Provides container orchestration and deployment management
 */

import { z } from 'zod';
import { KubeConfig, CoreV1Api, AppsV1Api, BatchV1Api, V1Pod, V1Deployment, V1Service, V1ConfigMap, V1Secret, V1Job, V1Namespace } from '@kubernetes/client-node';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError } from '../../src/utils/errors';

// Input schemas
const NamespaceSchema = z.object({
  namespace: z.string().default('default').describe('Kubernetes namespace'),
});

const PodSchema = z.object({
  name: z.string().describe('Pod name'),
  namespace: z.string().default('default').describe('Namespace'),
  image: z.string().describe('Container image'),
  ports: z.array(z.number()).optional().describe('Container ports'),
  env: z.record(z.string()).optional().describe('Environment variables'),
  labels: z.record(z.string()).optional().describe('Pod labels'),
  resources: z.object({
    requests: z.object({
      memory: z.string().optional(),
      cpu: z.string().optional(),
    }).optional(),
    limits: z.object({
      memory: z.string().optional(),
      cpu: z.string().optional(),
    }).optional(),
  }).optional().describe('Resource requirements'),
});

const DeploymentSchema = z.object({
  name: z.string().describe('Deployment name'),
  namespace: z.string().default('default').describe('Namespace'),
  image: z.string().describe('Container image'),
  replicas: z.number().default(1).describe('Number of replicas'),
  ports: z.array(z.object({
    containerPort: z.number(),
    protocol: z.enum(['TCP', 'UDP']).default('TCP'),
  })).optional().describe('Container ports'),
  env: z.record(z.string()).optional().describe('Environment variables'),
  labels: z.record(z.string()).optional().describe('Deployment labels'),
  resources: z.object({
    requests: z.object({
      memory: z.string().optional(),
      cpu: z.string().optional(),
    }).optional(),
    limits: z.object({
      memory: z.string().optional(),
      cpu: z.string().optional(),
    }).optional(),
  }).optional().describe('Resource requirements'),
});

const ServiceSchema = z.object({
  name: z.string().describe('Service name'),
  namespace: z.string().default('default').describe('Namespace'),
  selector: z.record(z.string()).describe('Pod selector labels'),
  ports: z.array(z.object({
    port: z.number(),
    targetPort: z.number(),
    protocol: z.enum(['TCP', 'UDP']).default('TCP'),
    name: z.string().optional(),
  })).describe('Service ports'),
  type: z.enum(['ClusterIP', 'NodePort', 'LoadBalancer']).default('ClusterIP').describe('Service type'),
});

const ConfigMapSchema = z.object({
  name: z.string().describe('ConfigMap name'),
  namespace: z.string().default('default').describe('Namespace'),
  data: z.record(z.string()).describe('Key-value data'),
});

const SecretSchema = z.object({
  name: z.string().describe('Secret name'),
  namespace: z.string().default('default').describe('Namespace'),
  data: z.record(z.string()).describe('Key-value data (will be base64 encoded)'),
  type: z.string().default('Opaque').describe('Secret type'),
});

const JobSchema = z.object({
  name: z.string().describe('Job name'),
  namespace: z.string().default('default').describe('Namespace'),
  image: z.string().describe('Container image'),
  command: z.array(z.string()).optional().describe('Container command'),
  args: z.array(z.string()).optional().describe('Container arguments'),
  env: z.record(z.string()).optional().describe('Environment variables'),
  backoffLimit: z.number().default(6).describe('Number of retries before marking job as failed'),
  ttlSecondsAfterFinished: z.number().optional().describe('TTL for cleaning up finished jobs'),
});

const ScaleSchema = z.object({
  name: z.string().describe('Deployment name'),
  namespace: z.string().default('default').describe('Namespace'),
  replicas: z.number().describe('Number of replicas'),
});

const LogsSchema = z.object({
  name: z.string().describe('Pod name'),
  namespace: z.string().default('default').describe('Namespace'),
  container: z.string().optional().describe('Container name (for multi-container pods)'),
  lines: z.number().default(100).describe('Number of lines to tail'),
  follow: z.boolean().default(false).describe('Follow log output'),
  previous: z.boolean().default(false).describe('Get logs from previous container instance'),
});

export class KubernetesServer extends BaseMCPServer {
  private kubeConfig!: KubeConfig;
  private coreApi!: CoreV1Api;
  private appsApi!: AppsV1Api;
  private batchApi!: BatchV1Api;

  constructor() {
    super('kubernetes', '1.0.0', 'Kubernetes container orchestration and deployment management');
  }

  protected async onInitialize(): Promise<void> {
    this.kubeConfig = new KubeConfig();
    
    // Try to load kubeconfig from various sources
    try {
      if (process.env.KUBECONFIG) {
        this.kubeConfig.loadFromFile(process.env.KUBECONFIG);
      } else {
        this.kubeConfig.loadFromDefault();
      }
    } catch (error) {
      // Try in-cluster config if running inside a pod
      try {
        this.kubeConfig.loadFromCluster();
      } catch (clusterError) {
        throw new Error('Failed to load Kubernetes configuration. Set KUBECONFIG environment variable or run from within a cluster.');
      }
    }

    // Initialize API clients
    this.coreApi = this.kubeConfig.makeApiClient(CoreV1Api);
    this.appsApi = this.kubeConfig.makeApiClient(AppsV1Api);
    // NetworkingV1Api can be added when needed for ingress/network policy management
    this.batchApi = this.kubeConfig.makeApiClient(BatchV1Api);

    // Test connection
    try {
      await this.coreApi.listNamespace();
      this.logger.info('Kubernetes server initialized', {
        context: this.kubeConfig.getCurrentContext(),
      });
    } catch (error: any) {
      throw new Error(`Failed to connect to Kubernetes cluster: ${error.message}`);
    }
  }

  protected async onShutdown(): Promise<void> {
    // No persistent connections to close
    this.logger.info('Kubernetes server shutdown');
  }

  protected async registerTools(): Promise<void> {
    // Namespace operations
    this.registerTool(
      'k8s_list_namespaces',
      'List all namespaces',
      z.object({}),
      createToolHandler(async () => {
        const response = await this.coreApi.listNamespace();
        
        return {
          namespaces: response.body.items.map(ns => ({
            name: ns.metadata?.name,
            status: ns.status?.phase,
            created: ns.metadata?.creationTimestamp,
          })),
          count: response.body.items.length,
        };
      })
    );

    this.registerTool(
      'k8s_create_namespace',
      'Create a new namespace',
      z.object({
        name: z.string().describe('Namespace name'),
        labels: z.record(z.string()).optional().describe('Namespace labels'),
      }),
      createToolHandler<any>(async (params) => {
        const namespace: V1Namespace = {
          metadata: {
            name: params.name,
            labels: params.labels,
          },
        };

        const response = await this.coreApi.createNamespace(namespace);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          created: response.body.metadata?.creationTimestamp,
        };
      })
    );

    // Pod operations
    this.registerTool(
      'k8s_list_pods',
      'List pods in a namespace',
      NamespaceSchema,
      createToolHandler<any>(async (params) => {
        const response = await this.coreApi.listNamespacedPod(params.namespace);
        
        return {
          pods: response.body.items.map(pod => ({
            name: pod.metadata?.name,
            status: pod.status?.phase,
            ready: pod.status?.containerStatuses?.every(cs => cs.ready) || false,
            restarts: pod.status?.containerStatuses?.reduce((sum, cs) => sum + cs.restartCount, 0) || 0,
            age: pod.metadata?.creationTimestamp,
            node: pod.spec?.nodeName,
          })),
          count: response.body.items.length,
        };
      })
    );

    this.registerTool(
      'k8s_create_pod',
      'Create a new pod',
      PodSchema,
      createToolHandler<any>(async (params) => {
        const pod: V1Pod = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
            labels: params.labels,
          },
          spec: {
            containers: [{
              name: params.name,
              image: params.image,
              ports: params.ports?.map((port: number) => ({ containerPort: port })),
              env: params.env ? Object.entries(params.env).map(([name, value]) => ({ name, value: String(value) })) : undefined,
              resources: params.resources,
            }],
          },
        };

        const response = await this.coreApi.createNamespacedPod(params.namespace, pod);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
        };
      })
    );

    this.registerTool(
      'k8s_delete_pod',
      'Delete a pod',
      z.object({
        name: z.string().describe('Pod name'),
        namespace: z.string().default('default').describe('Namespace'),
      }),
      createToolHandler<any>(async (params) => {
        await this.coreApi.deleteNamespacedPod(params.name, params.namespace);
        
        return {
          success: true,
          name: params.name,
          namespace: params.namespace,
        };
      })
    );

    // Deployment operations
    this.registerTool(
      'k8s_list_deployments',
      'List deployments in a namespace',
      NamespaceSchema,
      createToolHandler<any>(async (params) => {
        const response = await this.appsApi.listNamespacedDeployment(params.namespace);
        
        return {
          deployments: response.body.items.map(deploy => ({
            name: deploy.metadata?.name,
            replicas: deploy.spec?.replicas,
            ready: deploy.status?.readyReplicas || 0,
            available: deploy.status?.availableReplicas || 0,
            age: deploy.metadata?.creationTimestamp,
          })),
          count: response.body.items.length,
        };
      })
    );

    this.registerTool(
      'k8s_create_deployment',
      'Create a new deployment',
      DeploymentSchema,
      createToolHandler<any>(async (params) => {
        const deployment: V1Deployment = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
            labels: params.labels,
          },
          spec: {
            replicas: params.replicas,
            selector: {
              matchLabels: {
                app: params.name,
              },
            },
            template: {
              metadata: {
                labels: {
                  app: params.name,
                  ...params.labels,
                },
              },
              spec: {
                containers: [{
                  name: params.name,
                  image: params.image,
                  ports: params.ports,
                  env: params.env ? Object.entries(params.env).map(([name, value]) => ({ name, value: String(value) })) : undefined,
                  resources: params.resources,
                }],
              },
            },
          },
        };

        const response = await this.appsApi.createNamespacedDeployment(params.namespace, deployment);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
        };
      })
    );

    this.registerTool(
      'k8s_scale_deployment',
      'Scale a deployment',
      ScaleSchema,
      createToolHandler<any>(async (params) => {
        const deployment = await this.appsApi.readNamespacedDeployment(params.name, params.namespace);
        deployment.body.spec!.replicas = params.replicas;
        
        await this.appsApi.replaceNamespacedDeployment(
          params.name,
          params.namespace,
          deployment.body
        );
        
        return {
          success: true,
          name: params.name,
          replicas: params.replicas,
          previousReplicas: deployment.body.spec?.replicas,
        };
      })
    );

    this.registerTool(
      'k8s_delete_deployment',
      'Delete a deployment',
      z.object({
        name: z.string().describe('Deployment name'),
        namespace: z.string().default('default').describe('Namespace'),
      }),
      createToolHandler<any>(async (params) => {
        await this.appsApi.deleteNamespacedDeployment(params.name, params.namespace);
        
        return {
          success: true,
          name: params.name,
          namespace: params.namespace,
        };
      })
    );

    // Service operations
    this.registerTool(
      'k8s_list_services',
      'List services in a namespace',
      NamespaceSchema,
      createToolHandler<any>(async (params) => {
        const response = await this.coreApi.listNamespacedService(params.namespace);
        
        return {
          services: response.body.items.map(svc => ({
            name: svc.metadata?.name,
            type: svc.spec?.type,
            clusterIP: svc.spec?.clusterIP,
            ports: svc.spec?.ports?.map(p => `${p.port}:${p.targetPort}`),
            age: svc.metadata?.creationTimestamp,
          })),
          count: response.body.items.length,
        };
      })
    );

    this.registerTool(
      'k8s_create_service',
      'Create a new service',
      ServiceSchema,
      createToolHandler<any>(async (params) => {
        const service: V1Service = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
          },
          spec: {
            selector: params.selector,
            ports: params.ports,
            type: params.type,
          },
        };

        const response = await this.coreApi.createNamespacedService(params.namespace, service);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
          clusterIP: response.body.spec?.clusterIP,
        };
      })
    );

    // ConfigMap operations
    this.registerTool(
      'k8s_create_configmap',
      'Create a ConfigMap',
      ConfigMapSchema,
      createToolHandler<any>(async (params) => {
        const configMap: V1ConfigMap = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
          },
          data: params.data,
        };

        const response = await this.coreApi.createNamespacedConfigMap(params.namespace, configMap);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
          keys: Object.keys(params.data),
        };
      })
    );

    // Secret operations
    this.registerTool(
      'k8s_create_secret',
      'Create a Secret',
      SecretSchema,
      createToolHandler<any>(async (params) => {
        const secret: V1Secret = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
          },
          type: params.type,
          stringData: params.data, // Kubernetes will base64 encode for us
        };

        const response = await this.coreApi.createNamespacedSecret(params.namespace, secret);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
          type: response.body.type,
          keys: Object.keys(params.data),
        };
      })
    );

    // Job operations
    this.registerTool(
      'k8s_create_job',
      'Create a Job',
      JobSchema,
      createToolHandler<any>(async (params) => {
        const job: V1Job = {
          metadata: {
            name: params.name,
            namespace: params.namespace,
          },
          spec: {
            backoffLimit: params.backoffLimit,
            ttlSecondsAfterFinished: params.ttlSecondsAfterFinished,
            template: {
              spec: {
                containers: [{
                  name: params.name,
                  image: params.image,
                  command: params.command,
                  args: params.args,
                  env: params.env ? Object.entries(params.env).map(([name, value]) => ({ name, value: String(value) })) : undefined,
                }],
                restartPolicy: 'Never',
              },
            },
          },
        };

        const response = await this.batchApi.createNamespacedJob(params.namespace, job);
        
        return {
          success: true,
          name: response.body.metadata?.name,
          namespace: response.body.metadata?.namespace,
        };
      })
    );

    this.registerTool(
      'k8s_list_jobs',
      'List jobs in a namespace',
      NamespaceSchema,
      createToolHandler<any>(async (params) => {
        const response = await this.batchApi.listNamespacedJob(params.namespace);
        
        return {
          jobs: response.body.items.map(job => ({
            name: job.metadata?.name,
            active: job.status?.active || 0,
            succeeded: job.status?.succeeded || 0,
            failed: job.status?.failed || 0,
            completionTime: job.status?.completionTime,
            age: job.metadata?.creationTimestamp,
          })),
          count: response.body.items.length,
        };
      })
    );

    // Logs
    this.registerTool(
      'k8s_get_logs',
      'Get pod logs',
      LogsSchema,
      createToolHandler<any>(async (params) => {
        try {
          const response = await this.coreApi.readNamespacedPodLog(
            params.name,
            params.namespace,
            params.container,
            params.follow,
            undefined,
            undefined,
            params.previous,
            undefined,
            undefined,
            params.lines
          );
          
          return {
            logs: response.body,
            pod: params.name,
            container: params.container,
            lines: params.lines,
          };
        } catch (error: any) {
          if (error.response?.statusCode === 404) {
            throw new ResourceNotFoundError(`Pod "${params.name}" not found in namespace "${params.namespace}"`);
          }
          throw error;
        }
      })
    );

    // Events
    this.registerTool(
      'k8s_get_events',
      'Get events for a resource',
      z.object({
        namespace: z.string().default('default').describe('Namespace'),
        fieldSelector: z.string().optional().describe('Field selector for filtering events'),
        limit: z.number().optional().describe('Maximum number of events to return'),
      }),
      createToolHandler<any>(async (params) => {
        const response = await this.coreApi.listNamespacedEvent(
          params.namespace,
          undefined,
          undefined,
          undefined,
          params.fieldSelector,
          undefined,
          params.limit
        );
        
        return {
          events: response.body.items.map(event => ({
            type: event.type,
            reason: event.reason,
            message: event.message,
            object: `${event.involvedObject.kind}/${event.involvedObject.name}`,
            firstTimestamp: event.firstTimestamp,
            lastTimestamp: event.lastTimestamp,
            count: event.count,
          })),
          count: response.body.items.length,
        };
      })
    );

    // Cluster info
    this.registerTool(
      'k8s_cluster_info',
      'Get cluster information',
      z.object({}),
      createToolHandler(async () => {
        const nodes = await this.coreApi.listNode();
        const namespaces = await this.coreApi.listNamespace();
        
        return {
          context: this.kubeConfig.getCurrentContext(),
          nodes: {
            count: nodes.body.items.length,
            list: nodes.body.items.map(node => ({
              name: node.metadata?.name,
              status: node.status?.conditions?.find(c => c.type === 'Ready')?.status,
              version: node.status?.nodeInfo?.kubeletVersion,
              os: node.status?.nodeInfo?.operatingSystem,
              architecture: node.status?.nodeInfo?.architecture,
            })),
          },
          namespaces: {
            count: namespaces.body.items.length,
            list: namespaces.body.items.map(ns => ns.metadata?.name),
          },
        };
      })
    );
  }
}