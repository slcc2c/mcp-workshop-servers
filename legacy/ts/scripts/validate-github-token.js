#!/usr/bin/env node

/**
 * GitHub Token Validation Script
 * Validates GitHub personal access tokens and provides detailed diagnostics
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import https from 'https';

const execAsync = promisify(exec);

const COLORS = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = '') {
  console.log(`${color}${message}${COLORS.reset}`);
}

function success(message) {
  log(`[✓] ${message}`, COLORS.green);
}

function error(message) {
  log(`[✗] ${message}`, COLORS.red);
}

function warning(message) {
  log(`[⚠] ${message}`, COLORS.yellow);
}

function info(message) {
  log(`[INFO] ${message}`, COLORS.blue);
}

function section(title) {
  log(`\n=== ${title} ===`, COLORS.cyan);
}

/**
 * Test GitHub API with token
 */
async function testGitHubToken(token, tokenName) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'api.github.com',
      path: '/user',
      method: 'GET',
      headers: {
        'Authorization': `token ${token}`,
        'User-Agent': 'MCP-GitHub-Token-Validator/1.0'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          
          if (res.statusCode === 200) {
            resolve({
              valid: true,
              user: parsed.login,
              name: parsed.name,
              scopes: res.headers['x-oauth-scopes'] || 'unknown',
              rateLimit: res.headers['x-ratelimit-remaining']
            });
          } else {
            resolve({
              valid: false,
              error: parsed.message || 'Unknown error',
              statusCode: res.statusCode
            });
          }
        } catch (e) {
          resolve({
            valid: false,
            error: 'Failed to parse response',
            statusCode: res.statusCode
          });
        }
      });
    });
    
    req.on('error', (e) => {
      resolve({
        valid: false,
        error: e.message
      });
    });
    
    req.end();
  });
}

/**
 * Check token expiration from GitHub Settings
 */
async function checkTokenExpiration(token) {
  return new Promise((resolve) => {
    const options = {
      hostname: 'api.github.com',
      path: '/user/installations',
      method: 'GET',
      headers: {
        'Authorization': `token ${token}`,
        'User-Agent': 'MCP-GitHub-Token-Validator/1.0'
      }
    };

    const req = https.request(options, (res) => {
      // GitHub returns expiration info in headers for some endpoints
      const expiresAt = res.headers['github-authentication-token-expiration'];
      resolve(expiresAt || null);
    });
    
    req.on('error', () => {
      resolve(null);
    });
    
    req.end();
  });
}

/**
 * Store token validation results
 */
async function saveValidationResults(results) {
  const dataDir = path.join(process.cwd(), 'data');
  await fs.mkdir(dataDir, { recursive: true });
  
  const logFile = path.join(dataDir, 'github-token-validation.json');
  
  let history = [];
  try {
    const existing = await fs.readFile(logFile, 'utf-8');
    history = JSON.parse(existing);
  } catch (e) {
    // File doesn't exist yet
  }
  
  history.push({
    timestamp: new Date().toISOString(),
    ...results
  });
  
  // Keep only last 30 days of history
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
  history = history.filter(entry => new Date(entry.timestamp) > thirtyDaysAgo);
  
  await fs.writeFile(logFile, JSON.stringify(history, null, 2));
}

/**
 * Main validation function
 */
async function validateGitHubTokens() {
  section('GitHub Token Validation');
  
  const results = {
    tokensChecked: [],
    allValid: true,
    recommendations: []
  };
  
  // Check GITHUB_PERSONAL_ACCESS_TOKEN
  const personalToken = process.env.GITHUB_PERSONAL_ACCESS_TOKEN;
  if (personalToken) {
    info('Checking GITHUB_PERSONAL_ACCESS_TOKEN...');
    const result = await testGitHubToken(personalToken, 'GITHUB_PERSONAL_ACCESS_TOKEN');
    
    if (result.valid) {
      success(`Token is valid for user: ${result.user} (${result.name || 'No name set'})`);
      success(`Scopes: ${result.scopes}`);
      success(`Rate limit remaining: ${result.rateLimit}`);
      
      const expiration = await checkTokenExpiration(personalToken);
      if (expiration) {
        warning(`Token expires: ${expiration}`);
        results.recommendations.push(`Set a reminder to renew token before ${expiration}`);
      }
    } else {
      error(`Token is invalid: ${result.error}`);
      results.allValid = false;
      results.recommendations.push('Generate a new GitHub Personal Access Token');
    }
    
    results.tokensChecked.push({
      name: 'GITHUB_PERSONAL_ACCESS_TOKEN',
      ...result
    });
  } else {
    error('GITHUB_PERSONAL_ACCESS_TOKEN is not set');
    results.allValid = false;
    results.recommendations.push('Set GITHUB_PERSONAL_ACCESS_TOKEN environment variable');
  }
  
  // Check GITHUB_TOKEN
  const githubToken = process.env.GITHUB_TOKEN;
  if (githubToken && githubToken !== personalToken) {
    info('\nChecking GITHUB_TOKEN...');
    const result = await testGitHubToken(githubToken, 'GITHUB_TOKEN');
    
    if (result.valid) {
      success(`Token is valid for user: ${result.user}`);
    } else {
      error(`Token is invalid: ${result.error}`);
      results.allValid = false;
    }
    
    results.tokensChecked.push({
      name: 'GITHUB_TOKEN',
      ...result
    });
  }
  
  // Check MCP_GITHUB_TOKEN
  const mcpToken = process.env.MCP_GITHUB_TOKEN;
  if (mcpToken && mcpToken !== personalToken && mcpToken !== githubToken) {
    info('\nChecking MCP_GITHUB_TOKEN...');
    const result = await testGitHubToken(mcpToken, 'MCP_GITHUB_TOKEN');
    
    if (result.valid) {
      success(`Token is valid for user: ${result.user}`);
    } else {
      error(`Token is invalid: ${result.error}`);
      results.allValid = false;
    }
    
    results.tokensChecked.push({
      name: 'MCP_GITHUB_TOKEN',
      ...result
    });
  }
  
  // Save results
  await saveValidationResults(results);
  
  section('Recommendations');
  
  if (results.recommendations.length > 0) {
    results.recommendations.forEach(rec => {
      info(`• ${rec}`);
    });
  } else {
    success('All tokens are valid and properly configured!');
  }
  
  // Check if tokens need to be synced
  if (!mcpToken && personalToken) {
    warning('\nMCP_GITHUB_TOKEN is not set. The MCP server may expect this.');
    info('To fix, add to your shell profile:');
    info('export MCP_GITHUB_TOKEN="$GITHUB_PERSONAL_ACCESS_TOKEN"');
  }
  
  return results;
}

// Run validation
validateGitHubTokens()
  .then(results => {
    if (!results.allValid) {
      process.exit(1);
    }
  })
  .catch(err => {
    error(`Validation failed: ${err.message}`);
    process.exit(1);
  });