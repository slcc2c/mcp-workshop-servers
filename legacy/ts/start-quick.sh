#!/bin/bash
# Quick start script for testing

echo "🚀 Starting MCP Servers (Quick Mode)"
echo

# Start GitHub server
echo "Starting GitHub server..."
GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN" npx -y @modelcontextprotocol/server-github &
GITHUB_PID=$!
echo "✅ GitHub server started (PID: $GITHUB_PID)"

# Start Filesystem server  
echo "Starting Filesystem server..."
npx -y @modelcontextprotocol/server-filesystem "$PWD" &
FS_PID=$!
echo "✅ Filesystem server started (PID: $FS_PID)"

# Start Memory server (using npx)
echo "Starting Memory server..."
npx -y @modelcontextprotocol/server-memory &
MEM_PID=$!
echo "✅ Memory server started (PID: $MEM_PID)"

echo
echo "🎉 Servers running!"
echo "Press Ctrl+C to stop all servers"
echo

# Wait and handle shutdown
trap "echo 'Stopping servers...'; kill $GITHUB_PID $FS_PID $MEM_PID 2>/dev/null; exit" INT TERM
wait