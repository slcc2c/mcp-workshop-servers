#!/usr/bin/env node

/**
 * Docker MCP Server Demo
 * 
 * This example demonstrates:
 * - Container lifecycle management
 * - Image operations and building
 * - Resource limits and monitoring
 * - Volume and network management
 * - Security and isolation features
 */

const http = require('http');
const path = require('path');

async function makeDockerRequest(tool, args = {}) {
  const requestData = JSON.stringify({
    id: `docker-${Date.now()}`,
    method: 'executeTool',
    params: {
      tool,
      arguments: args
    },
    server: 'docker'
  });

  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: '/api/v1/execute',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(requestData)
      }
    }, (res) => {
      let data = '';
      
      res.on('data', chunk => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (response.error) {
            reject(new Error(response.error.message));
          } else {
            resolve(response.result);
          }
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('error', reject);
    req.write(requestData);
    req.end();
  });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  console.log('🐳 Docker MCP Server Demo\n');

  try {
    // Get Docker system information
    console.log('📊 Getting Docker system information...');
    const systemInfo = await makeDockerRequest('docker_system_info');
    console.log('✅ Docker system info:', {
      containers: systemInfo.containers,
      running: systemInfo.containersRunning,
      stopped: systemInfo.containersStopped,
      images: systemInfo.images,
      version: systemInfo.serverVersion,
      architecture: systemInfo.architecture
    });

    // List existing images
    console.log('\n📦 Listing Docker images...');
    const imageList = await makeDockerRequest('docker_list_images', {
      all: false
    });
    console.log(`✅ Found ${imageList.count} images`);
    if (imageList.images.length > 0) {
      imageList.images.slice(0, 3).forEach(image => {
        const tags = image.repoTags && image.repoTags.length > 0 ? image.repoTags[0] : '<none>';
        console.log(`   📦 ${tags} (${Math.round(image.size / 1024 / 1024)} MB)`);
      });
    }

    // Pull a lightweight image for testing
    console.log('\n⬇️  Pulling hello-world image...');
    try {
      const pullResult = await makeDockerRequest('docker_pull_image', {
        image: 'hello-world',
        tag: 'latest'
      });
      console.log(`✅ Image pulled: ${pullResult.image}`);
    } catch (error) {
      console.log('📦 Image already exists or pull failed, continuing...');
    }

    // Create a test volume
    console.log('\n💾 Creating a test volume...');
    const volumeName = `mcp-demo-volume-${Date.now()}`;
    const volumeResult = await makeDockerRequest('docker_create_volume', {
      name: volumeName,
      driver: 'local',
      labels: {
        'demo': 'mcp-workshop',
        'created-by': 'docker-demo'
      }
    });
    console.log(`✅ Volume created: ${volumeResult.name}`);

    // Create a test network
    console.log('\n🌐 Creating a test network...');
    const networkName = `mcp-demo-network-${Date.now()}`;
    const networkResult = await makeDockerRequest('docker_create_network', {
      name: networkName,
      driver: 'bridge',
      labels: {
        'demo': 'mcp-workshop'
      }
    });
    console.log(`✅ Network created: ${networkResult.name} (${networkResult.id.substring(0, 12)})`);

    // Create a container with resource limits
    console.log('\n🚀 Creating container with resource limits...');
    const containerName = `mcp-demo-container-${Date.now()}`;
    const createResult = await makeDockerRequest('docker_create_container', {
      name: containerName,
      image: 'hello-world:latest',
      memory: '128MB',
      cpus: '0.5',
      env: {
        'DEMO': 'true',
        'MCP_SERVER': 'docker'
      },
      labels: {
        'demo': 'mcp-workshop'
      },
      autoRemove: false // Don't auto-remove so we can inspect it
    });
    console.log(`✅ Container created: ${createResult.name} (${createResult.id.substring(0, 12)})`);

    // Start the container
    console.log('\n▶️  Starting container...');
    const startResult = await makeDockerRequest('docker_start_container', {
      containerId: createResult.id
    });
    console.log('✅ Container started successfully');

    // Wait for container to complete
    console.log('\n⏳ Waiting for container to complete...');
    await sleep(3000);

    // Get container logs
    console.log('\n📜 Getting container logs...');
    const logsResult = await makeDockerRequest('docker_container_logs', {
      containerId: createResult.id,
      tail: 50,
      timestamps: true
    });
    console.log('✅ Container logs:');
    console.log(logsResult.logs);

    // Inspect the container
    console.log('\n🔍 Inspecting container...');
    const inspectResult = await makeDockerRequest('docker_inspect_container', {
      containerId: createResult.id
    });
    console.log('✅ Container details:', {
      name: inspectResult.name,
      state: inspectResult.state.status,
      image: inspectResult.image,
      memory: `${Math.round(inspectResult.hostConfig.memory / 1024 / 1024)} MB`,
      cpuQuota: inspectResult.hostConfig.cpuQuota,
      exitCode: inspectResult.state.exitCode
    });

    // Build a custom image
    console.log('\n🔨 Building a custom Docker image...');
    const customImageTag = `mcp-demo-image:${Date.now()}`;
    const dockerfile = `
FROM alpine:latest
LABEL maintainer="MCP Workshop"
LABEL demo="true"

# Install some basic tools
RUN apk add --no-cache curl jq

# Create a simple script
RUN echo '#!/bin/sh' > /usr/local/bin/demo.sh
RUN echo 'echo "Hello from MCP Docker server!"' >> /usr/local/bin/demo.sh
RUN echo 'echo "Image built at: $(date)"' >> /usr/local/bin/demo.sh
RUN echo 'echo "Architecture: $(uname -m)"' >> /usr/local/bin/demo.sh
RUN chmod +x /usr/local/bin/demo.sh

# Set the default command
CMD ["/usr/local/bin/demo.sh"]
`;

    const buildResult = await makeDockerRequest('docker_build_image', {
      tag: customImageTag,
      dockerfile: dockerfile,
      labels: {
        'demo': 'mcp-workshop',
        'built-by': 'docker-demo'
      }
    });
    console.log(`✅ Custom image built: ${buildResult.tag}`);

    // Create and run a container from our custom image
    console.log('\n🚀 Running custom image...');
    const customContainerName = `mcp-custom-${Date.now()}`;
    const customCreateResult = await makeDockerRequest('docker_create_container', {
      name: customContainerName,
      image: customImageTag,
      memory: '256MB',
      cpus: '0.5',
      volumes: {
        [volumeName]: '/data'
      },
      autoRemove: false
    });

    await makeDockerRequest('docker_start_container', {
      containerId: customCreateResult.id
    });

    // Wait and get logs
    await sleep(3000);
    const customLogsResult = await makeDockerRequest('docker_container_logs', {
      containerId: customCreateResult.id,
      tail: 20
    });
    console.log('✅ Custom container output:');
    console.log(customLogsResult.logs);

    // Execute a command in the running container (create a long-running one first)
    console.log('\n⚙️  Creating long-running container for exec demo...');
    const execDemoContainer = await makeDockerRequest('docker_create_container', {
      name: `mcp-exec-demo-${Date.now()}`,
      image: 'alpine:latest',
      command: ['sleep', '30'],
      memory: '128MB'
    });

    await makeDockerRequest('docker_start_container', {
      containerId: execDemoContainer.id
    });

    console.log('\n💻 Executing command in running container...');
    const execResult = await makeDockerRequest('docker_exec', {
      containerId: execDemoContainer.id,
      command: ['sh', '-c', 'echo "Executing from MCP!" && ls -la / | head -5'],
      detach: false
    });
    console.log('✅ Command execution result:');
    console.log(execResult.output);

    // List all containers
    console.log('\n📋 Listing all containers...');
    const containerList = await makeDockerRequest('docker_list_containers', {
      all: true,
      filters: {}
    });
    console.log(`✅ Found ${containerList.count} containers`);
    
    const demoContainers = containerList.containers.filter(c => 
      c.names.some(name => name.includes('mcp-demo') || name.includes('mcp-custom') || name.includes('mcp-exec'))
    );
    
    console.log('Demo containers:');
    demoContainers.forEach(container => {
      console.log(`   🐳 ${container.names[0]} - ${container.state} (${container.image})`);
    });

    // List volumes and networks
    console.log('\n💾 Listing volumes...');
    const volumeList = await makeDockerRequest('docker_list_volumes');
    const demoVolumes = volumeList.volumes.filter(v => v.Labels && v.Labels.demo === 'mcp-workshop');
    console.log(`✅ Demo volumes: ${demoVolumes.length}`);
    demoVolumes.forEach(volume => {
      console.log(`   💾 ${volume.Name} (${volume.Driver})`);
    });

    console.log('\n🌐 Listing networks...');
    const networkList = await makeDockerRequest('docker_list_networks');
    const demoNetworks = networkList.networks.filter(n => n.labels && n.labels.demo === 'mcp-workshop');
    console.log(`✅ Demo networks: ${demoNetworks.length}`);
    demoNetworks.forEach(network => {
      console.log(`   🌐 ${network.name} (${network.driver})`);
    });

    // Check operation tracking
    console.log('\n📈 Checking operation tracking...');
    const trackingResult = await makeDockerRequest('getOperationHistory');
    console.log('✅ Operation tracking:', {
      enabled: trackingResult.trackingEnabled,
      defaultLimits: trackingResult.defaultLimits,
      allowedImages: trackingResult.allowedImages.slice(0, 3)
    });

    // Clean up demo resources
    console.log('\n🧹 Cleaning up demo resources...');
    
    // Stop and remove containers
    const containersToClean = [createResult.id, customCreateResult.id, execDemoContainer.id];
    for (const containerId of containersToClean) {
      try {
        await makeDockerRequest('docker_stop_container', {
          containerId,
          timeout: 5
        });
        console.log(`✅ Stopped container: ${containerId.substring(0, 12)}`);
      } catch (error) {
        // Container might already be stopped
      }

      try {
        await makeDockerRequest('docker_remove_container', {
          containerId,
          force: true,
          volumes: true
        });
        console.log(`✅ Removed container: ${containerId.substring(0, 12)}`);
      } catch (error) {
        console.log(`⚠️  Could not remove container: ${error.message}`);
      }
    }

    // Remove custom image
    try {
      await makeDockerRequest('docker_remove_image', {
        imageId: customImageTag,
        force: true
      });
      console.log(`✅ Removed image: ${customImageTag}`);
    } catch (error) {
      console.log(`⚠️  Could not remove image: ${error.message}`);
    }

    // Remove volume
    try {
      await makeDockerRequest('docker_remove_volume', {
        volumeName,
        force: true
      });
      console.log(`✅ Removed volume: ${volumeName}`);
    } catch (error) {
      console.log(`⚠️  Could not remove volume: ${error.message}`);
    }

    // Remove network
    try {
      await makeDockerRequest('docker_remove_network', {
        networkId: networkResult.id
      });
      console.log(`✅ Removed network: ${networkName}`);
    } catch (error) {
      console.log(`⚠️  Could not remove network: ${error.message}`);
    }

    console.log('\n🎉 Docker demo completed successfully!');
    console.log('\n💡 Key capabilities demonstrated:');
    console.log('   • Complete container lifecycle management');
    console.log('   • Resource limits and isolation (memory, CPU)');
    console.log('   • Custom image building from Dockerfile');
    console.log('   • Volume and network management');
    console.log('   • Command execution in running containers');
    console.log('   • Security controls and image validation');
    console.log('   • Operation tracking and monitoring');
    console.log('   • Comprehensive cleanup and resource management');

  } catch (error) {
    console.error('❌ Error:', error.message);
    
    if (error.message.includes('Docker daemon not available')) {
      console.log('\n💡 Docker Setup Required:');
      console.log('   1. Install Docker Desktop for Mac');
      console.log('   2. Start Docker Desktop');
      console.log('   3. Ensure Docker daemon is running');
      console.log('   4. Test with: docker --version');
    } else if (error.message.includes('not in the allowed list')) {
      console.log('\n💡 Security Feature Working:');
      console.log('   The Docker server enforces image allowlists');
      console.log('   Only approved images can be used for security');
    } else {
      console.log('\n💡 Make sure the MCP servers are running:');
      console.log('   npm run mcp:start');
    }
    
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}