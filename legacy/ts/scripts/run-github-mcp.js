#!/usr/bin/env node

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Ensure GitHub token is available
if (!process.env.GITHUB_PERSONAL_ACCESS_TOKEN) {
  console.error('Error: GITHUB_PERSONAL_ACCESS_TOKEN environment variable is not set');
  process.exit(1);
}

// Pass through the token and spawn the GitHub MCP server
const githubServer = spawn('npx', ['-y', '@modelcontextprotocol/server-github'], {
  stdio: 'inherit',
  env: {
    ...process.env,
    GITHUB_PERSONAL_ACCESS_TOKEN: process.env.GITHUB_PERSONAL_ACCESS_TOKEN
  }
});

githubServer.on('error', (err) => {
  console.error('Failed to start GitHub MCP server:', err);
  process.exit(1);
});

githubServer.on('exit', (code) => {
  if (code !== 0) {
    console.error(`GitHub MCP server exited with code ${code}`);
  }
  process.exit(code || 0);
});

// Handle termination signals
process.on('SIGINT', () => {
  githubServer.kill('SIGINT');
});

process.on('SIGTERM', () => {
  githubServer.kill('SIGTERM');
});