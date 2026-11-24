#!/usr/bin/env node

/**
 * Secrets Management Demo
 * 
 * This example demonstrates:
 * - Multiple secret providers (Environment, 1Password)
 * - Secret reference resolution
 * - Cache management
 * - Secure configuration access
 * 
 * Prerequisites:
 * - 1Password CLI installed (optional)
 * - Environment variables or 1Password items configured
 */

const http = require('http');

// Mock secrets manager API endpoints
async function makeSecretsRequest(endpoint, method = 'GET', body = null) {
  const requestData = body ? JSON.stringify(body) : null;
  
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: `/api/v1/secrets${endpoint}`,
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(requestData && { 'Content-Length': Buffer.byteLength(requestData) })
      }
    }, (res) => {
      let data = '';
      
      res.on('data', chunk => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (res.statusCode >= 400) {
            reject(new Error(response.error || `HTTP ${res.statusCode}`));
          } else {
            resolve(response);
          }
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('error', reject);
    if (requestData) {
      req.write(requestData);
    }
    req.end();
  });
}

async function demonstrateSecrets() {
  console.log('🔐 MCP Secrets Management Demo\n');

  try {
    // 1. Check available providers
    console.log('1️⃣  Checking available secret providers...');
    const providers = await makeSecretsRequest('/providers');
    console.log('✅ Available providers:', providers.providers);
    console.log('   Default provider:', providers.defaultProvider);

    // 2. Test environment variable access
    console.log('\n2️⃣  Testing environment variable access...');
    try {
      const envTest = await makeSecretsRequest('/get', 'POST', {
        reference: 'env:USER'
      });
      console.log('✅ Environment variable USER:', envTest.value);
    } catch (error) {
      console.log('⚠️  Could not access USER environment variable');
    }

    // 3. Test secret references
    console.log('\n3️⃣  Testing secret reference resolution...');
    const secretReferences = [
      'GITHUB_TOKEN',                    // Direct env var or resolved reference
      '1password:GitHub:token',          // Explicit 1Password reference
      'env:HOME',                        // Explicit environment reference
      'secret://environment/PATH'        // URL format
    ];

    for (const ref of secretReferences) {
      try {
        const result = await makeSecretsRequest('/get', 'POST', {
          reference: ref
        });
        console.log(`✅ ${ref}: ${result.value.substring(0, 20)}...`);
      } catch (error) {
        console.log(`❌ ${ref}: ${error.message}`);
      }
    }

    // 4. Check cache statistics
    console.log('\n4️⃣  Checking cache statistics...');
    const cacheStats = await makeSecretsRequest('/cache/stats');
    console.log('✅ Cache stats:', {
      enabled: cacheStats.enabled,
      size: cacheStats.size,
      maxSize: cacheStats.maxSize,
      hitRate: `${Math.round((cacheStats.hits / (cacheStats.hits + cacheStats.misses)) * 100)}%`
    });

    // 5. List secrets (if supported by provider)
    console.log('\n5️⃣  Listing available secrets...');
    
    if (providers.providers.includes('1password')) {
      try {
        const secrets = await makeSecretsRequest('/list?provider=1password');
        console.log('✅ 1Password secrets:');
        secrets.secrets.slice(0, 5).forEach(secret => {
          console.log(`   📄 ${secret.name} (updated: ${new Date(secret.lastUpdated).toLocaleDateString()})`);
        });
        if (secrets.secrets.length > 5) {
          console.log(`   ... and ${secrets.secrets.length - 5} more`);
        }
      } catch (error) {
        console.log('⚠️  Could not list 1Password secrets:', error.message);
      }
    }

    // 6. Test server-specific secrets
    console.log('\n6️⃣  Testing server-specific secret resolution...');
    const servers = ['github', 'postgres', 'redis'];
    
    for (const server of servers) {
      try {
        const serverSecrets = await makeSecretsRequest(`/server/${server}`);
        console.log(`✅ ${server} server secrets:`, Object.keys(serverSecrets.secrets));
      } catch (error) {
        console.log(`⚠️  No secrets configured for ${server} server`);
      }
    }

    // 7. Demonstrate secure configuration patterns
    console.log('\n7️⃣  Secure configuration patterns...');
    
    // Pattern 1: Direct secret reference
    console.log('\n   Pattern 1: Direct references in environment');
    console.log('   export GITHUB_TOKEN="1password:GitHub:token"');
    console.log('   # Automatically resolved when accessed');
    
    // Pattern 2: Fallback chain
    console.log('\n   Pattern 2: Fallback chain for resilience');
    console.log('   const token = await config.get("GITHUB_TOKEN") ||');
    console.log('                 await config.get("GH_TOKEN") ||');
    console.log('                 "default-token";');
    
    // Pattern 3: Bulk loading
    console.log('\n   Pattern 3: Bulk loading for efficiency');
    console.log('   const secrets = await secretsManager.getSecrets([');
    console.log('     "GITHUB_TOKEN",');
    console.log('     "DATABASE_URL",');
    console.log('     "REDIS_URL"');
    console.log('   ]);');

    // 8. Security audit demonstration
    console.log('\n8️⃣  Security audit features...');
    try {
      const auditLog = await makeSecretsRequest('/audit?limit=5');
      console.log('✅ Recent secret access:');
      auditLog.events.forEach(event => {
        const time = new Date(event.timestamp).toLocaleTimeString();
        const status = event.success ? '✅' : '❌';
        console.log(`   ${status} ${time}: ${event.action} ${event.secretName} (${event.provider})`);
      });
    } catch (error) {
      console.log('⚠️  Audit logging not enabled');
    }

    // 9. Performance considerations
    console.log('\n9️⃣  Performance optimization tips...');
    console.log('   • Use caching with appropriate TTL');
    console.log('   • Batch secret requests when possible');
    console.log('   • Pre-warm cache on startup');
    console.log('   • Use service accounts for non-interactive access');
    console.log('   • Monitor provider latency');

    // 10. Error handling demonstration
    console.log('\n🔟 Error handling examples...');
    
    // Test invalid reference
    try {
      await makeSecretsRequest('/get', 'POST', {
        reference: 'invalid:reference:format:too:many:parts'
      });
    } catch (error) {
      console.log('✅ Invalid reference handled:', error.message);
    }
    
    // Test non-existent secret
    try {
      await makeSecretsRequest('/get', 'POST', {
        reference: '1password:NonExistent:field'
      });
    } catch (error) {
      console.log('✅ Non-existent secret handled:', error.message);
    }

    console.log('\n🎉 Secrets management demo completed!');
    console.log('\n📚 Next steps:');
    console.log('   1. Set up 1Password CLI: brew install --cask 1password-cli');
    console.log('   2. Configure service account: export ONEPASSWORD_SERVICE_ACCOUNT_TOKEN="..."');
    console.log('   3. Create secrets: op item create --category=password --title="MySecret"');
    console.log('   4. Use in configuration: export MY_SECRET="1password:MySecret:password"');
    console.log('   5. Read the guide: docs/guides/secrets-management.md');

  } catch (error) {
    console.error('❌ Error:', error.message);
    console.log('\n💡 Make sure:');
    console.log('   1. MCP servers are running: npm run mcp:start');
    console.log('   2. Secrets endpoints are available');
    console.log('   3. 1Password CLI is installed (if using 1Password)');
  }
}

// Utility function to test a specific secret
async function testSecret(reference) {
  try {
    const result = await makeSecretsRequest('/get', 'POST', { reference });
    console.log(`✅ Successfully resolved: ${reference}`);
    console.log(`   Value: ${result.value.substring(0, 30)}...`);
    console.log(`   Provider: ${result.provider}`);
    console.log(`   Cached: ${result.cached}`);
  } catch (error) {
    console.log(`❌ Failed to resolve: ${reference}`);
    console.log(`   Error: ${error.message}`);
  }
}

// Command line interface
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.length > 0 && args[0] === 'test') {
    // Test specific secret: node secrets-demo.js test GITHUB_TOKEN
    const reference = args[1] || 'GITHUB_TOKEN';
    console.log(`🔐 Testing secret: ${reference}\n`);
    testSecret(reference);
  } else {
    // Run full demo
    demonstrateSecrets();
  }
}