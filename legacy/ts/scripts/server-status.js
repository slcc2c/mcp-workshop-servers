#!/usr/bin/env node

/**
 * Check status of all MCP servers
 */

import fs from 'fs';
import path from 'path';
import http from 'http';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PID_DIR = path.join(__dirname, '..', 'tmp', 'pids');
const GATEWAY_CONFIG_FILE = path.join(__dirname, '..', 'config', 'gateway.json');

async function loadGatewayPort() {
  try {
    const configData = await fs.promises.readFile(GATEWAY_CONFIG_FILE, 'utf-8');
    const config = JSON.parse(configData);
    const port = Number(config?.gateway?.port);
    return Number.isInteger(port) && port > 0 ? port : 3000;
  } catch {
    return 3000;
  }
}

async function getPidFiles() {
  try {
    const files = await fs.promises.readdir(PID_DIR);
    return files.filter(file => file.endsWith('.pid'));
  } catch (error) {
    return [];
  }
}

async function checkProcess(pidFile) {
  const pidPath = path.join(PID_DIR, pidFile);
  const serverName = path.basename(pidFile, '.pid');
  
  try {
    const pidContent = await fs.promises.readFile(pidPath, 'utf-8');
    const pid = parseInt(pidContent.trim(), 10);
    
    if (isNaN(pid)) {
      return {
        name: serverName,
        status: 'error',
        pid: null,
        error: 'Invalid PID file'
      };
    }

    // Check if process exists
    try {
      process.kill(pid, 0);
      
      return {
        name: serverName,
        status: 'running',
        pid: pid,
        uptime: await getProcessUptime(pid)
      };
    } catch (error) {
      if (error.code === 'ESRCH') {
        // Process not found, clean up PID file
        try {
          await fs.promises.unlink(pidPath);
        } catch (unlinkError) {
          // Ignore cleanup errors
        }
        
        return {
          name: serverName,
          status: 'stopped',
          pid: null,
          error: 'Process not found'
        };
      }
      throw error;
    }
  } catch (error) {
    return {
      name: serverName,
      status: 'error',
      pid: null,
      error: error.message
    };
  }
}

async function getProcessUptime(pid) {
  try {
    const { execSync } = require('child_process');
    
    // Get process start time on macOS
    const output = execSync(`ps -o lstart= -p ${pid}`, { encoding: 'utf-8' });
    const startTime = new Date(output.trim());
    const now = new Date();
    const uptimeMs = now - startTime;
    
    const seconds = Math.floor(uptimeMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  } catch (error) {
    return 'unknown';
  }
}

async function checkGatewayHealth() {
  try {
    const port = await loadGatewayPort();
    return new Promise((resolve) => {
      const req = http.get(`http://localhost:${port}/health`, { timeout: 2000 }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const health = JSON.parse(data);
            resolve({
              healthy: res.statusCode === 200,
              data: health,
              port
            });
          } catch (error) {
            resolve({ healthy: false, error: 'Invalid response', port });
          }
        });
      });
      
      req.on('error', () => {
        resolve({ healthy: false, error: 'Connection failed', port });
      });
      
      req.on('timeout', () => {
        req.destroy();
        resolve({ healthy: false, error: 'Timeout', port });
      });
    });
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

function formatStatus(servers) {
  console.log('📊 MCP Server Status Report\n');
  console.log('═'.repeat(60));
  
  const runningCount = servers.filter(s => s.status === 'running').length;
  const totalCount = servers.length;
  
  console.log(`Status: ${runningCount}/${totalCount} servers running\n`);
  
  servers.forEach(server => {
    const statusIcon = {
      running: '🟢',
      stopped: '🔴',
      error: '🟡'
    }[server.status] || '❓';
    
    console.log(`${statusIcon} ${server.name.padEnd(15)} ${server.status.toUpperCase()}`);
    
    if (server.pid) {
      console.log(`   PID: ${server.pid}`);
    }
    
    if (server.uptime) {
      console.log(`   Uptime: ${server.uptime}`);
    }
    
    if (server.error) {
      console.log(`   Error: ${server.error}`);
    }
    
    console.log();
  });
}

async function showDetailedStatus() {
  console.log('🔍 Detailed Server Information\n');
  
  // Check gateway health
  console.log('Gateway Health Check:');
  const gatewayHealth = await checkGatewayHealth();
  
  if (gatewayHealth.healthy) {
    console.log('✅ Gateway is healthy');
    console.log(`   URL: http://localhost:${gatewayHealth.port}/health`);
    if (gatewayHealth.data) {
      console.log(`   Timestamp: ${gatewayHealth.data.timestamp}`);
      if (gatewayHealth.data.servers) {
        console.log(`   Managed servers: ${gatewayHealth.data.servers.length}`);
      }
    }
  } else {
    console.log(`❌ Gateway health check failed: ${gatewayHealth.error}`);
    if (gatewayHealth.port) {
      console.log(`   URL: http://localhost:${gatewayHealth.port}/health`);
    }
  }
  
  console.log();
  
  // Show log file locations
  console.log('📝 Log Files:');
  const logsDir = path.join(__dirname, '..', 'logs');
  
  try {
    const logFiles = await fs.promises.readdir(logsDir);
    logFiles.forEach(file => {
      const logPath = path.join(logsDir, file);
      console.log(`   ${file}: ${logPath}`);
    });
  } catch (error) {
    console.log('   No log files found');
  }
  
  console.log();
  
  // Show data directory info
  console.log('💾 Data Directory:');
  const dataDir = path.join(__dirname, '..', 'data');
  
  try {
    const dataFiles = await fs.promises.readdir(dataDir);
    dataFiles.forEach(file => {
      const dataPath = path.join(dataDir, file);
      console.log(`   ${file}: ${dataPath}`);
    });
  } catch (error) {
    console.log('   No data files found');
  }
}

async function main() {
  const showDetailed = process.argv.includes('--detailed') || process.argv.includes('-d');
  
  const pidFiles = await getPidFiles();
  
  if (pidFiles.length === 0) {
    console.log('ℹ️  No servers currently registered');
    console.log('💡 Use "npm run mcp:start" to start servers');
    return;
  }

  // Check all server processes
  const servers = await Promise.all(pidFiles.map(checkProcess));
  
  formatStatus(servers);
  
  if (showDetailed) {
    await showDetailedStatus();
  }
  
  // Show helpful commands
  console.log('═'.repeat(60));
  console.log('💡 Available commands:');
  console.log('   npm run mcp:start     - Start all servers');
  console.log('   npm run mcp:stop      - Stop all servers');
  console.log('   npm run mcp:status -d - Show detailed status');
  console.log('   npm run mcp:logs      - View server logs');
}

// Run if this is the main module
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => {
    console.error('❌ Status check failed:', error.message);
    process.exit(1);
  });
}
