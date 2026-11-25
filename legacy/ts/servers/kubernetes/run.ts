#!/usr/bin/env node
/**
 * Kubernetes Server Entry Point
 */

import { KubernetesServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const kubernetesServer = new KubernetesServer();
  await runMCPServer(kubernetesServer);
}

main().catch((error) => {
  console.error('Failed to start kubernetes server:', error);
  process.exit(1);
});
