#!/usr/bin/env node

/**
 * Direct test of GitHub integration with secrets
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import https from 'https';
import dotenv from 'dotenv';

dotenv.config();

const execAsync = promisify(exec);

async function testGitHubDirect() {
  console.log('🔐 Testing GitHub Integration\n');

  // Get token reference from env
  const tokenRef = process.env.GITHUB_TOKEN;
  console.log('1️⃣  Token reference:', tokenRef);

  if (!tokenRef || !tokenRef.includes('1password:')) {
    console.error('❌ GITHUB_TOKEN not configured with 1Password reference');
    return;
  }

  // Parse and resolve the token
  const match = tokenRef.match(/1password:(.+)\/(.+):(.+)/);
  if (!match) {
    console.error('❌ Invalid token reference format');
    return;
  }

  const [, vault, item, field] = match;
  console.log('2️⃣  Resolving from 1Password...');
  console.log(`   Vault: ${vault}`);
  console.log(`   Item: ${item}`);
  console.log(`   Field: ${field}`);

  try {
    const { stdout } = await execAsync(`op item get "${item}" --vault="${vault}" --fields label=${field}`);
    const token = stdout.trim();
    
    console.log('✅ Token retrieved successfully');
    console.log(`   Length: ${token.length} characters`);

    // Test GitHub API
    console.log('\n3️⃣  Testing GitHub API...');
    
    // List user repos
    const repos = await githubRequest('/user/repos?per_page=5', token);
    console.log(`✅ Found ${repos.length} repositories:`);
    repos.forEach(repo => {
      console.log(`   - ${repo.full_name} (${repo.private ? 'private' : 'public'})`);
    });

    // Get rate limit
    const rateLimit = await githubRequest('/rate_limit', token);
    console.log('\n4️⃣  Rate Limit Status:');
    console.log(`   Core: ${rateLimit.rate.remaining}/${rateLimit.rate.limit}`);
    console.log(`   Search: ${rateLimit.resources.search.remaining}/${rateLimit.resources.search.limit}`);

    console.log('\n✅ GitHub integration is working perfectly!');
    console.log('\n🚀 You can now use the GitHub MCP server with:');
    console.log('   - All repository operations');
    console.log('   - Issue and PR management');
    console.log('   - Code search');
    console.log('   - And 40+ other GitHub tools');

  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

async function githubRequest(path, token) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.github.com',
      path,
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
          reject(new Error(`GitHub API error: ${res.statusCode}`));
        }
      });
    }).on('error', reject);
  });
}

testGitHubDirect().catch(console.error);