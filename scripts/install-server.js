#!/usr/bin/env node

/**
 * Install a specific MCP server
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const KNOWN_SERVERS = {
  'github': {
    package: '@modelcontextprotocol/server-github',
    description: 'GitHub repository management',
    env: ['GITHUB_PERSONAL_ACCESS_TOKEN']
  },
  'filesystem': {
    package: '@modelcontextprotocol/server-filesystem',
    description: 'File system operations',
    args: ['<directory-path>']
  },
  'postgres': {
    package: '@modelcontextprotocol/server-postgres',
    description: 'PostgreSQL database operations',
    env: ['POSTGRES_URL']
  },
  'sqlite': {
    package: '@modelcontextprotocol/server-sqlite',
    description: 'SQLite database operations',
    args: ['<database-path>']
  },
  'brave-search': {
    package: '@modelcontextprotocol/server-brave-search',
    description: 'Brave search integration',
    env: ['BRAVE_API_KEY']
  },
  'puppeteer': {
    package: '@modelcontextprotocol/server-puppeteer',
    description: 'Web automation and scraping'
  },
  'slack': {
    package: '@modelcontextprotocol/server-slack',
    description: 'Slack integration',
    env: ['SLACK_BOT_TOKEN']
  }
};

function showAvailableServers() {
  console.log('📦 Available MCP Servers:\n');
  
  Object.entries(KNOWN_SERVERS).forEach(([name, info]) => {
    console.log(`🔹 ${name}`);
    console.log(`   Description: ${info.description}`);
    console.log(`   Package: ${info.package}`);
    
    if (info.env) {
      console.log(`   Required env vars: ${info.env.join(', ')}`);
    }
    
    if (info.args) {
      console.log(`   Required args: ${info.args.join(', ')}`);
    }
    
    console.log();
  });
}

async function installServer(serverName, options = {}) {
  const serverInfo = KNOWN_SERVERS[serverName];
  
  if (!serverInfo) {
    console.error(`❌ Unknown server: ${serverName}`);
    console.log('\n💡 Available servers:');
    Object.keys(KNOWN_SERVERS).forEach(name => {
      console.log(`   • ${name}`);
    });
    return false;
  }

  console.log(`📦 Installing ${serverName} server...`);
  console.log(`   Package: ${serverInfo.package}`);
  console.log(`   Description: ${serverInfo.description}\n`);

  // Install the package
  if (!options.skipInstall) {
    console.log('⬇️  Installing npm package...');
    
    try {
      await new Promise((resolve, reject) => {
        const npm = spawn('npm', ['install', '-g', serverInfo.package], {
          stdio: 'inherit'
        });
        
        npm.on('close', (code) => {
          if (code === 0) {
            resolve();
          } else {
            reject(new Error(`npm install failed with code ${code}`));
          }
        });
        
        npm.on('error', reject);
      });
      
      console.log('✅ Package installed successfully');
    } catch (error) {
      console.error('❌ Failed to install package:', error.message);
      return false;
    }
  }

  // Update server configuration
  const configPath = path.join(__dirname, '..', 'config', 'servers.json');
  
  try {
    let config = {};
    
    // Load existing config
    try {
      const configData = await fs.promises.readFile(configPath, 'utf-8');
      config = JSON.parse(configData);
    } catch (error) {
      // Config file doesn't exist yet
    }

    // Add server configuration
    config[serverName] = {
      enabled: true,
      command: 'npx',
      args: ['-y', serverInfo.package],
      external: true,
      description: serverInfo.description
    };

    // Add environment variables if needed
    if (serverInfo.env) {
      config[serverName].env = {};
      serverInfo.env.forEach(envVar => {
        config[serverName].env[envVar] = `\${${envVar}}`;
      });
    }

    // Ensure config directory exists
    await fs.promises.mkdir(path.dirname(configPath), { recursive: true });
    
    // Save updated config
    await fs.promises.writeFile(configPath, JSON.stringify(config, null, 2));
    
    console.log('✅ Server configuration updated');
  } catch (error) {
    console.error('❌ Failed to update configuration:', error.message);
    return false;
  }

  // Show next steps
  console.log('\n🎉 Installation complete!');
  console.log('\n📝 Next steps:');
  
  if (serverInfo.env) {
    console.log('1. Set required environment variables:');
    serverInfo.env.forEach(envVar => {
      console.log(`   export ${envVar}="your-value-here"`);
    });
  }
  
  if (serverInfo.args) {
    console.log('2. Update server configuration with required arguments');
    console.log(`   Edit: ${configPath}`);
    console.log(`   Add args: ${JSON.stringify(serverInfo.args)}`);
  }
  
  console.log('3. Start the server:');
  console.log('   npm run mcp:start');
  
  return true;
}

async function uninstallServer(serverName) {
  const serverInfo = KNOWN_SERVERS[serverName];
  
  if (!serverInfo) {
    console.error(`❌ Unknown server: ${serverName}`);
    return false;
  }

  console.log(`🗑️  Uninstalling ${serverName} server...`);

  // Remove from configuration
  const configPath = path.join(__dirname, '..', 'config', 'servers.json');
  
  try {
    const configData = await fs.promises.readFile(configPath, 'utf-8');
    const config = JSON.parse(configData);
    
    if (config[serverName]) {
      delete config[serverName];
      await fs.promises.writeFile(configPath, JSON.stringify(config, null, 2));
      console.log('✅ Removed from configuration');
    }
  } catch (error) {
    console.log('⚠️  No configuration to update');
  }

  // Uninstall npm package
  try {
    await new Promise((resolve, reject) => {
      const npm = spawn('npm', ['uninstall', '-g', serverInfo.package], {
        stdio: 'inherit'
      });
      
      npm.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`npm uninstall failed with code ${code}`));
        }
      });
      
      npm.on('error', reject);
    });
    
    console.log('✅ Package uninstalled');
  } catch (error) {
    console.error('❌ Failed to uninstall package:', error.message);
  }

  console.log('🎉 Uninstallation complete!');
  return true;
}

async function main() {
  const args = process.argv.slice(2);
  
  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    console.log('🔧 MCP Server Installer\n');
    console.log('Usage:');
    console.log('  npm run mcp:install <server-name>    Install a server');
    console.log('  npm run mcp:install --list           List available servers');
    console.log('  npm run mcp:install --uninstall <name>  Uninstall a server');
    console.log();
    showAvailableServers();
    return;
  }

  if (args[0] === '--list' || args[0] === '-l') {
    showAvailableServers();
    return;
  }

  if (args[0] === '--uninstall' || args[0] === '-u') {
    if (args.length < 2) {
      console.error('❌ Please specify a server name to uninstall');
      return;
    }
    
    await uninstallServer(args[1]);
    return;
  }

  const serverName = args[0];
  const options = {
    skipInstall: args.includes('--skip-install')
  };

  const success = await installServer(serverName, options);
  
  if (!success) {
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error('❌ Installation failed:', error.message);
    process.exit(1);
  });
}