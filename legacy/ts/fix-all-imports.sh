#!/bin/bash

# Fix ALL imports in TypeScript files to add .js extensions

echo "Fixing imports in all TypeScript files..."

# Find all TypeScript files and fix imports
find . -name "*.ts" -type f ! -path "./node_modules/*" ! -path "./dist/*" ! -path "./external/*" | while read file; do
  echo "Processing: $file"
  
  # Create a temporary file
  temp_file="${file}.tmp"
  
  # Process the file line by line
  while IFS= read -r line; do
    # Check if the line contains an import from a relative path
    if echo "$line" | grep -q "from '[\.]\+/[^']*'"; then
      # Extract the import path
      import_path=$(echo "$line" | sed -n "s/.*from '\([^']*\)'.*/\1/p")
      
      # Check if the import path ends with .js, .json, or contains node_modules
      if ! echo "$import_path" | grep -qE '\.(js|json)$|node_modules'; then
        # Add .js extension
        new_line=$(echo "$line" | sed "s|from '\([^']*\)'|from '\1.js'|")
        echo "$new_line" >> "$temp_file"
      else
        echo "$line" >> "$temp_file"
      fi
    else
      echo "$line" >> "$temp_file"
    fi
  done < "$file"
  
  # Replace the original file with the temporary file
  mv "$temp_file" "$file"
done

echo "Import fixes complete!"