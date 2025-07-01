#!/bin/bash

# Fix ES module imports by adding .js extensions

echo "🔧 Fixing ES module imports in dist directory..."

# Fix imports in all server files
find /Users/spencer/repos/mcp-server/dist/servers -name "*.js" -type f | while read file; do
    echo "Fixing: $file"
    
    # Add .js extension to relative imports that don't have it
    # Match patterns like: from '../../src/core/base-server'
    sed -i '' -E "s/from '(\.\.[^']+)'/from '\1.js'/g" "$file"
    
    # Also fix imports that might use double quotes
    sed -i '' -E 's/from "(\.\.[^"]+)"/from "\1.js"/g' "$file"
    
    # Fix any imports that already have .js.js
    sed -i '' 's/\.js\.js/.js/g' "$file"
done

echo "✅ Import fixes complete!"