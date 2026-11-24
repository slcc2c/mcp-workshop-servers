#!/usr/bin/env node

/**
 * GitHub MCP Server Health Check
 * Monitors the health of GitHub MCP server and sends alerts
 */

import https from 'https';
import fs from 'fs/promises';
import path from 'path';
import { spawn } from 'child_process';

const COLORS = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = '') {
  console.log(`${color}${message}${COLORS.reset}`);
}

/**
 * Check if GitHub token is valid
 */
async function checkTokenHealth(token) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'api.github.com',
      path: '/user',
      method: 'GET',
      headers: {
        'Authorization': `token ${token}`,
        'User-Agent': 'MCP-GitHub-Health-Check/1.0'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        if (res.statusCode === 200) {
          const parsed = JSON.parse(data);
          const rateLimit = {
            remaining: parseInt(res.headers['x-ratelimit-remaining']),
            limit: parseInt(res.headers['x-ratelimit-limit']),
            reset: new Date(parseInt(res.headers['x-ratelimit-reset']) * 1000)
          };
          
          resolve({
            healthy: true,
            user: parsed.login,
            rateLimit,
            scopes: res.headers['x-oauth-scopes'] || 'unknown'
          });
        } else {
          resolve({
            healthy: false,
            error: `HTTP ${res.statusCode}`,
            message: JSON.parse(data).message || 'Unknown error'
          });
        }
      });
    });
    
    req.on('error', (e) => {
      resolve({
        healthy: false,
        error: 'Network error',
        message: e.message
      });
    });
    
    req.end();
  });
}

/**
 * Check if MCP server process is running
 */
async function checkServerProcess() {
  return new Promise((resolve) => {
    const checkProcess = spawn('pgrep', ['-f', 'github-server']);
    
    let output = '';
    checkProcess.stdout.on('data', (data) => {
      output += data.toString();
    });
    
    checkProcess.on('close', (code) => {
      const pids = output.trim().split('\n').filter(pid => pid);
      resolve({
        running: code === 0 && pids.length > 0,
        pids: pids
      });
    });
  });
}

/**
 * Test MCP server directly
 */
async function testMCPServer() {
  return new Promise((resolve) => {
    const serverPath = path.join(process.cwd(), 'runners', 'github-server.js');
    const child = spawn('node', [serverPath], {
      env: { ...process.env },
      stdio: ['pipe', 'pipe', 'pipe']
    });
    
    let stderr = '';
    let stdout = '';
    let timeout;
    
    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    
    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    
    // Give it 5 seconds to start
    timeout = setTimeout(() => {
      child.kill();
      
      // Check if authentication succeeded
      if (stderr.includes('authenticated') || stderr.includes('running')) {
        resolve({ healthy: true, message: 'Server started successfully' });
      } else if (stderr.includes('Bad credentials')) {
        resolve({ healthy: false, message: 'Invalid GitHub token' });
      } else if (stderr.includes('Failed to authenticate')) {
        resolve({ healthy: false, message: 'Authentication failed' });
      } else {
        resolve({ healthy: false, message: 'Unknown startup error', stderr });
      }
    }, 5000);
    
    child.on('error', (error) => {
      clearTimeout(timeout);
      resolve({ healthy: false, message: error.message });
    });
  });
}

/**
 * Load health history
 */
async function loadHealthHistory() {
  const historyFile = path.join(process.cwd(), 'data', 'github-health-history.json');
  try {
    const data = await fs.readFile(historyFile, 'utf-8');
    return JSON.parse(data);
  } catch (e) {
    return [];
  }
}

/**
 * Save health check result
 */
async function saveHealthResult(result) {
  const dataDir = path.join(process.cwd(), 'data');
  await fs.mkdir(dataDir, { recursive: true });
  
  const historyFile = path.join(dataDir, 'github-health-history.json');
  const history = await loadHealthHistory();
  
  history.push({
    timestamp: new Date().toISOString(),
    ...result
  });
  
  // Keep last 7 days
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const filtered = history.filter(entry => new Date(entry.timestamp) > sevenDaysAgo);
  
  await fs.writeFile(historyFile, JSON.stringify(filtered, null, 2));
}

/**
 * Send alert (placeholder for actual alerting)
 */
async function sendAlert(message, severity = 'warning') {
  const alertFile = path.join(process.cwd(), 'data', 'github-alerts.log');
  const alert = {
    timestamp: new Date().toISOString(),
    severity,
    message
  };
  
  try {
    await fs.appendFile(alertFile, JSON.stringify(alert) + '\n');
  } catch (e) {
    console.error('Failed to write alert:', e.message);
  }
  
  // In a real implementation, this could:
  // - Send email
  // - Post to Slack
  // - Create GitHub issue
  // - Send macOS notification
  log(`ALERT [${severity}]: ${message}`, severity === 'error' ? COLORS.red : COLORS.yellow);
}

/**
 * Analyze health trends
 */
