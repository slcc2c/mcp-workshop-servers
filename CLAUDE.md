# MCP Servers for CS Experimentation Workshop

## Project Overview
This project implements a comprehensive Model Context Protocol (MCP) server ecosystem for rapid CS experimentation. The goal is to achieve "5-minute magic" - enabling developers to go from concept to working experiment in under 5 minutes using AI-collaborative development.

## Quick Start: Connect AI Clients
- **Claude Desktop**: Copy `claude-desktop-config.json` to Claude's config directory
- **Cursor IDE**: Use `cursor-mcp-config.json` with your `MCP_CURSOR_AUTH_TOKEN`
- **OpenAI**: Use `openai-functions.json` for function calling
- See [Quick Setup Guide](docs/quick-setup-clients.md) or [Full Documentation](docs/client-connections.md)

## Architecture
- **Tier 1**: Essential foundation servers (GitHub, filesystem, Docker, memory)
- **Tier 2**: Database and service management (PostgreSQL, Redis, MongoDB, Neo4j, Kubernetes)
- **Tier 3**: AI collaboration and rapid prototyping tools

## Key Commands

### Development
```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Run tests
npm test

# Lint code
npm run lint

# Type check
npm run typecheck

# Build project (TypeScript compilation - now clean!)
npm run build
```

### Docker
```bash
# Build Docker image
docker build -t mcp-workshop .

# Run container
docker run -d -p 3000:3000 mcp-workshop

# Docker compose up
docker-compose up -d
```

### MCP Server Management
```bash
# Start all MCP servers
npm run mcp:start

# Stop all MCP servers
npm run mcp:stop

# Check MCP server status
npm run mcp:status

# Install a specific MCP server
npm run mcp:install <server-name>
```

## Project Structure
```
mcp-server/
├── servers/           # Individual MCP server implementations
│   ├── github/       # GitHub integration server
│   ├── filesystem/   # File operations server
│   ├── docker/       # Docker management server
│   └── memory/       # Persistent context server
├── docs/             # Documentation
├── scripts/          # Build and deployment scripts
├── config/           # Configuration files
└── examples/         # Example implementations
```

## Key Features
- Sub-5-minute project setup
- Comprehensive GitHub integration
- Multi-database support
- Docker-based isolation
- AI memory and context persistence
- Mac Studio M3 Ultra optimized

## Testing Strategy
- Unit tests for individual servers
- Integration tests for server communication
- End-to-end workshop scenario tests
- Performance benchmarks for 5-minute target

## Deployment
- Docker containers for each server
- Kubernetes orchestration for production
- One-click deployment scripts
- Automatic health monitoring

## Security
- OAuth 2.1 authentication
- Container isolation (2GB RAM limits)
- Configurable access controls
- Comprehensive audit logging

## Recent Improvements (2025-06-29)
- Fixed all TypeScript compilation errors (400+ → 0)
- Improved type safety across all servers
- Enhanced build reliability
- See [TypeScript Patterns](docs/typescript-patterns.md) for development guidelines