#!/usr/bin/env node
/**
 * MongoDB Server Entry Point
 */

import { MongoDBServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const mongodbServer = new MongoDBServer();
  await runMCPServer(mongodbServer);
}

main().catch((error) => {
  console.error('Failed to start mongodb server:', error);
  process.exit(1);
});
