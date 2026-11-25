#!/bin/bash

# Remove file logging from logger to fix the logs directory issue

echo "🔧 Removing file logging from Winston logger..."

# Comment out or remove file transports from logger.js
sed -i '' '22,28d' /Users/spencer/repos/mcp-server/dist/src/utils/logger.js

# Fix the trailing comma
sed -i '' 's/}),$/})/' /Users/spencer/repos/mcp-server/dist/src/utils/logger.js

echo "✅ Logger fix complete!"