#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

function fixServerPatterns(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  let modified = false;
  
  // Fix imports if needed
  if (!content.includes('createToolHandler') && content.includes("from '../../src/core/base-server'")) {
    content = content.replace(
      "import { BaseMCPServer } from '../../src/core/base-server';",
      "import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';"
    );
    modified = true;
  }
  
  // Pattern 1: PostgreSQL-style incorrect pattern
  // this.addTool(createToolHandler({ name: ..., description: ..., inputSchema: ..., handler: ... }));
  if (content.includes('this.addTool(createToolHandler({')) {
    // Fix method name
    content = content.replace('protected defineTools(): void {', 'protected async registerTools(): Promise<void> {');
    
    // Fix each tool registration
    let index = 0;
    while (true) {
      const match = content.indexOf('this.addTool(createToolHandler({', index);
      if (match === -1) break;
      
      // Find the end of this block
      let braceCount = 0;
      let i = match + 'this.addTool(createToolHandler('.length;
      let blockEnd = -1;
      
      while (i < content.length) {
        if (content[i] === '{') braceCount++;
        else if (content[i] === '}') {
          braceCount--;
          if (braceCount === 0) {
            // Look for }));
            if (content.substring(i, i + 4) === '}));') {
              blockEnd = i + 4;
              break;
            }
          }
        }
        i++;
      }
      
      if (blockEnd === -1) {
        console.error('Could not find end of block at', match);
        index = match + 1;
        continue;
      }
      
      // Extract the content
      const fullBlock = content.substring(match, blockEnd);
      
      // Parse the properties
      const nameMatch = fullBlock.match(/name:\s*['"`]([^'"`]+)['"`]/);
      const descMatch = fullBlock.match(/description:\s*['"`]([^'"`]+)['"`]/);
      const schemaMatch = fullBlock.match(/inputSchema:\s*(\w+)/);
      const handlerMatch = fullBlock.match(/handler:\s*(async\s*\([^)]*\)\s*=>\s*\{[\s\S]*)/);
      
      if (!nameMatch || !descMatch || !schemaMatch || !handlerMatch) {
        console.error('Could not parse block:', fullBlock.substring(0, 100));
        index = blockEnd;
        continue;
      }
      
      // Extract handler body
      let handlerContent = handlerMatch[1];
      // Remove the trailing },
      handlerContent = handlerContent.replace(/\s*\},?\s*$/, '\n      }');
      
      // Build replacement
      const replacement = `this.registerTool(
      '${nameMatch[1]}',
      '${descMatch[1]}',
      ${schemaMatch[1]},
      createToolHandler(${handlerContent})
    );`;
      
      // Replace
      content = content.substring(0, match) + replacement + content.substring(blockEnd);
      
      // Update index
      index = match + replacement.length;
    }
    modified = true;
  }
  
  // Pattern 2: Redis-style pattern (already handled by previous script)
  // this.addTool({ name: ..., description: ..., inputSchema: ..., handler: ... });
  if (content.includes('this.addTool({') && !content.includes('createToolHandler({')) {
    // This was handled by the previous script
    console.log('Redis-style pattern detected, skipping...');
  }
  
  return { content, modified };
}

// Process all servers
const servers = [
  'servers/postgresql/index.ts',
  'servers/mongodb/index.ts',
  'servers/neo4j/index.ts',
  'servers/kubernetes/index.ts',
  'servers/jupyter/index.ts'
];

servers.forEach(serverPath => {
  const fullPath = path.join(__dirname, '..', serverPath);
  
  try {
    const { content, modified } = fixServerPatterns(fullPath);
    
    if (modified) {
      fs.writeFileSync(fullPath, content);
      console.log(`✓ Fixed ${serverPath}`);
    } else {
      console.log(`✓ ${serverPath} - no changes needed`);
    }
  } catch (error) {
    console.error(`✗ Error fixing ${serverPath}:`, error.message);
  }
});

console.log('Done!');