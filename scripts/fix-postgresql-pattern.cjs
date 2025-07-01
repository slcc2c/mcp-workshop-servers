#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

function fixPostgreSQLPattern(content) {
  // Replace all occurrences of the incorrect pattern
  const pattern = /this\.addTool\(createToolHandler\(\{\s*name:\s*['"`]([^'"`]+)['"`],\s*description:\s*['"`]([^'"`]+)['"`],\s*inputSchema:\s*(\w+),\s*handler:\s*(async\s*\([^)]*\)\s*=>\s*\{)/gm;
  
  return content.replace(pattern, (match, name, description, schema, handler) => {
    return `this.registerTool(\n      '${name}',\n      '${description}',\n      ${schema},\n      createToolHandler(${handler}`;
  });
  
  // Also fix the closing pattern
  return result.replace(/\}\s*,?\s*\}\)\);/gm, '      })\n    );');
}

// Fix PostgreSQL server
const pgFile = path.join(__dirname, '..', 'servers/postgresql/index.ts');
let content = fs.readFileSync(pgFile, 'utf8');

// Apply the fix
content = fixPostgreSQLPattern(content);

// Write back
fs.writeFileSync(pgFile, content);
console.log('Fixed PostgreSQL server patterns');