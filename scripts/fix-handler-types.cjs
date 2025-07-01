#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

// Add explicit type parameters to createToolHandler
function fixHandlerTypes(content) {
  // Find all registerTool calls and extract the schema name
  const lines = content.split('\n');
  let modified = false;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Look for registerTool calls
    if (line.includes('this.registerTool(')) {
      // Look ahead to find the schema
      let schemaName = null;
      for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
        const schemaLine = lines[j];
        const schemaMatch = schemaLine.match(/^\s*(\w+Schema),?\s*$/);
        if (schemaMatch) {
          schemaName = schemaMatch[1];
          break;
        }
      }
      
      if (schemaName) {
        // Look for createToolHandler on the next few lines
        for (let j = i + 1; j < Math.min(i + 6, lines.length); j++) {
          if (lines[j].includes('createToolHandler(')) {
            // Add type parameter if not already present
            if (!lines[j].includes('createToolHandler<')) {
              lines[j] = lines[j].replace(
                'createToolHandler(',
                `createToolHandler<z.infer<typeof ${schemaName}>>(` 
              );
              modified = true;
            }
            break;
          }
        }
      }
    }
  }
  
  return modified ? lines.join('\n') : content;
}

// Process files
const files = [
  'servers/redis/index.ts',
];

files.forEach(file => {
  const filePath = path.join(__dirname, '..', file);
  
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const fixed = fixHandlerTypes(content);
    
    if (content !== fixed) {
      fs.writeFileSync(filePath, fixed);
      console.log(`✓ Fixed handler types in ${file}`);
    } else {
      console.log(`✓ ${file} - no changes needed`);
    }
  } catch (error) {
    console.error(`✗ Error processing ${file}:`, error.message);
  }
});

console.log('Done!');