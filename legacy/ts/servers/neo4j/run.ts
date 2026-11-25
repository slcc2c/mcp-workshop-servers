#!/usr/bin/env node
/**
 * Neo4j Server Entry Point
 */

import { Neo4jServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const neo4jServer = new Neo4jServer();
  await runMCPServer(neo4jServer);
}

main().catch((error) => {
  console.error('Failed to start neo4j server:', error);
  process.exit(1);
});
