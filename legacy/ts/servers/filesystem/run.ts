#!/usr/bin/env node
/**
 * Filesystem Server Entry Point
 */

import { FilesystemServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const filesystemServer = new FilesystemServer();
  await runMCPServer(filesystemServer);
}

main().catch((error) => {
  console.error('Failed to start filesystem server:', error);
  process.exit(1);
});
