#!/usr/bin/env node
/**
 * Memory Server Entry Point
 */

import { MemoryServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const memoryServer = new MemoryServer();
  await runMCPServer(memoryServer);
}

main().catch((error) => {
  console.error('Failed to start memory server:', error);
  process.exit(1);
});
