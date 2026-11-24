#!/bin/bash

# Fix imports in all TypeScript files to add .js extensions

# Fix imports in server files
find servers -name "*.ts" -type f | while read file; do
  echo "Fixing imports in $file"
  
  # Fix relative imports from src/core
  sed -i '' "s|from '\.\./\.\./src/core/base-server'|from '../../src/core/base-server.js'|g" "$file"
  sed -i '' "s|from '\.\./\.\./src/utils/errors'|from '../../src/utils/errors.js'|g" "$file"
  sed -i '' "s|from '\./index'|from './index.js'|g" "$file"
  
  # Fix imports in run.ts files
  sed -i '' "s|from '\.\./\.\./src/core/mcp-runner'|from '../../src/core/mcp-runner.js'|g" "$file"
done

# Fix imports in src files
find src -name "*.ts" -type f | while read file; do
  echo "Fixing imports in $file"
  
  # Fix relative imports
  sed -i '' "s|from '\./base-server'|from './base-server.js'|g" "$file"
  sed -i '' "s|from '\.\./utils/logger'|from '../utils/logger.js'|g" "$file"
  sed -i '' "s|from '\.\./utils/errors'|from '../utils/errors.js'|g" "$file"
  sed -i '' "s|from '\.\./types/|from '../types/|g" "$file"
done

echo "Import fixes complete!"