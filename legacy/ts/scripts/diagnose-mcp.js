#!/usr/bin/env node

import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Colors for terminal output
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m'
};

const log = {
  info: (msg) => console.log(`${colors.blue}[INFO]${colors.reset} ${msg}`),
  success: (msg) => console.log(`${colors.green}[✓]${colors.reset} ${msg}`),
  warning: (msg) => console.log(`${colors.yellow}[⚠]${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}[✗]${colors.reset} ${msg}`),
  section: (msg) => console.log(`\n${colors.blue}=== ${msg} ===${colors.reset}\n`)
};

async function checkFile(filePath, description) {
  try {
    const stats = await fs.promises.stat(filePath);
    if (stats.isFile()) {
      log.success(`${description}: ${filePath}`);
      return true;
    } else {
      log.error(`${description} exists but is not a file: ${filePath}`);
      return false;
    }
  } catch (error) {
    log.error(`${description} not found: ${filePath}`);
    return false;
  }
}

async function checkDirectory(dirPath, description) {
  try {
    const stats = await fs.promises.stat(dirPath);
    if (stats.isDirectory()) {
      log.success(`${description}: ${dirPath}`);
      return true;
    } else {
      log.error(`${description} exists but is not a directory: ${dirPath}`);
      return false;
    }
  } catch (error) {
    log.error(`${description} not found: ${dirPath}`);
    return false;
  }
}

async function checkEnvironmentVariables() {
  log.section('Checking Environment Variables');
  
  const requiredVars = [
    'GITHUB_PERSONAL_ACCESS_TOKEN',
    'MCP_GITHUB_TOKEN'
  ];
  
  const optionalVars = [
    'MCP_CURSOR_AUTH_TOKEN',
    'NODE_ENV',
    'PATH'
  ];
  
  let allRequired = true;
  
  // Check required variables
  for (const varName of requiredVars) {
    if (process.env[varName]) {
      log.success(`${varName} is set (length: ${process.env[varName].length})`);
    } else {
      log.error(`${varName} is NOT set - This is required!`);
      allRequired = false;
    }
  }
  
  // Check optional variables
  for (const varName of optionalVars) {
    if (process.env[varName]) {
      log.info(`${varName} is set`);
    } else {
      log.warning(`${varName} is not set (optional)`);
    }
  }
  
  return allRequired;
}

async function loadClaudeConfig() {
  log.section('Loading Claude Desktop Configuration');
  
  const configPath = path.join(__dirname, '..', 'claude-desktop-config.json');
  
  if (!await checkFile(configPath, 'Config file')) {
    return null;
  }
  
  try {
    const content = await fs.promises.readFile(configPath, 'utf8');
    const config = JSON.parse(content);
    log.success('Successfully parsed claude-desktop-config.json');
    return config;
  } catch (error) {
    log.error(`Failed to parse config file: ${error.message}`);
    return null;
  }
}

async function checkMCPServers(config) {
  log.section('Checking MCP Server Configurations');
  
  if (!config || !config.mcpServers) {
    log.error('No mcpServers section found in configuration');
    return;
  }
  
  const projectRoot = path.join(__dirname, '..');
  
  for (const [serverName, serverConfig] of Object.entries(config.mcpServers)) {
    log.info(`\nChecking server: ${serverName}`);
    
    // Check command
    if (!serverConfig.command) {
      log.error(`  No command specified for ${serverName}`);
      continue;
    }
    
    log.info(`  Command: ${serverConfig.command}`);
    
    // Check args
    if (!serverConfig.args || !Array.isArray(serverConfig.args)) {
      log.error(`  No args or invalid args for ${serverName}`);
      continue;
    }
    
    // For node servers, check the script path
    if (serverConfig.command === 'node' && serverConfig.args.length > 0) {
      const scriptPath = serverConfig.args[0];
      const fullScriptPath = path.isAbsolute(scriptPath) 
        ? scriptPath 
        : path.join(projectRoot, scriptPath);
      
      await checkFile(fullScriptPath, '  Script file');
      
      // Check if the script directory has package.json
      const scriptDir = path.dirname(fullScriptPath);
      const packageJsonPath = path.join(scriptDir, 'package.json');
      
      if (await checkFile(packageJsonPath, '  Package.json')) {
        // Check if node_modules exists
        const nodeModulesPath = path.join(scriptDir, 'node_modules');
        if (!await checkDirectory(nodeModulesPath, '  node_modules')) {
          log.warning(`    Run 'npm install' in ${scriptDir}`);
        }
      }
    }
    
    // For executable commands, check if they exist in PATH
    if (serverConfig.command !== 'node') {
      const isInPath = await checkCommandInPath(serverConfig.command);
      if (isInPath) {
        log.success(`  Command '${serverConfig.command}' found in PATH`);
      } else {
        log.error(`  Command '${serverConfig.command}' not found in PATH`);
      }
    }
    
    // Check environment variables
    if (serverConfig.env) {
      log.info('  Checking server-specific environment variables:');
      for (const [key, value] of Object.entries(serverConfig.env)) {
        if (value) {
          log.success(`    ${key} is set`);
        } else {
          log.error(`    ${key} is not set`);
        }
      }
    }
  }
}

