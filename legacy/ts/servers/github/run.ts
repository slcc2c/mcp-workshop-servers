#!/usr/bin/env node
/**
 * GitHub Server Entry Point
 */

import { GitHubServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const githubServer = new GitHubServer();
  await runMCPServer(githubServer);
}

main().catch((error) => {
  console.error('Failed to start github server:', error);
  process.exit(1);
});
