#!/usr/bin/env node
/**
 * Redis Server Entry Point
 */

import { RedisServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const redisServer = new RedisServer();
  await runMCPServer(redisServer);
}

main().catch((error) => {
  console.error('Failed to start redis server:', error);
  process.exit(1);
});
