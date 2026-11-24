#!/usr/bin/env node

/**
 * GitHub MCP Server Demo
 * 
 * This example demonstrates:
 * - Listing repositories
 * - Creating issues
 * - Working with branches
 * - Repository information
 */

const http = require('http');

async function makeGitHubRequest(tool, args = {}) {
  const requestData = JSON.stringify({
    id: `github-${Date.now()}`,
    method: 'executeTool',
    params: {
      tool,
      arguments: args
    },
    server: 'github'
  });

  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: '/api/v1/execute',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(requestData)
      }
    }, (res) => {
      let data = '';
      
      res.on('data', chunk => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (response.error) {
            reject(new Error(response.error.message));
          } else {
            resolve(response.result);
          }
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('error', reject);
    req.write(requestData);
    req.end();
  });
}

async function main() {
  console.log('🐙 GitHub MCP Server Demo\n');
  
  if (!process.env.GITHUB_TOKEN) {
    console.error('❌ GITHUB_TOKEN environment variable is required');
    console.log('💡 Set your GitHub token:');
    console.log('   export GITHUB_TOKEN="your-token-here"');
    process.exit(1);
  }

  try {
    // List repositories
    console.log('📚 Listing your repositories...');
    const repos = await makeGitHubRequest('github_list_repos', {
      type: 'owner',
      sort: 'updated',
      perPage: 5
    });
    
    console.log(`✅ Found ${repos.length} repositories:`);
    repos.forEach((repo, index) => {
      console.log(`   ${index + 1}. ${repo.name}`);
      console.log(`      ${repo.description || 'No description'}`);
      console.log(`      Updated: ${new Date(repo.updatedAt).toLocaleDateString()}`);
      console.log(`      URL: ${repo.url}`);
      console.log();
    });
    
    if (repos.length > 0) {
      const firstRepo = repos[0];
      const [owner, repoName] = firstRepo.fullName.split('/');
      
      // Get detailed repository info
      console.log(`🔍 Getting details for ${firstRepo.name}...`);
      const repoInfo = await makeGitHubRequest('github_get_repo', {
        owner,
        repo: repoName
      });
      
      console.log('✅ Repository details:', {
        name: repoInfo.name,
        description: repoInfo.description,
        language: repoInfo.language,
        stars: repoInfo.stars,
        forks: repoInfo.forks,
        defaultBranch: repoInfo.defaultBranch
      });
      
      // List branches
      console.log(`\n🌿 Listing branches for ${firstRepo.name}...`);
      const branches = await makeGitHubRequest('github_list_branches', {
        owner,
        repo: repoName
      });
      
      console.log(`✅ Found ${branches.length} branches:`);
      branches.slice(0, 5).forEach(branch => {
        console.log(`   • ${branch.name} ${branch.protected ? '(protected)' : ''}`);
      });
      
      // List recent commits
      console.log(`\n📝 Recent commits for ${firstRepo.name}...`);
      const commits = await makeGitHubRequest('github_list_commits', {
        owner,
        repo: repoName,
        perPage: 3
      });
      
      console.log(`✅ Recent commits:`);
      commits.forEach(commit => {
        console.log(`   • ${commit.sha.substring(0, 7)}: ${commit.message.split('\n')[0]}`);
        console.log(`     By: ${commit.author} on ${new Date(commit.date).toLocaleDateString()}`);
      });
      
      // List issues
      console.log(`\n🐛 Issues for ${firstRepo.name}...`);
      const issues = await makeGitHubRequest('github_list_issues', {
        owner,
        repo: repoName,
        state: 'open',
        perPage: 3
      });
      
      if (issues.length > 0) {
        console.log(`✅ Found ${issues.length} open issues:`);
        issues.forEach(issue => {
          console.log(`   • #${issue.number}: ${issue.title}`);
          console.log(`     Created: ${new Date(issue.createdAt).toLocaleDateString()}`);
          console.log(`     Labels: ${issue.labels.join(', ') || 'none'}`);
        });
      } else {
        console.log('✅ No open issues found');
      }
    }
    
    // Demonstrate search
    console.log('\n🔍 Searching for code...');
    try {
      const codeSearch = await makeGitHubRequest('searchCode', {
        query: 'function main language:javascript',
        perPage: 3
      });
      
      console.log(`✅ Code search results (${codeSearch.totalCount} total):`);
      codeSearch.items.forEach(item => {
        console.log(`   • ${item.name} in ${item.repository}`);
        console.log(`     Path: ${item.path}`);
      });
    } catch (error) {
      console.log('⚠️  Code search requires additional permissions');
    }
    
    console.log('\n🎉 GitHub demo completed successfully!');
    
  } catch (error) {
    console.error('❌ Error:', error.message);
    
    if (error.message.includes('authentication')) {
      console.log('\n💡 GitHub authentication failed. Check your token:');
      console.log('   1. Go to https://github.com/settings/tokens');
      console.log('   2. Generate a new token with appropriate scopes');
      console.log('   3. Set GITHUB_TOKEN environment variable');
    } else {
      console.log('\n💡 Make sure the MCP servers are running:');
      console.log('   npm run mcp:start');
    }
    
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}