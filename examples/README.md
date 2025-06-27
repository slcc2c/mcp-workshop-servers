# MCP Workshop Examples

This directory contains example implementations showing how to use the MCP Workshop Servers for various tasks.

## Prerequisites

Before running examples, make sure:

1. **Servers are running**:
   ```bash
   npm run mcp:start
   ```

2. **Environment variables are set** (for applicable examples):
   ```bash
   export GITHUB_TOKEN="your-github-token"
   ```

## Basic Examples

### Hello World (`basic/hello-world.js`)

A simple example demonstrating basic MCP server communication using the Memory server.

**What it demonstrates:**
- Storing memories
- Retrieving memories by ID
- Searching memories
- Listing tags

**Usage:**
```bash
node examples/basic/hello-world.js
```

### GitHub Demo (`basic/github-demo.js`)

Comprehensive GitHub integration example using the GitHub MCP server.

**What it demonstrates:**
- Listing repositories
- Getting repository details
- Listing branches and commits
- Working with issues
- Code search functionality

**Prerequisites:**
- GitHub personal access token set as `GITHUB_TOKEN`

**Usage:**
```bash
export GITHUB_TOKEN="your-token-here"
node examples/basic/github-demo.js
```

### Filesystem Demo (`basic/filesystem-demo.js`)

Complete filesystem operations demonstration using the Filesystem MCP server.

**What it demonstrates:**
- Secure file read/write operations
- Directory creation and management
- File copying and moving
- Real-time file watching
- Content and filename search
- Path sandboxing and security
- Operation tracking

**Usage:**
```bash
node examples/basic/filesystem-demo.js
```

## Workshop Scenarios

### Rapid Prototyping Workflow

This example shows the complete "5-minute magic" workflow:

1. **Project Setup**:
   ```bash
   node examples/workshops/rapid-prototype.js create-project my-app
   ```

2. **Repository Creation**:
   ```bash
   node examples/workshops/rapid-prototype.js setup-repo my-app
   ```

3. **Development Environment**:
   ```bash
   node examples/workshops/rapid-prototype.js setup-dev my-app
   ```

### AI-Assisted Development

Examples showing how AI assistants can leverage MCP servers:

- **Context Building**: How Memory server maintains context across sessions
- **Code Generation**: Using GitHub server for repository scaffolding
- **Automated Workflows**: Combining multiple servers for complex tasks

## Advanced Examples

### Custom Server Development

Examples for creating your own MCP servers:

- **Basic Server Template**: Minimal MCP server implementation
- **Database Integration**: Server with PostgreSQL/Redis integration
- **API Wrapper**: Wrapping external APIs as MCP tools

### Multi-Server Orchestration

Examples showing coordination between multiple MCP servers:

- **File + GitHub**: Local development with automatic repository sync
- **Memory + All Servers**: Context-aware operations across all tools
- **Database + Docker**: Containerized database operations

## Integration Examples

### Claude Desktop Integration

Configuration examples for various scenarios:

- **Development Setup**: Local development configuration
- **Production Setup**: Secure production configuration
- **Multi-User Setup**: Team collaboration configuration

### VS Code Integration

Examples for VS Code + MCP integration:

- **Workspace Configuration**: Project-specific MCP server setup
- **Extension Development**: Custom VS Code extensions using MCP
- **Debugging Setup**: MCP server debugging in VS Code

## Running Examples

### Individual Examples

Run any example directly:
```bash
node examples/path/to/example.js
```

### Batch Execution

Run all basic examples:
```bash
npm run examples:basic
```

Run workshop scenarios:
```bash
npm run examples:workshops
```

### Example-Specific Scripts

Some examples include their own package.json with specific scripts:

```bash
cd examples/advanced/custom-server
npm install
npm run demo
```

## Error Handling

Common issues and solutions:

### Servers Not Running
```
❌ Error: Connection failed
💡 Make sure the MCP servers are running: npm run mcp:start
```

### Authentication Issues
```
❌ Error: Authentication failed
💡 Set required environment variables (GITHUB_TOKEN, etc.)
```

### Port Conflicts
```
❌ Error: Port already in use
💡 Check server status: npm run mcp:status
```

## Creating Your Own Examples

### Template Structure

```javascript
#!/usr/bin/env node

/**
 * Example: Your Example Name
 * 
 * Description of what this example demonstrates
 */

const http = require('http');

async function makeRequest(server, tool, args) {
  // Request implementation
}

async function main() {
  console.log('🚀 Your Example Name\n');
  
  try {
    // Your example code here
    console.log('🎉 Example completed!');
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
```

### Best Practices

1. **Include clear descriptions** of what the example demonstrates
2. **Handle errors gracefully** with helpful error messages
3. **Use console output** to show what's happening
4. **Include prerequisites** in comments
5. **Make examples self-contained** when possible

### Contributing Examples

When contributing new examples:

1. Follow the existing directory structure
2. Include comprehensive comments
3. Add the example to this README
4. Test with a clean environment
5. Include any required setup steps

## Next Steps

After running these examples:

1. **Explore the source code** to understand MCP server implementation
2. **Modify examples** to experiment with different parameters
3. **Create your own examples** for specific use cases
4. **Integrate MCP servers** into your own projects

For more advanced usage, see:
- [API Documentation](../docs/api/)
- [Custom Server Guide](../docs/guides/custom-servers.md)
- [Integration Patterns](../docs/guides/integration-patterns.md)