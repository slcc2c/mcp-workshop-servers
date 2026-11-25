#!/usr/bin/env node

// Test if the MCP server starts correctly
import { spawn } from 'child_process';

console.error('Starting Docker MCP server test...');

const server = spawn('node', ['/Users/spencer/repos/mcp-server/dist/servers/docker/index.js'], {
  stdio: 'pipe',
  env: {
    ...process.env,
    DOCKER_HOST: 'unix:///var/run/docker.sock'
  }
});

server.stdout.on('data', (data) => {
  console.log('STDOUT:', data.toString());
});

server.stderr.on('data', (data) => {
  console.error('STDERR:', data.toString());
});

server.on('close', (code) => {
  console.error('Server exited with code:', code);
});

// Send initialize request
const initRequest = {
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: {
      tools: {}
    },
    clientInfo: {
      name: 'test-client',
      version: '1.0.0'
    }
  }
};

setTimeout(() => {
  console.error('Sending initialize request...');
  server.stdin.write(JSON.stringify(initRequest) + '\n');
}, 1000);

// Keep process alive
setTimeout(() => {
  console.error('Test complete');
  process.exit(0);
}, 5000);