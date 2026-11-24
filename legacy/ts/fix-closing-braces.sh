#!/bin/bash

# Fix files that are missing closing braces or have syntax issues

# Fix src/core/mcp-runner.ts
echo "Fixing src/core/mcp-runner.ts"
sed -i '' '$ s/^$/}/' src/core/mcp-runner.ts

# Fix src/gateway/routes/secrets.ts - needs export default
echo "Fixing src/gateway/routes/secrets.ts"
echo "export default router;" >> src/gateway/routes/secrets.ts

# Fix other TypeScript files that might have issues
files=(
  "src/types/logger.ts"
  "src/types/mcp.ts"
  "src/types/config.ts"
  "src/secrets/types.ts"
  "src/secrets/index.ts"
  "src/gateway/auth.ts"
  "src/gateway/index.ts"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    # Check if file ends with an empty line
    if [ "$(tail -c 1 "$file")" == "" ]; then
      echo "File $file already ends properly"
    else
      # Only add a closing brace if the file seems to need it
      last_line=$(tail -1 "$file")
      if [[ ! "$last_line" =~ \}$ ]] && [[ ! "$last_line" =~ \;$ ]]; then
        echo "Adding closing brace to $file"
        echo "}" >> "$file"
      fi
    fi
  fi
done

echo "Closing braces fixed!"