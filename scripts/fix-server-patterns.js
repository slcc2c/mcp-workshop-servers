#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

function fixServerFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  
  // Fix import if needed
  if (!content.includes('createToolHandler') && content.includes("from '../../src/core/base-server'")) {
    content = content.replace(
      "import { BaseMCPServer } from '../../src/core/base-server';",
      "import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';"
    );
  }
  
  // Remove any addTool helper methods
  const addToolHelperRegex = /\s*\/\/ Helper method.*?\n\s*private addTool\(.*?\): void \{[\s\S]*?\n\s*\}/g;
  content = content.replace(addToolHelperRegex, '');
  
  // Fix the pattern: this.addTool({ ... }) to this.registerTool(...)
  // This regex matches the full addTool call including nested objects
  const addToolRegex = /this\.addTool\(\{\s*name:\s*['"`]([^'"`]+)['"`],\s*description:\s*['"`]([^'"`]+)['"`],\s*inputSchema:\s*(\w+),\s*handler:\s*(async\s*\([^)]*\)\s*=>\s*\{[\s\S]*?^\s*\}),?\s*\}\);/gm;
  
  content = content.replace(addToolRegex, (match, name, description, schema, handler) => {
    // Clean up the handler - remove trailing comma if present
    handler = handler.trim();
    if (handler.endsWith(',')) {
      handler = handler.slice(0, -1);
    }
    
    return `this.registerTool(
      '${name}',
      '${description}',
      ${schema},
      createToolHandler(${handler})
    );`;
  });
  
  fs.writeFileSync(filePath, content);
  console.log(`Fixed: ${filePath}`);
}

// Process all servers that need fixing
const serversToFix = [
  'servers/redis/index.ts',
  'servers/postgresql/index.ts',
  'servers/mongodb/index.ts',
  'servers/neo4j/index.ts',
  'servers/kubernetes/index.ts',
  'servers/jupyter/index.ts'
];

serversToFix.forEach(server => {
  const fullPath = path.join(__dirname, '..', server);
  if (fs.existsSync(fullPath)) {
    try {
      fixServerFile(fullPath);
    } catch (error) {
      console.error(`Error fixing ${server}:`, error.message);
    }
  } else {
    console.warn(`File not found: ${fullPath}`);
  }
});

console.log('Done!');