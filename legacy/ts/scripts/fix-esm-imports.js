#!/usr/bin/env node
/**
 * Fix ES module imports by adding .js extensions
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.join(__dirname, '..');

async function fixImportsInFile(filePath) {
  try {
    let content = await fs.readFile(filePath, 'utf8');
    
    // Fix relative imports (starting with ./ or ../)
    content = content.replace(
      /from\s+['"](\.\.?\/[^'"]+)(?<!\.js)['"]/g,
      "from '$1.js'"
    );
    
    // Fix imports statements
    content = content.replace(
      /import\s+['"](\.\.?\/[^'"]+)(?<!\.js)['"]/g,
      "import '$1.js'"
    );
    
    await fs.writeFile(filePath, content);
    return true;
  } catch (error) {
    console.error(`Error fixing ${filePath}:`, error.message);
    return false;
  }
}

async function findJsFiles(dir, files = []) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await findJsFiles(fullPath, files);
    } else if (entry.name.endsWith('.js')) {
      files.push(fullPath);
    }
  }
  
  return files;
}

async function main() {
  console.log('Fixing ES module imports in dist directory...\n');
  
  const distDir = path.join(projectRoot, 'dist');
  const jsFiles = await findJsFiles(distDir);
  
  let fixed = 0;
  let failed = 0;
  
  for (const file of jsFiles) {
    if (await fixImportsInFile(file)) {
      fixed++;
    } else {
      failed++;
    }
  }
  
  console.log(`\nFixed imports in ${fixed} files`);
  if (failed > 0) {
    console.log(`Failed to fix ${failed} files`);
  }
}

main().catch(console.error);