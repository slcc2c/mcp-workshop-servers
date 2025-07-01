#!/usr/bin/env node

/**
 * Test MCP client connections
 */

import axios from 'axios';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const GATEWAY_URL = 'http://localhost:3000';

// Client configurations
const clients = {
  claude: {
    name: 'Claude Desktop',
    token: process.env.MCP_CLAUDE_AUTH_TOKEN,
    testStdio: true,
  },
  cursor: {
    name: 'Cursor IDE',
    token: process.env.MCP_CURSOR_AUTH_TOKEN,
    testHttp: true,
  },
  openai: {
    name: 'OpenAI',
    token: process.env.MCP_OPENAI_AUTH_TOKEN,
    testHttp: true,
    restrictedServers: ['github', 'filesystem', 'memory'],
  },
  default: {
    name: 'Default Client',
    token: process.env.MCP_DEFAULT_AUTH_TOKEN,
    testHttp: true,
  },
};

// Test HTTP connection
async function testHttpConnection(clientId, config) {
  console.log(`\n🔍 Testing HTTP connection for ${config.name}...`);
  
  if (!config.token) {
    console.error(`❌ No token found for ${clientId}. Set ${`MCP_${clientId.toUpperCase()}_AUTH_TOKEN`}`);
    return false;
  }

  try {
    // Test health endpoint
    const healthResponse = await axios.get(`${GATEWAY_URL}/health`, {
      headers: {
        'Authorization': `Bearer ${config.token}`,
      },
    });
    console.log(`✅ Health check passed`);

    // Test server list
    const serversResponse = await axios.get(`${GATEWAY_URL}/api/v1/servers`, {
      headers: {
        'Authorization': `Bearer ${config.token}`,
      },
    });
    console.log(`✅ Retrieved ${serversResponse.data.servers.length} servers`);

    // Test tool execution
    const testServer = config.restrictedServers ? config.restrictedServers[0] : 'github';
    console.log(`📋 Testing tool execution on ${testServer} server...`);
    
    const toolsResponse = await axios.post(
      `${GATEWAY_URL}/api/v1/servers/${testServer}/execute`,
      {
        id: `test-${Date.now()}`,
        method: 'tools/list',
        params: {},
      },
      {
        headers: {
          'Authorization': `Bearer ${config.token}`,
        },
      }
    );

    if (toolsResponse.data.result?.tools) {
      console.log(`✅ Retrieved ${toolsResponse.data.result.tools.length} tools from ${testServer}`);
    } else {
      console.log(`⚠️  No tools returned from ${testServer}`);
    }

    // Test restricted server access if applicable
    if (config.restrictedServers) {
      try {
        await axios.post(
          `${GATEWAY_URL}/api/v1/servers/docker/execute`,
          {
            id: `test-restricted-${Date.now()}`,
            method: 'tools/list',
            params: {},
          },
          {
            headers: {
              'Authorization': `Bearer ${config.token}`,
            },
          }
        );
        console.log(`⚠️  Unexpectedly allowed access to restricted server`);
      } catch (error) {
        if (error.response?.status === 401) {
          console.log(`✅ Correctly denied access to restricted server`);
        } else {
          throw error;
        }
      }
    }

    console.log(`✅ ${config.name} HTTP connection test passed`);
    return true;
  } catch (error) {
    console.error(`❌ ${config.name} HTTP connection test failed:`);
    if (error.response) {
      console.error(`   Status: ${error.response.status}`);
      console.error(`   Message: ${error.response.data?.error?.message || error.message}`);
    } else {
      console.error(`   Error: ${error.message}`);
    }
    return false;
  }
}

// Test stdio connection
async function testStdioConnection(clientId, config) {
  console.log(`\n🔍 Testing stdio connection for ${config.name}...`);
  
  if (!config.token) {
    console.error(`❌ No token found for ${clientId}. Set ${`MCP_${clientId.toUpperCase()}_AUTH_TOKEN`}`);
    return false;
  }

  return new Promise((resolve) => {
    const adapterPath = path.join(__dirname, '..', 'dist', 'gateway', 'stdio-adapter.js');
    
    // Spawn stdio adapter
    const child = spawn('node', [adapterPath], {
      env: {
        ...process.env,
        MCP_GATEWAY_URL: GATEWAY_URL,
        MCP_AUTH_TOKEN: config.token,
      },
    });

    let output = '';
    let errorOutput = '';
    const timeout = setTimeout(() => {
      child.kill();
      console.error(`❌ Stdio adapter timeout`);
      resolve(false);
    }, 10000);

    child.stderr.on('data', (data) => {
      errorOutput += data.toString();
      
      if (data.toString().includes('STDIO adapter ready')) {
        clearTimeout(timeout);
        console.log(`✅ Stdio adapter started successfully`);
        
        // Send test request
        const testRequest = {
          jsonrpc: '2.0',
          id: 1,
          method: 'tools/list',
          params: {},
        };
        
        child.stdin.write(JSON.stringify(testRequest) + '\n');
      }
    });

    child.stdout.on('data', (data) => {
      output += data.toString();
      
      try {
        const response = JSON.parse(data.toString());
        if (response.id === 1 && response.result) {
          console.log(`✅ Received valid response from stdio adapter`);
          console.log(`✅ ${config.name} stdio connection test passed`);
          child.kill();
          clearTimeout(timeout);
          resolve(true);
        }
      } catch (e) {
        // Not JSON, continue collecting
      }
    });

    child.on('exit', (code) => {
      clearTimeout(timeout);
      if (code !== 0 && code !== null) {
        console.error(`❌ Stdio adapter exited with code ${code}`);
        if (errorOutput) {
          console.error(`   Error output: ${errorOutput}`);
        }
        resolve(false);
      }
    });
  });
}

// Main test function
async function testClient(clientId) {
  const config = clients[clientId];
  
  if (!config) {
    console.error(`Unknown client: ${clientId}`);
    console.log(`Available clients: ${Object.keys(clients).join(', ')}`);
    return;
  }

  console.log(`\n🧪 Testing ${config.name} Connection`);
  console.log('='.repeat(50));

  let passed = true;

  if (config.testHttp) {
    const httpPassed = await testHttpConnection(clientId, config);
    passed = passed && httpPassed;
  }

  if (config.testStdio) {
    const stdioPassed = await testStdioConnection(clientId, config);
    passed = passed && stdioPassed;
  }

  console.log('\n' + '='.repeat(50));
  if (passed) {
    console.log(`✅ All ${config.name} tests passed`);
  } else {
    console.log(`❌ Some ${config.name} tests failed`);
  }
}

// Test all clients
async function testAll() {
  console.log('🧪 Testing All MCP Client Connections');
  
  // First check if gateway is running
  try {
    await axios.get(`${GATEWAY_URL}/health`);
    console.log('✅ Gateway is running');
  } catch (error) {
    console.error('❌ Gateway is not running. Start it with: npm run mcp:start');
    process.exit(1);
  }

  for (const clientId of Object.keys(clients)) {
    await testClient(clientId);
  }
}

// Main
const clientArg = process.argv[2];

if (clientArg === 'all' || !clientArg) {
  testAll().catch(console.error);
} else {
  testClient(clientArg).catch(console.error);
}