async function analyzeHealthTrends() {
  const history = await loadHealthHistory();
  
  if (history.length < 2) {
    return { trending: 'insufficient_data' };
  }
  
  // Count failures in last 24 hours
  const oneDayAgo = new Date();
  oneDayAgo.setDate(oneDayAgo.getDate() - 1);
  
  const recentChecks = history.filter(entry => new Date(entry.timestamp) > oneDayAgo);
  const failures = recentChecks.filter(entry => !entry.overall.healthy);
  
  return {
    trending: failures.length > recentChecks.length * 0.5 ? 'degrading' : 'stable',
    failureRate: (failures.length / recentChecks.length * 100).toFixed(1),
    totalChecks: recentChecks.length
  };
}

/**
 * Main health check
 */
async function performHealthCheck() {
  log('\n=== GitHub MCP Server Health Check ===', COLORS.cyan);
  log(`Time: ${new Date().toISOString()}`, COLORS.blue);
  
  const result = {
    token: { healthy: false },
    process: { healthy: false },
    server: { healthy: false },
    overall: { healthy: false }
  };
  
  // Check token health
  log('\nChecking GitHub token...', COLORS.blue);
  const token = process.env.GITHUB_PERSONAL_ACCESS_TOKEN || 
                process.env.GITHUB_TOKEN || 
                process.env.MCP_GITHUB_TOKEN;
                
  if (!token) {
    log('[✗] No GitHub token found', COLORS.red);
    result.token.error = 'No token configured';
    await sendAlert('No GitHub token configured', 'error');
  } else {
    const tokenHealth = await checkTokenHealth(token);
    result.token = tokenHealth;
    
    if (tokenHealth.healthy) {
      log(`[✓] Token valid for user: ${tokenHealth.user}`, COLORS.green);
      log(`    Rate limit: ${tokenHealth.rateLimit.remaining}/${tokenHealth.rateLimit.limit}`, COLORS.green);
      
      // Warn if rate limit is low
      if (tokenHealth.rateLimit.remaining < 100) {
        await sendAlert(`GitHub rate limit low: ${tokenHealth.rateLimit.remaining} remaining`, 'warning');
      }
    } else {
      log(`[✗] Token invalid: ${tokenHealth.message}`, COLORS.red);
      await sendAlert(`GitHub token invalid: ${tokenHealth.message}`, 'error');
    }
  }
  
  // Check server process
  log('\nChecking MCP server process...', COLORS.blue);
  const processHealth = await checkServerProcess();
  result.process = processHealth;
  
  if (processHealth.running) {
    log(`[✓] Server process running (PIDs: ${processHealth.pids.join(', ')})`, COLORS.green);
  } else {
    log('[✗] Server process not running', COLORS.yellow);
  }
  
  // Test server startup
  if (token) {
    log('\nTesting MCP server startup...', COLORS.blue);
    const serverTest = await testMCPServer();
    result.server = serverTest;
    
    if (serverTest.healthy) {
      log(`[✓] ${serverTest.message}`, COLORS.green);
    } else {
      log(`[✗] ${serverTest.message}`, COLORS.red);
      if (serverTest.stderr) {
        log(`    Error output: ${serverTest.stderr.substring(0, 200)}...`, COLORS.yellow);
      }
    }
  }
  
  // Overall health
  result.overall.healthy = result.token.healthy && 
                          (result.process.running || result.server.healthy);
  
  // Analyze trends
  const trends = await analyzeHealthTrends();
  result.trends = trends;
  
  log('\n=== Health Summary ===', COLORS.cyan);
  log(`Token Health: ${result.token.healthy ? 'OK' : 'FAILED'}`, 
      result.token.healthy ? COLORS.green : COLORS.red);
  log(`Process Health: ${result.process.running ? 'OK' : 'NOT RUNNING'}`,
      result.process.running ? COLORS.green : COLORS.yellow);
  log(`Server Health: ${result.server.healthy ? 'OK' : 'FAILED'}`,
      result.server.healthy ? COLORS.green : COLORS.red);
  log(`Overall: ${result.overall.healthy ? 'HEALTHY' : 'UNHEALTHY'}`,
      result.overall.healthy ? COLORS.green : COLORS.red);
      
  if (trends.trending !== 'insufficient_data') {
    log(`\nTrend Analysis:`, COLORS.blue);
    log(`Status: ${trends.trending}`, 
        trends.trending === 'stable' ? COLORS.green : COLORS.yellow);
    log(`Failure rate (24h): ${trends.failureRate}% (${trends.totalChecks} checks)`,
        COLORS.blue);
  }
  
  // Save result
  await saveHealthResult(result);
  
  return result;
}

// Run health check
performHealthCheck()
  .then(result => {
    if (!result.overall.healthy) {
      process.exit(1);
    }
  })
  .catch(error => {
    log(`Health check failed: ${error.message}`, COLORS.red);
    process.exit(1);
  });