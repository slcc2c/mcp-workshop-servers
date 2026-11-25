#!/usr/bin/env node
/**
 * Docker Server Entry Point
 */

import { DockerServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const dockerServer = new DockerServer();
  await runMCPServer(dockerServer);
}

main().catch((error) => {
  console.error('Failed to start docker server:', error);
  process.exit(1);
});
