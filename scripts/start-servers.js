#!/usr/bin/env node

/**
 * Start all MCP servers
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CONFIG_FILE = path.join(__dirname, '..', 'config', 'servers.json');
const PID_DIR = path.join(__dirname, '..', 'tmp', 'pids');

// Default server configurations
const DEFAULT_SERVERS = {
  gateway: {
    enabled: true,
    command: 'npm',
    args: ['run', 'dev'],
    cwd: path.join(__dirname, '..'),
    env: {},
    port: 3000
  },
  github: {
    enabled: true,
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-github'],
    env: {
      GITHUB_PERSONAL_ACCESS_TOKEN: process.env.GITHUB_TOKEN
    },
    external: true
  },
  filesystem: {
    enabled: true,
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-filesystem', process.cwd()],
    external: true
  }
};

async function ensureDirectories() {
  try {
    await fs.promises.mkdir(PID_DIR, { recursive: true });
    await fs.promises.mkdir(path.join(__dirname, '..', 'logs'), { recursive: true });
  } catch (error) {
    // Directories might already exist
  }
}

async function loadConfig() {
  try {
    const configData = await fs.promises.readFile(CONFIG_FILE, 'utf-8');
    return JSON.parse(configData);
  } catch (error) {
    console.log('Using default server configuration');
    return DEFAULT_SERVERS;
  }
}

async function startServer(name, config) {
  if (!config.enabled) {
    console.log(`⏭️  Skipping ${name} (disabled)`);
    return null;
  }

  console.log(`🚀 Starting ${name} server...`);

  const env = {
    ...process.env,
    ...config.env,
    MCP_SERVER_NAME: name
  };

  const options = {
    env,
    cwd: config.cwd || process.cwd(),
    stdio: ['ignore', 'pipe', 'pipe']
  };

  const child = spawn(config.command, config.args || [], options);

  // Create log files
  const logFile = path.join(__dirname, '..', 'logs', `${name}.log`);
  const errorFile = path.join(__dirname, '..', 'logs', `${name}.error.log`);
  
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });
  const errorStream = fs.createWriteStream(errorFile, { flags: 'a' });

  // Pipe output to log files
  child.stdout.pipe(logStream);
  child.stderr.pipe(errorStream);

  // Also log to console in development
  if (process.env.NODE_ENV === 'development') {
    child.stdout.on('data', (data) => {
      console.log(`[${name}] ${data}`);
    });
  }

  child.stderr.on('data', (data) => {
    console.error(`[${name}] ERROR: ${data}`);
  });

  // Save PID
  const pidFile = path.join(PID_DIR, `${name}.pid`);
  await fs.promises.writeFile(pidFile, child.pid.toString());

  // Handle process events
  child.on('error', (error) => {
    console.error(`❌ Failed to start ${name}:`, error.message);
  });

  child.on('exit', (code, signal) => {
    console.log(`🛑 ${name} exited with code ${code} (signal: ${signal})`);
    
    // Clean up PID file
    fs.promises.unlink(pidFile).catch(() => {});
  });

  // Wait a moment to see if it starts successfully
  await new Promise(resolve => setTimeout(resolve, 2000));

  if (child.killed) {
    throw new Error(`Server ${name} failed to start`);
  }

  console.log(`✅ ${name} started (PID: ${child.pid})`);
  
  if (config.port) {
    console.log(`   Available at: http://localhost:${config.port}`);
  }

  return child;
}

async function checkHealth(config) {
  // Simple health check for gateway
  if (config.gateway && config.gateway.enabled) {
    try {
      const http = require('http');
      const port = config.gateway.port || 3000;
      
      await new Promise((resolve, reject) => {
        const req = http.get(`http://localhost:${port}/health`, (res) => {
          if (res.statusCode === 200) {
            console.log('✅ Gateway health check passed');
            resolve();
          } else {
            reject(new Error(`Health check failed: ${res.statusCode}`));
          }
        });
        
        req.on('error', reject);
        req.setTimeout(5000, () => reject(new Error('Health check timeout')));
      });
    } catch (error) {
      console.log('⚠️  Gateway health check failed:', error.message);
    }
  }
}

async function main() {
  console.log('🎯 Starting MCP Workshop Servers...\n');

  try {
    await ensureDirectories();
    const config = await loadConfig();
    
    const servers = [];
    
    for (const [name, serverConfig] of Object.entries(config)) {
      try {
        const server = await startServer(name, serverConfig);
        if (server) {
          servers.push({ name, process: server });
        }
      } catch (error) {
        console.error(`❌ Failed to start ${name}:`, error.message);
      }
    }

    if (servers.length === 0) {
      console.log('❌ No servers were started');
      process.exit(1);
    }

    console.log(`\n🎉 Started ${servers.length} server(s):`);
    servers.forEach(({ name }) => console.log(`   • ${name}`));

    // Wait a bit then run health checks
    setTimeout(() => checkHealth(config), 5000);

    console.log('\n📝 Log files location: ./logs/');
    console.log('🛑 Use "npm run mcp:stop" to stop all servers');
    console.log('📊 Use "npm run mcp:status" to check server status');

    // Keep the script running
    process.on('SIGINT', () => {
      console.log('\n🛑 Stopping all servers...');
      servers.forEach(({ process }) => {
        if (process && !process.killed) {
          process.kill('SIGTERM');
        }
      });
      process.exit(0);
    });

  } catch (error) {
    console.error('❌ Failed to start servers:', error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}