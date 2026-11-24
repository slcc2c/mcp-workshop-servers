#!/bin/bash

# Fix all run.ts files that are missing closing braces

for file in servers/*/run.ts; do
  echo "Fixing $file"
  # Check if the file ends with a line that doesn't have });
  if tail -1 "$file" | grep -q "^$"; then
    # Remove the last empty line and add });
    sed -i '' -e '$ d' "$file"
    echo "});" >> "$file"
  fi
done

echo "Run.ts files fixed!"