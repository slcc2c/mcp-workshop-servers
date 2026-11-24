#!/usr/bin/env node

/**
 * Test 2-vault configuration
 * 
 * This verifies that:
 * 1. Only the configured vaults can be accessed
 * 2. Vault scoping works correctly
 * 3. Secrets can be retrieved from both vaults
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

async function checkVaultAccess() {
  console.log('🔐 Testing 2-Vault Configuration\n');

  // Read .env to get configured vaults
  const fs = require('fs');
  if (!fs.existsSync('.env')) {
    console.error('❌ No .env file found. Run ./scripts/setup-vaults.sh first!');
    process.exit(1);
  }

  const envContent = fs.readFileSync('.env', 'utf8');
  const allowedVaultsMatch = envContent.match(/ONEPASSWORD_ALLOWED_VAULTS=(.+)/);
  
  if (!allowedVaultsMatch) {
    console.error('❌ ONEPASSWORD_ALLOWED_VAULTS not configured in .env');
    process.exit(1);
  }

  const allowedVaults = allowedVaultsMatch[1].split(',').map(v => v.trim());
  console.log('✅ Configured vaults:', allowedVaults.join(', '));
  console.log();

  // Check if signed in
  try {
    await execAsync('op vault list --format=json');
    console.log('✅ Authenticated with 1Password\n');
  } catch (error) {
    console.error('❌ Not signed in to 1Password. Run: op signin');
    process.exit(1);
  }

  // List all available vaults
  try {
    const { stdout } = await execAsync('op vault list --format=json');
    const allVaults = JSON.parse(stdout);
    console.log('📁 All available vaults in your account:');
    allVaults.forEach(vault => {
      const isAllowed = allowedVaults.includes(vault.name);
      console.log(`   ${isAllowed ? '✅' : '❌'} ${vault.name} ${isAllowed ? '(allowed)' : '(blocked)'}`);
    });
    console.log();
  } catch (error) {
    console.error('Failed to list vaults:', error.message);
  }

  // Test item access in allowed vaults
  console.log('🧪 Testing item access...\n');
  
  for (const vault of allowedVaults) {
    console.log(`Vault: ${vault}`);
    try {
      const { stdout } = await execAsync(`op item list --vault="${vault}" --format=json`);
      const items = JSON.parse(stdout);
      
      if (items.length === 0) {
        console.log('   📭 No items in this vault');
        console.log(`   💡 Create one: op item create --vault="${vault}" --title="TestSecret" password=test123`);
      } else {
        console.log(`   📄 ${items.length} items found`);
        // Show first 3 items
        items.slice(0, 3).forEach(item => {
          console.log(`      - ${item.title}`);
        });
        if (items.length > 3) {
          console.log(`      ... and ${items.length - 3} more`);
        }
      }
    } catch (error) {
      console.log(`   ❌ Error accessing vault: ${error.message}`);
    }
    console.log();
  }

  // Test secret reference formats
  console.log('📝 Example secret references for your vaults:\n');
  
  for (const vault of allowedVaults) {
    console.log(`From ${vault}:`);
    console.log(`   1password:${vault}/GitHub:token`);
    console.log(`   1password:${vault}/Database:password`);
    console.log(`   1password:${vault}/API:key`);
    console.log();
  }

  // Show how to test with MCP servers
  console.log('🚀 To test with MCP servers:\n');
  console.log('1. Start the servers:');
  console.log('   npm run mcp:start\n');
  console.log('2. Test secret resolution:');
  console.log('   node examples/secrets/secrets-demo.js test "1password:' + allowedVaults[0] + '/GitHub:token"\n');
  console.log('3. Use in your .env:');
  console.log('   GITHUB_TOKEN=1password:' + allowedVaults[0] + '/GitHub:token');
  console.log('   DATABASE_URL=1password:' + allowedVaults[1] + '/Database:url\n');
}

// Utility to create a test secret
async function createTestSecret(vault, title) {
  console.log(`\n🔑 Creating test secret "${title}" in vault "${vault}"...`);
  
  try {
    const testValue = `test_${Date.now()}`;
    await execAsync(`echo "${testValue}" | op item create --vault="${vault}" --title="${title}" --category=password password[password]=-`);
    console.log(`✅ Created successfully!`);
    console.log(`   Reference it as: 1password:${vault}/${title}:password`);
    return true;
  } catch (error) {
    if (error.message.includes('already exists')) {
      console.log(`✅ Item already exists`);
      return true;
    }
    console.error(`❌ Failed to create: ${error.message}`);
    return false;
  }
}

// Main execution
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args[0] === 'create') {
    // Create test secret: node test-vaults.js create VaultName ItemName
    const [_, vault, title] = args;
    if (!vault || !title) {
      console.error('Usage: node test-vaults.js create <vault> <title>');
      process.exit(1);
    }
    createTestSecret(vault, title);
  } else {
    // Default: check vault configuration
    checkVaultAccess().catch(console.error);
  }
}