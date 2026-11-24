#!/usr/bin/env node

/**
 * Simple runner for XcodeBuildMCP server
 * This script provides a direct way to run the XcodeBuildMCP server for Claude Desktop
 */

import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Check if running in MCP mode (via stdio)
const isMCPMode = !process.argv.includes('--help') && !process.argv.includes('--version');

if (!isMCPMode) {
  console.log('XcodeBuildMCP Server Runner');
  console.log('This script runs the XcodeBuildMCP server for Claude Desktop integration');
  process.exit(0);
}

// Path to the actual XcodeBuildMCP repository
const XCODEBUILD_MCP_PATH = process.env.XCODEBUILD_MCP_PATH || path.join(__dirname, '..', 'external', 'XcodeBuildMCP');

// Check if XcodeBuildMCP is installed
if (!fs.existsSync(XCODEBUILD_MCP_PATH)) {
  console.error(`XcodeBuildMCP not found at: ${XCODEBUILD_MCP_PATH}`);
  console.error('Please clone it from: https://github.com/cameroncooke/XcodeBuildMCP');
  console.error('Or set XCODEBUILD_MCP_PATH environment variable');
  process.exit(1);
}

// Check if it's built
const builtPath = path.join(XCODEBUILD_MCP_PATH, 'build', 'index.js');
if (!fs.existsSync(builtPath)) {
  console.error('XcodeBuildMCP is not built. Please run:');
  console.error(`cd ${XCODEBUILD_MCP_PATH} && npm install && npm run build`);
  process.exit(1);
}

// Run the XcodeBuildMCP server
const xcodeBuildProcess = spawn('node', [builtPath], {
  stdio: 'inherit',
  env: {
    ...process.env,
    NODE_ENV: 'production'
  }
});

xcodeBuildProcess.on('error', (err) => {
  console.error('Failed to start XcodeBuildMCP:', err);
  process.exit(1);
});

xcodeBuildProcess.on('exit', (code) => {
  process.exit(code || 0);
});