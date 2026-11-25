#!/usr/bin/env node
/**
 * Jupyter Server Entry Point
 */

import { JupyterServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const jupyterServer = new JupyterServer();
  await runMCPServer(jupyterServer);
}

main().catch((error) => {
  console.error('Failed to start jupyter server:', error);
  process.exit(1);
});
