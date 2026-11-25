#!/bin/bash

# Add closing braces to all files that need them

files=(
  # Server index files
  "servers/docker/index.ts"
  "servers/filesystem/index.ts"
  "servers/github/index.ts"
  "servers/jupyter/index.ts"
  "servers/kubernetes/index.ts"
  "servers/memory/index.ts"
  "servers/mongodb/index.ts"
  "servers/neo4j/index.ts"
  "servers/postgresql/index.ts"
  "servers/redis/index.ts"
  "servers/xcodebuild/index.ts"
  
  # Source files
  "src/config/defaults.ts"
  "src/gateway/auth.ts"
  "src/gateway/middleware.ts"
  "src/gateway/router.ts"
  "src/gateway/server-manager.ts"
  "src/gateway/stdio-adapter.ts"
  "src/gateway/websocket.ts"
  "src/integrations/openai-adapter.ts"
  "src/secrets/cache.ts"
  "src/secrets/manager.ts"
  "src/secrets/providers/base.ts"
  "src/secrets/providers/environment.ts"
  "src/secrets/providers/onepassword.ts"
  "src/secrets/types.ts"
  "src/types/config.ts"
  "src/types/logger.ts"
  "src/types/mcp.ts"
  "src/utils/config.ts"
  "src/utils/errors.ts"
  "src/utils/logger.ts"
  "src/utils/secrets-config.ts"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    echo "Fixing $file"
    # Simply append a closing brace to each file
    echo "}" >> "$file"
  fi
done

echo "All files fixed!"