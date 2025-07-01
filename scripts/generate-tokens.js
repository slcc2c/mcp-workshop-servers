#!/usr/bin/env node

/**
 * Generate secure authentication tokens for MCP clients
 */

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Generate a secure token
function generateToken() {
  return crypto.randomBytes(32).toString('base64url');
}

// Client configurations
const clients = [
  {
    id: 'claude',
    name: 'Claude Desktop',
    envVar: 'MCP_CLAUDE_AUTH_TOKEN',
    description: 'Authentication token for Claude Desktop',
  },
  {
    id: 'cursor',
    name: 'Cursor IDE',
    envVar: 'MCP_CURSOR_AUTH_TOKEN',
    description: 'Authentication token for Cursor IDE',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    envVar: 'MCP_OPENAI_AUTH_TOKEN',
    description: 'Authentication token for OpenAI function calling',
  },
  {
    id: 'default',
    name: 'Default Client',
    envVar: 'MCP_DEFAULT_AUTH_TOKEN',
    description: 'Authentication token for other clients',
  },
];

console.log('🔐 MCP Client Token Generator');
console.log('=============================\n');

const tokens = {};
const envLines = [];

// Generate tokens for each client
clients.forEach(client => {
  const token = generateToken();
  tokens[client.id] = token;
  
  console.log(`${client.name}:`);
  console.log(`  Token: ${token}`);
  console.log(`  Env Variable: ${client.envVar}`);
  console.log(`  Description: ${client.description}`);
  console.log('');
  
  envLines.push(`# ${client.description}`);
  envLines.push(`${client.envVar}=${token}`);
  envLines.push('');
});

// Create .env.tokens file
const envContent = `# MCP Client Authentication Tokens
# Generated on ${new Date().toISOString()}
# 
# IMPORTANT: Keep these tokens secure!
# Add these to your .env file or store in 1Password

${envLines.join('\n')}`;

const tokensFile = path.join(__dirname, '..', '.env.tokens');
fs.writeFileSync(tokensFile, envContent);

console.log(`✅ Tokens saved to: ${tokensFile}`);
console.log('\n📋 Next steps:');
console.log('1. Copy the tokens from .env.tokens to your .env file');
console.log('2. Store the tokens in 1Password for secure management');
console.log('3. Delete the .env.tokens file after securing the tokens');
console.log('\n🔒 1Password CLI commands to store tokens:');

clients.forEach(client => {
  console.log(`op item create --category="API Credential" --title="MCP ${client.name} Token" --vault="AI" notesPlain="${tokens[client.id]}"`);
});

console.log('\n⚠️  Remember to delete .env.tokens after securing the tokens!');