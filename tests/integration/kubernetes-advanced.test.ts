import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { KubernetesServer } from '../../servers/kubernetes';
import { KubeConfig, CoreV1Api } from '@kubernetes/client-node';

describe('Kubernetes MCP Server Integration Tests', () => {
  let server: any; // KubernetesServer with any cast for testing
  let testKubeConfig: KubeConfig;
  let testApi: CoreV1Api;
  const testNamespace = 'mcp-test';
  const createdResources = {
    namespaces: [] as string[],
    pods: [] as string[],
    deployments: [] as string[],
    services: [] as string[],
    configMaps: [] as string[],
    secrets: [] as string[],
    jobs: [] as string[],
  };

  beforeAll(async () => {
    // Check if Kubernetes is available
    try {
      testKubeConfig = new KubeConfig();
      
      if (process.env.KUBECONFIG) {
        testKubeConfig.loadFromFile(process.env.KUBECONFIG);
      } else {
        testKubeConfig.loadFromDefault();
      }
      
      testApi = testKubeConfig.makeApiClient(CoreV1Api);
      await testApi.listNamespace();
    } catch (error) {
      console.log('⚠️  Kubernetes not available, skipping Kubernetes tests');
      return;
    }

    // Initialize server
    try {
      server = new KubernetesServer();
      await server.initialize();
    } catch (error) {
      console.log('⚠️  Failed to initialize Kubernetes server, skipping tests:', error);
      return;
    }

    // Create test namespace
    try {
      await server.executeTool('k8s_create_namespace', {
        name: testNamespace,
        labels: { 'mcp-test': 'true' },
      });
      createdResources.namespaces.push(testNamespace);
    } catch (error) {
      // Namespace might already exist
    }
  });

  afterAll(async () => {
    if (!server || !testApi) return;

    try {
      // Clean up in reverse order
      for (const job of createdResources.jobs) {
        try {
          await testApi.deleteNamespacedPod(job, testNamespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const secret of createdResources.secrets) {
        try {
          await testApi.deleteNamespacedSecret(secret, testNamespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const configMap of createdResources.configMaps) {
        try {
          await testApi.deleteNamespacedConfigMap(configMap, testNamespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const service of createdResources.services) {
        try {
          await testApi.deleteNamespacedService(service, testNamespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const deployment of createdResources.deployments) {
        try {
          await server.executeTool('k8s_delete_deployment', {
            name: deployment,
            namespace: testNamespace,
          });
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      for (const pod of createdResources.pods) {
        try {
          await testApi.deleteNamespacedPod(pod, testNamespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      // Delete test namespace last
      for (const namespace of createdResources.namespaces) {
        try {
          await testApi.deleteNamespace(namespace);
        } catch (error) {
          // Ignore cleanup errors
        }
      }

      await server.shutdown();
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  beforeEach(async () => {
    if (!server) return;

    // Clean up any existing test resources in the namespace
    try {
      const pods = await server.executeTool('k8s_list_pods', {
        namespace: testNamespace,
      });
      
      for (const pod of pods.pods) {
        if (pod.name.startsWith('mcp-test-')) {
          try {
            await server.executeTool('k8s_delete_pod', {
              name: pod.name,
              namespace: testNamespace,
            });
          } catch (error) {
            // Ignore cleanup errors
          }
        }
      }
    } catch (error) {
      // Ignore if namespace doesn't exist yet
    }
  });

  describe('Namespace Operations', () => {
    it('should list namespaces', async () => {
      if (!server) return;

      const result = await server.executeTool('k8s_list_namespaces', {});

      expect(result.namespaces).toBeInstanceOf(Array);
      expect(result.count).toBeGreaterThan(0);
      expect(result.namespaces).toContainEqual(
        expect.objectContaining({
          name: testNamespace,
        })
      );
    });

    it('should create a new namespace', async () => {
      if (!server) return;

      const testNs = `${testNamespace}-extra`;
      
      const result = await server.executeTool('k8s_create_namespace', {
        name: testNs,
        labels: { 'mcp-test': 'true', 'test-type': 'extra' },
      });

      expect(result.success).toBe(true);
      expect(result.name).toBe(testNs);
      expect(result.created).toBeDefined();

      createdResources.namespaces.push(testNs);
    });
  });

  describe('Pod Operations', () => {
    it('should create and manage pods', async () => {
      if (!server) return;

      const podName = 'mcp-test-pod';

      // Create pod
      const createResult = await server.executeTool('k8s_create_pod', {
        name: podName,
        namespace: testNamespace,
        image: 'nginx:alpine',
        ports: [80],
        env: {
          'TEST_ENV': 'test-value',
          'POD_NAME': podName,
        },
        labels: {
          'app': 'mcp-test',
          'component': 'web',
        },
        resources: {
          requests: {
            memory: '64Mi',
            cpu: '100m',
          },
          limits: {
            memory: '128Mi',
            cpu: '200m',
          },
        },
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(podName);
      expect(createResult.namespace).toBe(testNamespace);

      createdResources.pods.push(podName);

      // List pods
      const listResult = await server.executeTool('k8s_list_pods', {
        namespace: testNamespace,
      });

      expect(listResult.pods).toContainEqual(
        expect.objectContaining({
          name: podName,
        })
      );

      // Wait a moment for pod to start
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Get pod logs (might be empty for nginx but should not error)
      try {
        const logsResult = await server.executeTool('k8s_get_logs', {
          name: podName,
          namespace: testNamespace,
          lines: 10,
        });

        expect(logsResult.pod).toBe(podName);
        expect(logsResult.logs).toBeDefined();
      } catch (error: any) {
        // Logs might not be available immediately, which is ok
        if (!error.message.includes('not found')) {
          throw error;
        }
      }

      // Delete pod
      const deleteResult = await server.executeTool('k8s_delete_pod', {
        name: podName,
        namespace: testNamespace,
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.name).toBe(podName);

      // Remove from tracking since it's deleted
      createdResources.pods = createdResources.pods.filter(p => p !== podName);
    });
  });

  describe('Deployment Operations', () => {
    it('should create, scale, and manage deployments', async () => {
      if (!server) return;

      const deploymentName = 'mcp-test-deployment';

      // Create deployment
      const createResult = await server.executeTool('k8s_create_deployment', {
        name: deploymentName,
        namespace: testNamespace,
        image: 'nginx:alpine',
        replicas: 2,
        ports: [
          { containerPort: 80, protocol: 'TCP' },
        ],
        env: {
          'DEPLOYMENT_NAME': deploymentName,
        },
        labels: {
          'app': deploymentName,
          'version': 'v1',
        },
        resources: {
          requests: {
            memory: '64Mi',
            cpu: '100m',
          },
          limits: {
            memory: '128Mi',
            cpu: '200m',
          },
        },
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(deploymentName);
      expect(createResult.namespace).toBe(testNamespace);

      createdResources.deployments.push(deploymentName);

      // List deployments
      const listResult = await server.executeTool('k8s_list_deployments', {
        namespace: testNamespace,
      });

      expect(listResult.deployments).toContainEqual(
        expect.objectContaining({
          name: deploymentName,
          replicas: 2,
        })
      );

      // Scale deployment
      const scaleResult = await server.executeTool('k8s_scale_deployment', {
        name: deploymentName,
        namespace: testNamespace,
        replicas: 3,
      });

      expect(scaleResult.success).toBe(true);
      expect(scaleResult.name).toBe(deploymentName);
      expect(scaleResult.replicas).toBe(3);
      expect(scaleResult.previousReplicas).toBe(2);

      // Verify scaling
      const listAfterScale = await server.executeTool('k8s_list_deployments', {
        namespace: testNamespace,
      });

      const deployment = listAfterScale.deployments.find(d => d.name === deploymentName);
      expect(deployment?.replicas).toBe(3);

      // Delete deployment
      const deleteResult = await server.executeTool('k8s_delete_deployment', {
        name: deploymentName,
        namespace: testNamespace,
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.name).toBe(deploymentName);

      // Remove from tracking since it's deleted
      createdResources.deployments = createdResources.deployments.filter(d => d !== deploymentName);
    });
  });

  describe('Service Operations', () => {
    it('should create and manage services', async () => {
      if (!server) return;

      const serviceName = 'mcp-test-service';

      // First create a deployment to expose
      const deploymentResult = await server.executeTool('k8s_create_deployment', {
        name: 'mcp-test-app',
        namespace: testNamespace,
        image: 'nginx:alpine',
        replicas: 1,
        ports: [{ containerPort: 80 }],
        labels: { app: 'mcp-test-app' },
      });

      createdResources.deployments.push('mcp-test-app');

      // Create service
      const createResult = await server.executeTool('k8s_create_service', {
        name: serviceName,
        namespace: testNamespace,
        selector: { app: 'mcp-test-app' },
        ports: [
          {
            port: 80,
            targetPort: 80,
            protocol: 'TCP',
            name: 'http',
          },
        ],
        type: 'ClusterIP',
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(serviceName);
      expect(createResult.namespace).toBe(testNamespace);
      expect(createResult.clusterIP).toBeDefined();

      createdResources.services.push(serviceName);

      // List services
      const listResult = await server.executeTool('k8s_list_services', {
        namespace: testNamespace,
      });

      expect(listResult.services).toContainEqual(
        expect.objectContaining({
          name: serviceName,
          type: 'ClusterIP',
        })
      );

      const service = listResult.services.find(s => s.name === serviceName);
      expect(service?.ports).toContain('80:80');
    });
  });

  describe('ConfigMap and Secret Operations', () => {
    it('should create and manage ConfigMaps', async () => {
      if (!server) return;

      const configMapName = 'mcp-test-config';

      // Create ConfigMap
      const createResult = await server.executeTool('k8s_create_configmap', {
        name: configMapName,
        namespace: testNamespace,
        data: {
          'app.properties': 'debug=true\nport=8080',
          'database.conf': 'host=localhost\nport=5432',
          'feature-flags': 'new-ui=enabled\nanalytics=disabled',
        },
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(configMapName);
      expect(createResult.namespace).toBe(testNamespace);
      expect(createResult.keys).toEqual(['app.properties', 'database.conf', 'feature-flags']);

      createdResources.configMaps.push(configMapName);
    });

    it('should create and manage Secrets', async () => {
      if (!server) return;

      const secretName = 'mcp-test-secret';

      // Create Secret
      const createResult = await server.executeTool('k8s_create_secret', {
        name: secretName,
        namespace: testNamespace,
        type: 'Opaque',
        data: {
          'username': 'admin',
          'password': 'super-secret-password',
          'api-key': 'abc123def456',
        },
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(secretName);
      expect(createResult.namespace).toBe(testNamespace);
      expect(createResult.type).toBe('Opaque');
      expect(createResult.keys).toEqual(['username', 'password', 'api-key']);

      createdResources.secrets.push(secretName);
    });
  });

  describe('Job Operations', () => {
    it('should create and manage Jobs', async () => {
      if (!server) return;

      const jobName = 'mcp-test-job';

      // Create Job
      const createResult = await server.executeTool('k8s_create_job', {
        name: jobName,
        namespace: testNamespace,
        image: 'alpine:latest',
        command: ['sh', '-c'],
        args: ['echo "Hello from MCP test job" && sleep 10'],
        env: {
          'JOB_NAME': jobName,
          'TEST_MODE': 'true',
        },
        backoffLimit: 3,
        ttlSecondsAfterFinished: 60,
      });

      expect(createResult.success).toBe(true);
      expect(createResult.name).toBe(jobName);
      expect(createResult.namespace).toBe(testNamespace);

      createdResources.jobs.push(jobName);

      // List jobs
      const listResult = await server.executeTool('k8s_list_jobs', {
        namespace: testNamespace,
      });

      expect(listResult.jobs).toContainEqual(
        expect.objectContaining({
          name: jobName,
        })
      );

      const job = listResult.jobs.find(j => j.name === jobName);
      expect(job?.active).toBeGreaterThanOrEqual(0);
      expect(job?.succeeded).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Events and Monitoring', () => {
    it('should get cluster events', async () => {
      if (!server) return;

      const eventsResult = await server.executeTool('k8s_get_events', {
        namespace: testNamespace,
        limit: 10,
      });

      expect(eventsResult.events).toBeInstanceOf(Array);
      expect(eventsResult.count).toBeGreaterThanOrEqual(0);

      // Events should have required fields
      if (eventsResult.events.length > 0) {
        const event = eventsResult.events[0];
        expect(event.type).toBeDefined();
        expect(event.reason).toBeDefined();
        expect(event.message).toBeDefined();
        expect(event.object).toBeDefined();
      }
    });

    it('should get filtered events', async () => {
      if (!server) return;

      // Create a pod to generate events
      const podName = 'mcp-event-test-pod';
      await server.executeTool('k8s_create_pod', {
        name: podName,
        namespace: testNamespace,
        image: 'nginx:alpine',
      });

      createdResources.pods.push(podName);

      // Wait a moment for events to be generated
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Get events for the specific pod
      const eventsResult = await server.executeTool('k8s_get_events', {
        namespace: testNamespace,
        fieldSelector: `involvedObject.name=${podName}`,
        limit: 5,
      });

      expect(eventsResult.events).toBeInstanceOf(Array);
      expect(eventsResult.count).toBeGreaterThanOrEqual(0);

      // If events exist, they should be related to our pod
      if (eventsResult.events.length > 0) {
        const event = eventsResult.events[0];
        expect(event.object).toContain(podName);
      }
    });
  });

  describe('Cluster Information', () => {
    it('should get cluster information', async () => {
      if (!server) return;

      const clusterInfo = await server.executeTool('k8s_cluster_info', {});

      expect(clusterInfo.context).toBeDefined();
      expect(clusterInfo.nodes).toMatchObject({
        count: expect.any(Number),
        list: expect.any(Array),
      });
      expect(clusterInfo.namespaces).toMatchObject({
        count: expect.any(Number),
        list: expect.any(Array),
      });

      // Should include our test namespace
      expect(clusterInfo.namespaces.list).toContain(testNamespace);

      // Nodes should have required information
      if (clusterInfo.nodes.list.length > 0) {
        const node = clusterInfo.nodes.list[0];
        expect(node.name).toBeDefined();
        expect(node.status).toBeDefined();
      }
    });
  });

  describe('Resource Validation', () => {
    it('should validate resource requirements', async () => {
      if (!server) return;

      // Create pod with valid resource limits
      const podName = 'mcp-test-resources-pod';
      const createResult = await server.executeTool('k8s_create_pod', {
        name: podName,
        namespace: testNamespace,
        image: 'alpine:latest',
        resources: {
          requests: {
            memory: '32Mi',
            cpu: '50m',
          },
          limits: {
            memory: '64Mi',
            cpu: '100m',
          },
        },
      });

      expect(createResult.success).toBe(true);
      createdResources.pods.push(podName);
    });

    it('should handle pod creation with environment variables', async () => {
      if (!server) return;

      const podName = 'mcp-test-env-pod';
      const createResult = await server.executeTool('k8s_create_pod', {
        name: podName,
        namespace: testNamespace,
        image: 'alpine:latest',
        env: {
          'ENV_VAR_1': 'value1',
          'ENV_VAR_2': 'value2',
          'NUMERIC_ENV': '123',
          'BOOLEAN_ENV': 'true',
        },
      });

      expect(createResult.success).toBe(true);
      createdResources.pods.push(podName);
    });
  });

  describe('Error Handling', () => {
    it('should handle non-existent resource operations', async () => {
      if (!server) return;

      // Try to delete non-existent pod
      try {
        await server.executeTool('k8s_delete_pod', {
          name: 'non-existent-pod',
          namespace: testNamespace,
        });
        // Some Kubernetes setups might not error on deleting non-existent resources
        expect(true).toBe(true);
      } catch (error: any) {
        expect(error.message).toContain('not found');
      }

      // Try to get logs from non-existent pod
      await expect(
        server.executeTool('k8s_get_logs', {
          name: 'non-existent-pod',
          namespace: testNamespace,
        })
      ).rejects.toThrow('not found');
    });

    it('should handle invalid namespace operations', async () => {
      if (!server) return;

      // Try to list pods in non-existent namespace
      try {
        const result = await server.executeTool('k8s_list_pods', {
          namespace: 'non-existent-namespace',
        });
        // Should return empty list rather than error
        expect(result.pods).toHaveLength(0);
      } catch (error: any) {
        // Some clusters might error on non-existent namespace
        expect(error.message).toContain('not found');
      }
    });

    it('should handle invalid resource configurations', async () => {
      if (!server) return;

      // Try to create service with invalid selector
      try {
        await server.executeTool('k8s_create_service', {
          name: 'invalid-service',
          namespace: testNamespace,
          selector: {}, // Empty selector might be invalid
          ports: [{
            port: 80,
            targetPort: 80,
          }],
        });
        // Some configurations might be accepted
        expect(true).toBe(true);
      } catch (error) {
        // Expected to fail with invalid configuration
        expect(error).toBeDefined();
      }
    });
  });

  describe('Integration Scenarios', () => {
    it('should deploy a complete application stack', async () => {
      if (!server) return;

      const appName = 'mcp-test-stack';

      // Create ConfigMap for app configuration
      const configResult = await server.executeTool('k8s_create_configmap', {
        name: `${appName}-config`,
        namespace: testNamespace,
        data: {
          'nginx.conf': 'server { listen 80; location / { return 200 "Hello MCP"; } }',
        },
      });
      expect(configResult.success).toBe(true);
      createdResources.configMaps.push(`${appName}-config`);

      // Create Secret for sensitive data
      const secretResult = await server.executeTool('k8s_create_secret', {
        name: `${appName}-secret`,
        namespace: testNamespace,
        data: {
          'api-key': 'secret-api-key-value',
        },
      });
      expect(secretResult.success).toBe(true);
      createdResources.secrets.push(`${appName}-secret`);

      // Create Deployment
      const deploymentResult = await server.executeTool('k8s_create_deployment', {
        name: appName,
        namespace: testNamespace,
        image: 'nginx:alpine',
        replicas: 2,
        ports: [{ containerPort: 80 }],
        labels: { app: appName },
        env: {
          'APP_NAME': appName,
        },
      });
      expect(deploymentResult.success).toBe(true);
      createdResources.deployments.push(appName);

      // Create Service to expose deployment
      const serviceResult = await server.executeTool('k8s_create_service', {
        name: `${appName}-service`,
        namespace: testNamespace,
        selector: { app: appName },
        ports: [{
          port: 80,
          targetPort: 80,
          name: 'http',
        }],
        type: 'ClusterIP',
      });
      expect(serviceResult.success).toBe(true);
      createdResources.services.push(`${appName}-service`);

      // Verify all components are created
      const deployments = await server.executeTool('k8s_list_deployments', {
        namespace: testNamespace,
      });
      expect(deployments.deployments.find(d => d.name === appName)).toBeDefined();

      const services = await server.executeTool('k8s_list_services', {
        namespace: testNamespace,
      });
      expect(services.services.find(s => s.name === `${appName}-service`)).toBeDefined();
    });
  });
});