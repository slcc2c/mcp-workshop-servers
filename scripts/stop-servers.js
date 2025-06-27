#!/usr/bin/env node

/**
 * Stop all MCP servers
 */

const fs = require('fs');
const path = require('path');

const PID_DIR = path.join(__dirname, '..', 'tmp', 'pids');

async function getPidFiles() {
  try {
    const files = await fs.promises.readdir(PID_DIR);
    return files.filter(file => file.endsWith('.pid'));
  } catch (error) {
    return [];
  }
}

async function stopProcess(pidFile) {
  const pidPath = path.join(PID_DIR, pidFile);
  const serverName = path.basename(pidFile, '.pid');
  
  try {
    const pidContent = await fs.promises.readFile(pidPath, 'utf-8');
    const pid = parseInt(pidContent.trim(), 10);
    
    if (isNaN(pid)) {
      console.log(`⚠️  Invalid PID in ${pidFile}`);
      return;
    }

    console.log(`🛑 Stopping ${serverName} (PID: ${pid})...`);

    // Check if process exists
    try {
      process.kill(pid, 0); // This doesn't actually kill, just checks if process exists
    } catch (error) {
      if (error.code === 'ESRCH') {
        console.log(`   Process ${pid} not found (already stopped)`);
        await fs.promises.unlink(pidPath);
        return;
      }
      throw error;
    }

    // Try graceful shutdown first
    try {
      process.kill(pid, 'SIGTERM');
      
      // Wait for graceful shutdown
      await new Promise((resolve) => {
        const checkInterval = setInterval(() => {
          try {
            process.kill(pid, 0);
          } catch (error) {
            if (error.code === 'ESRCH') {
              clearInterval(checkInterval);
              resolve();
            }
          }
        }, 100);
        
        // Force kill after 10 seconds
        setTimeout(() => {
          clearInterval(checkInterval);
          try {
            process.kill(pid, 'SIGKILL');
            console.log(`   Force killed ${serverName}`);
          } catch (error) {
            // Process might already be dead
          }
          resolve();
        }, 10000);
      });
      
      console.log(`✅ ${serverName} stopped`);
    } catch (error) {
      console.error(`❌ Failed to stop ${serverName}:`, error.message);
    }

    // Clean up PID file
    try {
      await fs.promises.unlink(pidPath);
    } catch (error) {
      // File might already be deleted
    }

  } catch (error) {
    console.error(`❌ Error stopping ${serverName}:`, error.message);
  }
}

async function stopAllServers() {
  console.log('🛑 Stopping all MCP servers...\n');

  const pidFiles = await getPidFiles();
  
  if (pidFiles.length === 0) {
    console.log('ℹ️  No running servers found');
    return;
  }

  console.log(`Found ${pidFiles.length} server(s) to stop:`);
  pidFiles.forEach(file => {
    const serverName = path.basename(file, '.pid');
    console.log(`   • ${serverName}`);
  });
  console.log();

  // Stop all servers
  await Promise.all(pidFiles.map(stopProcess));

  console.log('\n🎉 All servers stopped');
}

async function stopSpecificServer(serverName) {
  const pidFile = `${serverName}.pid`;
  const pidPath = path.join(PID_DIR, pidFile);
  
  try {
    await fs.promises.access(pidPath);
    await stopProcess(pidFile);
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.log(`ℹ️  Server '${serverName}' is not running`);
    } else {
      console.error(`❌ Error stopping ${serverName}:`, error.message);
    }
  }
}

async function main() {
  const serverName = process.argv[2];
  
  if (serverName) {
    await stopSpecificServer(serverName);
  } else {
    await stopAllServers();
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error('❌ Script failed:', error.message);
    process.exit(1);
  });
}