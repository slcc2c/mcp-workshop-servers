#!/usr/bin/env node
/**
 * Photos Server Entry Point
 */

import { PhotosServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const photosServer = new PhotosServer();
  await runMCPServer(photosServer);
}

main().catch((error) => {
  console.error('Failed to start photos server:', error);
  process.exit(1);
});

