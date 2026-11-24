#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

function transformAddToolToRegisterTool(content) {
  // First, fix the import if needed
  if (!content.includes('createToolHandler') && content.includes("from '../../src/core/base-server'")) {
    content = content.replace(
      "import { BaseMCPServer } from '../../src/core/base-server';",
      "import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';"
    );
  }
  
  // Remove helper method if it exists
  content = content.replace(/\s*\/\/ Helper method to bridge old addTool pattern to new registerTool\s*\n\s*private addTool\(config: \{ name: string; description: string; inputSchema: z\.ZodType<any>; handler: \(params: any\) => Promise<any> \}\): void \{\s*\n\s*this\.registerTool\(config\.name, config\.description, config\.inputSchema, config\.handler\);\s*\n\s*\}/g, '');
  
  // Transform all addTool calls
  let result = content;
  let startIndex = 0;
  
  while (true) {
    // Find next occurrence of this.addTool({
    const addToolStart = result.indexOf('this.addTool({', startIndex);
    if (addToolStart === -1) break;
    
    // Find the matching closing });
    let braceCount = 0;
    let i = addToolStart + 'this.addTool('.length;
    let endIndex = -1;
    
    while (i < result.length) {
      if (result[i] === '{') braceCount++;
      else if (result[i] === '}') {
        braceCount--;
        if (braceCount === 0) {
          // Check if next chars are );
          if (result.substring(i, i + 3) === '});') {
            endIndex = i + 3;
            break;
          }
        }
      }
      i++;
    }
    
    if (endIndex === -1) {
      console.error('Could not find matching closing for addTool at position', addToolStart);
      startIndex = addToolStart + 1;
      continue;
    }
    
    // Extract the content between { and }
    const blockStart = addToolStart + 'this.addTool({'.length;
    const blockEnd = endIndex - '});'.length;
    const blockContent = result.substring(blockStart, blockEnd);
    
    // Parse the properties
    const nameMatch = blockContent.match(/name:\s*['"`]([^'"`]+)['"`]/);
    const descMatch = blockContent.match(/description:\s*['"`]([^'"`]+)['"`]/);
    const schemaMatch = blockContent.match(/inputSchema:\s*(\w+)/);
    
    if (!nameMatch || !descMatch || !schemaMatch) {
      console.error('Could not parse addTool block at position', addToolStart);
      startIndex = endIndex;
      continue;
    }
    
    const name = nameMatch[1];
    const description = descMatch[1];
    const schema = schemaMatch[1];
    
    // Find handler
    const handlerMatch = blockContent.match(/handler:\s*(async\s*\([^)]*\)\s*=>\s*\{)/);
    if (!handlerMatch) {
      console.error('Could not find handler in addTool block at position', addToolStart);
      startIndex = endIndex;
      continue;
    }
    
    // Find the handler's closing brace
    const handlerStart = blockContent.indexOf(handlerMatch[0]) + handlerMatch[0].length;
    let handlerBraceCount = 1;
    let j = handlerStart;
    let handlerEnd = -1;
    
    while (j < blockContent.length && handlerBraceCount > 0) {
      if (blockContent[j] === '{') handlerBraceCount++;
      else if (blockContent[j] === '}') {
        handlerBraceCount--;
        if (handlerBraceCount === 0) {
          handlerEnd = j + 1;
          break;
        }
      }
      j++;
    }
    
    if (handlerEnd === -1) {
      console.error('Could not find handler closing brace');
      startIndex = endIndex;
      continue;
    }
    
    // Extract full handler
    const fullHandler = blockContent.substring(
      blockContent.indexOf(handlerMatch[1]), 
      handlerEnd
    ).trim();
    
    // Clean up trailing comma if present
    let cleanHandler = fullHandler;
    if (cleanHandler.endsWith(',')) {
      cleanHandler = cleanHandler.slice(0, -1);
    }
    
    // Build replacement
    const indent = result.substring(result.lastIndexOf('\n', addToolStart) + 1, addToolStart);
    const replacement = `${indent}this.registerTool(
      '${name}',
      '${description}',
      ${schema},
      createToolHandler(${cleanHandler})
    );`;
    
    // Replace in the result
    result = result.substring(0, addToolStart) + replacement + result.substring(endIndex);
    
    // Update startIndex for next search
    startIndex = addToolStart + replacement.length;
  }
  
  return result;
}

// Process files
const files = [
  'servers/redis/index.ts',
  'servers/postgresql/index.ts', 
  'servers/mongodb/index.ts',
  'servers/neo4j/index.ts',
  'servers/kubernetes/index.ts',
  'servers/jupyter/index.ts'
];

files.forEach(file => {
  const filePath = path.join(__dirname, '..', file);
  
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const transformed = transformAddToolToRegisterTool(content);
    
    if (content !== transformed) {
      fs.writeFileSync(filePath, transformed);
      console.log(`✓ Fixed ${file}`);
    } else {
      console.log(`✓ ${file} already correct or no changes needed`);
    }
  } catch (error) {
    console.error(`✗ Error processing ${file}:`, error.message);
  }
});

console.log('Done!');