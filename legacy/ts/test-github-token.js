#!/usr/bin/env node

/**
 * Test GitHub token from 1Password
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import https from 'https';

const execAsync = promisify(exec);

async function testGitHubToken() {
  console.log('🔐 Testing GitHub Token from 1Password\n');

  try {
    // Get token from 1Password
    console.log('1️⃣  Fetching token from 1Password...');
    const { stdout } = await execAsync('op item get "GitHub Token" --vault=AI --fields label=notesPlain');
    const token = stdout.trim();
    
    console.log('✅ Token retrieved (length: ' + token.length + ')');
    console.log('   Format: ' + token.substring(0, 10) + '...');

    // Test with GitHub API
    console.log('\n2️⃣  Testing token with GitHub API...');
    
    const userData = await new Promise((resolve, reject) => {
      const options = {
        hostname: 'api.github.com',
        path: '/user',
        method: 'GET',
        headers: {
          'Authorization': `token ${token}`,
          'User-Agent': 'MCP-Server-Test',
          'Accept': 'application/vnd.github.v3+json'
        }
      };

      https.get(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve(JSON.parse(data));
          } else {
            reject(new Error(`GitHub API returned ${res.statusCode}: ${data}`));
          }
        });
      }).on('error', reject);
    });

    console.log('✅ GitHub API access successful!');
    console.log('   User: ' + userData.login);
    console.log('   Name: ' + userData.name);
    console.log('   Public repos: ' + userData.public_repos);

    // Check token scopes
    console.log('\n3️⃣  Checking token permissions...');
    const scopesData = await new Promise((resolve, reject) => {
      const options = {
        hostname: 'api.github.com',
        path: '/rate_limit',
        method: 'GET',
        headers: {
          'Authorization': `token ${token}`,
          'User-Agent': 'MCP-Server-Test'
        }
      };

      https.get(options, (res) => {
        const scopes = res.headers['x-oauth-scopes'] || 'classic token';
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          const rateLimit = JSON.parse(data);
          resolve({ scopes, rateLimit });
        });
      }).on('error', reject);
    });

    console.log('✅ Token scopes: ' + (scopesData.scopes || 'Not available'));
    console.log('   Rate limit: ' + scopesData.rateLimit.rate.remaining + '/' + scopesData.rateLimit.rate.limit);

    console.log('\n✅ GitHub Token Configuration Complete!');
    console.log('\n🚀 Your GitHub MCP server is ready to use:');
    console.log('   - Token is valid and working');
    console.log('   - Stored securely in 1Password AI vault');
    console.log('   - Referenced in .env as GITHUB_TOKEN');
    console.log('\n📝 Test with MCP servers:');
    console.log('   npm run mcp:start');
    console.log('   node examples/basic/github-demo.js');

  } catch (error) {
    console.error('\n❌ Error:', error.message);
    
    if (error.message.includes('401')) {
      console.log('\n💡 Token seems invalid. Make sure you:');
      console.log('   1. Created a Personal Access Token at https://github.com/settings/tokens');
      console.log('   2. Selected necessary scopes (repo, read:user)');
      console.log('   3. Copied the complete token');
    }
  }
}

testGitHubToken().catch(console.error);