#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

// Remove explicit type annotations from createToolHandler params
function cleanupTypes(content) {
  // Pattern to match: createToolHandler(async (params: z.infer<typeof SomeSchema>) => {
  // Replace with: createToolHandler(async (params) => {
  const pattern = /createToolHandler\(async \(params: z\.infer<typeof \w+>\) => \{/g;
  
  return content.replace(pattern, 'createToolHandler(async (params) => {');
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
    const cleaned = cleanupTypes(content);
    
    if (content !== cleaned) {
      fs.writeFileSync(filePath, cleaned);
      console.log(`✓ Cleaned type annotations in ${file}`);
    } else {
      console.log(`✓ ${file} - no type annotations to clean`);
    }
  } catch (error) {
    console.error(`✗ Error processing ${file}:`, error.message);
  }
});

console.log('Done!');