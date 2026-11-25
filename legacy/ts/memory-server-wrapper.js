#!/usr/bin/env node
// Wrapper script for MCP Memory Server with proper ES module support

import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Set up module resolution
process.env.NODE_PATH = join(__dirname, 'dist');

// Import and run the memory server
try {
    await import('./dist/servers/memory/index.js');
} catch (error) {
    console.error('Failed to start memory server:', error);
    process.exit(1);
}
