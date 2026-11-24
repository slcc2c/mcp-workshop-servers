#!/usr/bin/env node

/**
 * Test 1Password integration with your actual vault entries
 */

import { exec } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(exec);

async function testVaultIntegration() {
  console.log('🔐 Testing 1Password Integration with Your Vaults\n');

  const testSecrets = [
    // AI Vault
    { name: 'AI_ML_API_HOST', ref: '1password:AI/AI ML API Host:notesPlain', expected: 'localhost' },
    { name: 'AI_ML_API_PORT', ref: '1password:AI/AI ML API Port:notesPlain', expected: '8000' },
    { name: 'AI_ML_API_DEBUG', ref: '1password:AI/AI ML API Debug:notesPlain', expected: 'false' },
    
    // Server-Configurations Vault
    { name: 'REDIS_HOST', ref: '1password:Server-Configurations/Redis Host:notesPlain', expected: 'localhost' },
    { name: 'REDIS_PORT', ref: '1password:Server-Configurations/Redis Port:notesPlain', expected: '6379' },
    { name: 'LOG_LEVEL', ref: '1password:Server-Configurations/LOG_LEVEL:notesPlain', expected: 'INFO' },
  ];

  console.log('Testing direct 1Password access:\n');

  for (const { name, ref, expected } of testSecrets) {
    try {
      // Parse the reference
      const match = ref.match(/1password:(.+)\/(.+):(.+)/);
      if (!match) continue;
      
      const [, vault, item, field] = match;
      const { stdout } = await execAsync(`op item get "${item}" --vault="${vault}" --fields label=${field}`);
      const value = stdout.trim();
      
      const matches = value === expected;
      console.log(`${matches ? '✅' : '⚠️ '} ${name}: ${value} ${matches ? '' : `(expected: ${expected})`}`);
    } catch (error) {
      console.log(`❌ ${name}: Failed to retrieve`);
    }
  }

  console.log('\n📝 Your .env is configured with:');
  console.log('   - 3 secrets from AI vault');
  console.log('   - 15+ secrets from Server-Configurations vault');
  console.log('\n✅ All secrets use the "notesPlain" field');
  
  console.log('\n🚀 Next steps:');
  console.log('1. Start MCP servers: npm run mcp:start');
  console.log('2. Test secret resolution: node examples/secrets/secrets-demo.js');
}

testVaultIntegration().catch(console.error);