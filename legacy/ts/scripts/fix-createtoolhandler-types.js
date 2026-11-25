#!/usr/bin/env node

/**
 * Script to automatically add type annotations to createToolHandler calls
 * Usage: node fix-createtoolhandler-types.js <server-file>
 */

const fs = require('fs');
const path = require('path');

function extractSchemaName(toolRegistration) {
  // Extract the schema parameter from registerTool call
  const schemaMatch = toolRegistration.match(/registerTool\s*\(\s*['"][\w_]+['"]\s*,\s*['"][^'"]+['"]\s*,\s*(\w+Schema|\w+|z\.object)/);
  if (schemaMatch) {
    return schemaMatch[1];
  }
  return null;
}

function fixCreateToolHandler(content) {
  let fixed = content;
  let changeCount = 0;
  
  // Find all registerTool calls with createToolHandler
  const registerToolPattern = /this\.registerTool\s*\(\s*['"][\w_]+['"]\s*,\s*['"][^'"]+['"]\s*,\s*([\w.]+(?:\([^)]*\))?)\s*,\s*createToolHandler\s*\(/g;
  
  let match;
  const replacements = [];
  
  while ((match = registerToolPattern.exec(content)) !== null) {
    const fullMatch = match[0];
    const schemaName = match[1];
    
    // Find the end of this registerTool call to get the full context
    let depth = 1;
    let i = match.index + fullMatch.length;
    let toolEnd = i;
    
    while (depth > 0 && i < content.length) {
      if (content[i] === '(') depth++;
      if (content[i] === ')') depth--;
      if (depth === 0) toolEnd = i;
      i++;
    }
    
    const toolRegistration = content.substring(match.index, toolEnd + 1);
    
    // Check if it already has a type annotation
    if (toolRegistration.includes('createToolHandler<')) {
      continue;
    }
    
    // Determine the type to add
    let typeAnnotation = '';
    
    if (schemaName.endsWith('Schema')) {
      // Named schema
      typeAnnotation = `z.infer<typeof ${schemaName}>`;
    } else if (schemaName.startsWith('z.object')) {
      // Inline schema - extract parameter names
      const paramsMatch = toolRegistration.match(/async\s*\(\s*\{([^}]+)\}/);
      if (paramsMatch) {
        const params = paramsMatch[1].split(',').map(p => p.trim());
        // Try to infer types from the schema definition
        const schemaContent = schemaName;
        const types = [];
        
        for (const param of params) {
          const paramName = param.split(':')[0].trim();
          // Look for the parameter definition in the schema
          const paramPattern = new RegExp(`${paramName}:\\s*z\\.(\\w+)\\(`, 'g');
          const paramMatch = paramPattern.exec(schemaContent);
          
          if (paramMatch) {
            const zodType = paramMatch[1];
            let tsType = 'any';
            
            // Map zod types to TypeScript types
            switch(zodType) {
              case 'string': tsType = 'string'; break;
              case 'number': tsType = 'number'; break;
              case 'boolean': tsType = 'boolean'; break;
              case 'array': tsType = 'any[]'; break;
              case 'object': tsType = 'Record<string, any>'; break;
              case 'enum': tsType = 'string'; break;
              default: tsType = 'any';
            }
            
            types.push(`${paramName}: ${tsType}`);
          } else {
            types.push(`${paramName}: any`);
          }
        }
        
        typeAnnotation = `{ ${types.join('; ')} }`;
      }
    }
    
    if (typeAnnotation) {
      replacements.push({
        find: 'createToolHandler(',
        replace: `createToolHandler<${typeAnnotation}>(`,
        context: toolRegistration
      });
      changeCount++;
    }
  }
  
  // Apply replacements
  for (const replacement of replacements) {
    fixed = fixed.replace(replacement.context, replacement.context.replace(replacement.find, replacement.replace));
  }
  
  return { fixed, changeCount };
}

// Main execution
const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('Usage: node fix-createtoolhandler-types.js <server-file>');
  process.exit(1);
}

const filePath = args[0];
if (!fs.existsSync(filePath)) {
  console.error(`File not found: ${filePath}`);
  process.exit(1);
}

const content = fs.readFileSync(filePath, 'utf8');
const { fixed, changeCount } = fixCreateToolHandler(content);

if (changeCount > 0) {
  fs.writeFileSync(filePath, fixed);
  console.log(`✅ Fixed ${changeCount} createToolHandler calls in ${path.basename(filePath)}`);
} else {
  console.log(`✨ No changes needed in ${path.basename(filePath)}`);
}