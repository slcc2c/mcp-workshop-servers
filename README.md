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

## Quick Start

```bash
# Clone the repository
git clone https://github.com/slcc2c/mcp-workshop-servers.git
cd mcp-workshop-servers

# Install dependencies
npm install

# (Optional) Set up self-hosted GitHub runner for Mac Studio
./scripts/setup-runner.sh

# Start all MCP servers
npm run mcp:start

# Your environment is ready! 🚀
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

- [Architecture Guide](docs/architecture.md)
- [Server Setup](docs/setup.md)
- [API Reference](docs/api.md)
- [Workshop Examples](examples/README.md)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

Built on the Model Context Protocol by Anthropic, leveraging the vibrant MCP ecosystem and community servers.