# MCP Servers for CS Experimentation Workshop

> Achieve "5-minute magic" - go from concept to working experiment in under 5 minutes using AI-collaborative development with Model Context Protocol servers.

## Overview

This project implements a comprehensive Model Context Protocol (MCP) server ecosystem designed specifically for rapid CS experimentation. Built for Mac Studio M3 Ultra optimization, it provides seamless integration between AI assistants and development tools.

## Features

- **Sub-5-minute Setup**: From zero to fully configured development environment
- **Multi-Tier Architecture**: Essential, database, and AI collaboration servers
- **Docker Isolation**: Secure, containerized environments for each experiment
- **AI Memory**: Persistent context across sessions
- **Multi-Database Support**: PostgreSQL, Redis, MongoDB, Neo4j out of the box
- **GitHub Integration**: Automated repository management and CI/CD
- **TypeScript Build**: Clean compilation with full type safety ✅

## Quick Start

### Option 1: MCP Starter Kit (Recommended for New Users)

```bash
# Get the starter kit for a 5-minute setup
cd mcp-starter-kit/
./setup.sh

# Or with 1Password integration:
./setup-with-1password.sh

# Restart Claude Desktop and you're ready! 🚀
```

### Option 2: Full Workshop Setup

```bash
# Clone the repository
git clone https://github.com/slcc2c/mcp-workshop-servers.git
cd mcp-workshop-servers

# Install dependencies
npm install

# Set up 1Password integration (recommended)
./scripts/add-database-connections.sh

# Start all MCP servers
npm run mcp:start
```

📚 **[Read the Quick Start Guide](./docs/quick-start.md)** for detailed setup instructions.

## Attaching Your Project

### Quick Attach (2 minutes)

```bash
# Run the interactive attachment script
./scripts/attach-project.sh

# Follow the prompts to:
# 1. Select your project directory
# 2. Choose a project name
# 3. Configure filesystem + memory access

# Restart Claude Desktop and start coding!
```

📎 **[Read the Project Attachment Guide](./docs/attach-project-guide.md)** for detailed instructions and advanced configurations.

### Project Templates

Use our pre-configured templates for common project types:

- **Web App**: React + Node.js full-stack template
- **API**: RESTful API with authentication and docs
- **Data Science**: Python ML project with Jupyter
- **Mobile**: React Native cross-platform template

```bash
# View available templates
ls templates/

# Use a template
cp -r templates/web-app/* /path/to/your/project/
```

## Architecture

### Tier 1: Essential Foundation
- **GitHub Server**: Repository management, issue tracking, PR automation
- **Filesystem Server**: Secure file operations with configurable access
- **Docker Server**: Container management and isolated environments
- **Memory Server**: Persistent AI context and knowledge graphs

### Tier 2: Database & Services
- **PostgreSQL/Supabase**: Full database management with real-time features
- **Redis**: Caching, sessions, and real-time data structures
- **MongoDB**: Document store with Atlas integration
- **Neo4j**: Graph database for relationship-heavy experiments
- **Kubernetes**: Service orchestration and deployment

### Tier 3: AI Collaboration
- **Jupyter Integration**: Live notebook execution
- **FastMCP Framework**: Rapid tool creation
- **Code Analysis**: Automated documentation and insights

## Configuration

Configure Claude Desktop by adding to `claude_config.json`:

```json
{
  "mcpServers": {
    "mcp-workshop": {
      "command": "node",
      "args": ["/path/to/mcp-workshop-servers/dist/index.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}",
        "WORKSHOP_MODE": "true"
      }
    }
  }
}
```

## Documentation

- [MCP Starter Kit](mcp-starter-kit/README.md) - Quick 5-minute setup guide
- [Memory Segregation Guide](docs/memory-segregation.md) - Project isolation strategy
- [Architecture Guide](docs/architecture.md)
- [Server Setup](docs/setup.md)
- [API Reference](docs/api.md)
- [Workshop Examples](examples/README.md)

## Documentation

- 📖 **[Quick Start Guide](./docs/quick-start.md)** - Get up and running in 5 minutes
- 🔧 **[Server Reference](./docs/server-reference.md)** - Comprehensive guide to all MCP servers
- 💾 **[Database Servers](./docs/database-servers.md)** - PostgreSQL, Redis, MongoDB setup and usage
- 🧠 **[Memory Segregation](./docs/memory-segregation.md)** - Managing multiple projects with the Memory server
- 🔐 **[Secrets Management](./docs/guides/secrets-management.md)** - 1Password integration guide
- 📦 **[MCP Starter Kit](./mcp-starter-kit/README.md)** - Standalone package for easy distribution
- 🔨 **[TypeScript Patterns](./docs/typescript-patterns.md)** - Development patterns and best practices

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

Built on the Model Context Protocol by Anthropic, leveraging the vibrant MCP ecosystem and community servers.