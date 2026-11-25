#!/usr/bin/env node
/**
 * PostgreSQL Server Entry Point
 */

import { PostgreSQLServer } from './index.js';
import { runMCPServer } from '../../src/core/mcp-runner.js';

async function main() {
  const postgresqlServer = new PostgreSQLServer();
  await runMCPServer(postgresqlServer);
}

main().catch((error) => {
  console.error('Failed to start postgresql server:', error);
  process.exit(1);
});