async function checkCommandInPath(command) {
  return new Promise((resolve) => {
    const which = spawn('which', [command]);
    which.on('close', (code) => {
      resolve(code === 0);
    });
  });
}

async function testServerStartup(serverName, serverConfig) {
  log.info(`\nTesting ${serverName} startup...`);
  
  return new Promise((resolve) => {
    const projectRoot = path.join(__dirname, '..');
    const env = { ...process.env, ...serverConfig.env };
    
    // Resolve script path
    let args = [...serverConfig.args];
    if (serverConfig.command === 'node' && args.length > 0 && !path.isAbsolute(args[0])) {
      args[0] = path.join(projectRoot, args[0]);
    }
    
    const proc = spawn(serverConfig.command, args, {
      env,
      cwd: projectRoot
    });
    
    let output = '';
    let errorOutput = '';
    
    proc.stdout.on('data', (data) => {
      output += data.toString();
    });
    
    proc.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });
    
    // Give it 3 seconds to start
    setTimeout(() => {
      proc.kill();
      
      if (errorOutput.includes('Error') || errorOutput.includes('error')) {
        log.error(`  ${serverName} failed to start`);
        log.error(`  Error: ${errorOutput.split('\n')[0]}`);
        resolve(false);
      } else if (output || errorOutput) {
        log.success(`  ${serverName} started successfully`);
        resolve(true);
      } else {
        log.warning(`  ${serverName} produced no output`);
        resolve(false);
      }
    }, 3000);
    
    proc.on('error', (error) => {
      log.error(`  ${serverName} failed to spawn: ${error.message}`);
      resolve(false);
    });
  });
}

async function checkNodeVersion() {
  log.section('Checking Node.js Version');
  
  const nodeVersion = process.version;
  const majorVersion = parseInt(nodeVersion.split('.')[0].substring(1));
  
  log.info(`Node.js version: ${nodeVersion}`);
  
  if (majorVersion < 16) {
    log.error('Node.js version 16 or higher is required');
    return false;
  } else {
    log.success('Node.js version is compatible');
    return true;
  }
}

async function checkProjectStructure() {
  log.section('Checking Project Structure');
  
  const projectRoot = path.join(__dirname, '..');
  const requiredDirs = [
    'servers',
    'servers/github',
    'servers/filesystem',
    'servers/docker',
    'servers/memory',
    'data'
  ];
  
  let allExist = true;
  
  for (const dir of requiredDirs) {
    const dirPath = path.join(projectRoot, dir);
    if (!await checkDirectory(dirPath, `Directory ${dir}`)) {
      allExist = false;
    }
  }
  
  return allExist;
}

async function testAllServers(config) {
  log.section('Testing Server Startup');
  
  if (!config || !config.mcpServers) {
    log.error('Cannot test servers without configuration');
    return;
  }
  
  const results = {};
  
  for (const [serverName, serverConfig] of Object.entries(config.mcpServers)) {
    // Skip external servers for now
    if (serverName.includes('xcodebuild')) {
      log.info(`Skipping external server: ${serverName}`);
      continue;
    }
    
    const success = await testServerStartup(serverName, serverConfig);
    results[serverName] = success;
  }
  
  log.section('Server Startup Results');
  
  let allSuccess = true;
  for (const [serverName, success] of Object.entries(results)) {
    if (success) {
      log.success(`${serverName}: OK`);
    } else {
      log.error(`${serverName}: FAILED`);
      allSuccess = false;
    }
  }
  
  return allSuccess;
}

async function main() {
  console.log('\n🔍 MCP Server Diagnostics Tool\n');
  
  // Check Node.js version
  const nodeOk = await checkNodeVersion();
  
  // Check project structure
  const structureOk = await checkProjectStructure();
  
  // Check environment variables
  const envOk = await checkEnvironmentVariables();
  
  // Load and check Claude configuration
  const config = await loadClaudeConfig();
  
  if (config) {
    await checkMCPServers(config);
    
    // Test server startup
    await testAllServers(config);
  }
  
  // Summary
  log.section('Diagnostic Summary');
  
  if (!nodeOk) {
    log.error('Node.js version is incompatible');
  }
  
  if (!structureOk) {
    log.error('Project structure is incomplete');
  }
  
  if (!envOk) {
    log.error('Required environment variables are missing');
    log.info('\nTo fix this, run:');
    log.info('export GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token"');
    log.info('export MCP_GITHUB_TOKEN="your-github-token"');
  }
  
  if (!config) {
    log.error('Configuration file is missing or invalid');
  }
  
  if (nodeOk && structureOk && envOk && config) {
    log.success('\nBasic requirements are met!');
    log.info('\nNext steps:');
    log.info('1. Make sure all servers have their dependencies installed:');
    log.info('   cd servers/github && npm install');
    log.info('   cd servers/filesystem && npm install');
    log.info('   cd servers/docker && npm install');
    log.info('   cd servers/memory && npm install');
    log.info('\n2. Restart Claude Desktop after fixing any issues');
    log.info('3. Check Claude Desktop logs for more details');
  }
}

// Run diagnostics
main().catch(error => {
  log.error(`Unexpected error: ${error.message}`);
  process.exit(1);
});