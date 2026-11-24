#!/bin/bash

# Add startup code to each MCP server

echo "🔧 Adding startup code to MCP servers..."

# Docker server
echo "Fixing Docker server..."
cat >> /Users/spencer/repos/mcp-server/dist/servers/docker/index.js << 'EOF'

// Auto-start server when run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    const server = new DockerServer();
    server.start().catch(error => {
        console.error('Failed to start server:', error);
        process.exit(1);
    });
}
EOF

# Memory server
echo "Fixing Memory server..."
cat >> /Users/spencer/repos/mcp-server/dist/servers/memory/index.js << 'EOF'

// Auto-start server when run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    const server = new MemoryServer();
    server.start().catch(error => {
        console.error('Failed to start server:', error);
        process.exit(1);
    });
}
EOF

# Jupyter server
echo "Fixing Jupyter server..."
cat >> /Users/spencer/repos/mcp-server/dist/servers/jupyter/index.js << 'EOF'

// Auto-start server when run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    const server = new JupyterServer();
    server.start().catch(error => {
        console.error('Failed to start server:', error);
        process.exit(1);
    });
}
EOF

# Kubernetes server
echo "Fixing Kubernetes server..."
cat >> /Users/spencer/repos/mcp-server/dist/servers/kubernetes/index.js << 'EOF'

// Auto-start server when run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    const server = new KubernetesServer();
    server.start().catch(error => {
        console.error('Failed to start server:', error);
        process.exit(1);
    });
}
EOF

echo "✅ Server startup code added!"