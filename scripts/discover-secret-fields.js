#!/usr/bin/env node

/**
 * Discover field names in your 1Password entries
 * This helps you find the exact field names to use in references
 */

import { exec } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(exec);

async function discoverSecrets() {
  console.log('🔍 Discovering Your 1Password Secret Structure\n');

  const vaults = ['AI', 'Server-Configurations'];
  const references = [];

  for (const vault of vaults) {
    console.log(`\n📁 Vault: ${vault}`);
    console.log('=' .repeat(50));

    try {
      // Get all items in vault
      const { stdout: itemsJson } = await execAsync(`op item list --vault="${vault}" --format=json`);
      const items = JSON.parse(itemsJson);

      for (const item of items) {
        console.log(`\n📄 ${item.title}`);
        
        try {
          // Get full item details
          const { stdout: itemJson } = await execAsync(`op item get "${item.id}" --vault="${vault}" --format=json`);
          const fullItem = JSON.parse(itemJson);

          // Find all fields with values
          const fields = fullItem.fields || [];
          const validFields = fields.filter(f => f.value && f.label);

          if (validFields.length > 0) {
            console.log('   Available fields:');
            validFields.forEach(field => {
              const reference = `1password:${vault}/${item.title}:${field.label}`;
              console.log(`   - ${field.label} → ${reference}`);
              
              // Guess common env var names
              const envVarSuggestions = guessEnvVarName(vault, item.title, field.label);
              if (envVarSuggestions.length > 0) {
                console.log(`     Suggested env var: ${envVarSuggestions.join(' or ')}`);
                references.push({
                  envVar: envVarSuggestions[0],
                  reference: reference
                });
              }
            });
          }

          // Check for special sections (like database credentials)
          if (fullItem.sections) {
            fullItem.sections.forEach(section => {
              if (section.fields && section.fields.length > 0) {
                console.log(`   Section: ${section.label || 'Additional Fields'}`);
                section.fields.forEach(field => {
                  if (field.value) {
                    const reference = `1password:${vault}/${item.title}:${field.label}`;
                    console.log(`   - ${field.label} → ${reference}`);
                  }
                });
              }
            });
          }

        } catch (error) {
          console.log(`   ⚠️  Could not read item details`);
        }
      }

    } catch (error) {
      console.log(`❌ Error reading vault: ${error.message}`);
    }
  }

  // Generate .env suggestions
  if (references.length > 0) {
    console.log('\n\n📝 Suggested .env entries:');
    console.log('=' .repeat(50));
    console.log('\n# Add these to your .env file:\n');
    
    references.forEach(({ envVar, reference }) => {
      console.log(`${envVar}=${reference}`);
    });
  }

  console.log('\n\n✅ Discovery complete!');
}

function guessEnvVarName(vault, itemTitle, fieldLabel) {
  const suggestions = [];
  
  // Common patterns
  const patterns = [
    // GitHub
    { item: /github/i, field: /token|pat|personal/i, env: 'GITHUB_TOKEN' },
    { item: /github/i, field: /api/i, env: 'GITHUB_API_KEY' },
    
    // OpenAI
    { item: /openai/i, field: /api|key/i, env: 'OPENAI_API_KEY' },
    { item: /openai/i, field: /org/i, env: 'OPENAI_ORG_ID' },
    
    // Anthropic
    { item: /anthropic|claude/i, field: /api|key/i, env: 'ANTHROPIC_API_KEY' },
    
    // Databases
    { item: /postgres|postgresql|pg/i, field: /url|uri|connection/i, env: 'POSTGRES_URL' },
    { item: /redis/i, field: /url|uri|connection/i, env: 'REDIS_URL' },
    { item: /mongo/i, field: /url|uri|connection/i, env: 'MONGODB_URL' },
    { item: /database/i, field: /postgres/i, env: 'POSTGRES_URL' },
    
    // Auth
    { item: /auth/i, field: /secret|key/i, env: 'AUTH_SECRET' },
    { item: /jwt/i, field: /secret|key/i, env: 'JWT_SECRET' },
    
    // Docker
    { item: /docker/i, field: /token|registry/i, env: 'DOCKER_REGISTRY_TOKEN' },
    { item: /docker/i, field: /username/i, env: 'DOCKER_USERNAME' },
  ];

  for (const pattern of patterns) {
    if (pattern.item.test(itemTitle) && pattern.field.test(fieldLabel)) {
      suggestions.push(pattern.env);
    }
  }

  // Generic fallback
  if (suggestions.length === 0) {
    const cleanItem = itemTitle.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();
    const cleanField = fieldLabel.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();
    suggestions.push(`${cleanItem}_${cleanField}`);
  }

  return suggestions;
}

// Run discovery
discoverSecrets().catch(console.error);