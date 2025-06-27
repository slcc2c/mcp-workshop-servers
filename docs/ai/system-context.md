# System Context for AI Assistants

This document provides comprehensive context about the MCP Workshop Servers system to help AI assistants understand the architecture, make informed decisions, and provide accurate assistance.

## Project Overview

**MCP Workshop Servers** is a comprehensive Model Context Protocol implementation designed for rapid CS experimentation. The primary goal is achieving "5-minute magic" - enabling developers to go from concept to working experiment in under 5 minutes.

### Key Characteristics
- **Platform**: Optimized for Mac Studio M3 Ultra
- **Architecture**: Microservices using MCP protocol
- **Runtime**: Node.js 20.x on Apple Silicon
- **Deployment**: Local development with Docker containers
- **CI/CD**: Self-hosted GitHub runners

## System State

### Current Configuration
```yaml
environment: development
version: 1.0.0
platform:
  os: macOS
  architecture: arm64
  processor: Apple M3 Ultra
  memory: 192GB available
  
services:
  active:
    - mcp-gateway (port 3000)
    - github-server (port 3001)
    - filesystem-server (port 3002)
    - memory-server (port 3003)
    - docker-server (port 3004)
    
  planned:
    - postgresql-server
    - redis-server
    - mongodb-server
    - neo4j-server
    - kubernetes-server
```

## Common AI Tasks

### 1. Adding New Features
When asked to add features, consider:
- Check existing patterns in similar components
- Update both implementation and documentation
- Add appropriate tests
- Update cross-references if adding new components

### 2. Debugging Issues
For debugging requests:
- Check logs in `logs/` directory
- Verify service status with `npm run mcp:status`
- Check port availability and network connections
- Review recent changes in git history

### 3. Performance Optimization
When optimizing:
- Current target: <5 minute setup time
- Server startup: <30 seconds
- Operation latency: <200ms
- Memory usage: <2GB per server

## File Structure Context

### Source Code Organization
```
src/
├── core/           # Core MCP protocol implementation
├── gateway/        # Request routing and orchestration
├── servers/        # Individual MCP server implementations
├── utils/          # Shared utilities and helpers
└── types/          # TypeScript type definitions
```

### Documentation Organization
```
docs/
├── setup/          # Installation and configuration
├── api/            # API references
├── guides/         # How-to guides
├── troubleshooting/# Problem resolution
├── examples/       # Code samples
└── ai/            # AI-specific documentation
```

## Technology Stack

### Core Dependencies
- **MCP SDK**: `@modelcontextprotocol/sdk` - Protocol implementation
- **TypeScript**: Type safety and better IDE support
- **Node.js**: Runtime environment
- **Docker**: Container orchestration

### Development Tools
- **Vitest**: Testing framework
- **ESLint**: Code linting
- **Prettier**: Code formatting
- **tsx**: TypeScript execution

## Integration Points

### Claude Desktop
- Configuration: `~/Library/Application Support/Claude/claude_config.json`
- Communication: JSON-RPC over stdio
- Authentication: Token-based

### GitHub
- API: REST and GraphQL endpoints
- Authentication: Personal access tokens
- Webhooks: Repository events

### Docker
- API: Docker Engine API
- Socket: `/var/run/docker.sock`
- Resource limits: Configurable per container

## Security Context

### Access Control
- Path sandboxing for filesystem operations
- Token rotation for external services
- Container isolation for experiments
- Audit logging for all operations

### Sensitive Data
- Environment variables for secrets
- Never commit tokens or passwords
- Use `.env` files (git-ignored)

## Performance Targets

### Benchmarks
| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Setup time | <5 min | 4.2 min | ✅ |
| Server startup | <30s | 18s | ✅ |
| API latency | <200ms | 150ms | ✅ |
| Memory/server | <2GB | 1.5GB | ✅ |

## Common Patterns

### Adding a New MCP Server
1. Create directory: `servers/new-server/`
2. Implement MCP protocol interface
3. Add to gateway routing
4. Create documentation
5. Add tests
6. Update cross-references

### Modifying Existing Features
1. Locate component using cross-references
2. Check for dependent components
3. Update implementation
4. Update tests
5. Update documentation
6. Run integration tests

## Error Handling Patterns

### Standard Error Response
```typescript
{
  error: {
    code: "ERROR_CODE",
    message: "Human-readable message",
    details: { /* additional context */ }
  }
}
```

### Logging Patterns
```typescript
logger.error('Operation failed', {
  operation: 'createRepository',
  user: userId,
  error: error.message,
  stack: error.stack
});
```

## Testing Strategy

### Test Types
- **Unit Tests**: Individual function testing
- **Integration Tests**: Server communication testing
- **E2E Tests**: Complete workflow testing
- **Performance Tests**: Benchmark verification

### Test Locations
- Unit: `tests/unit/`
- Integration: `tests/integration/`
- E2E: `tests/e2e/`

## Deployment Context

### Local Development
- All services run as Node.js processes
- Databases in Docker containers
- Hot reloading enabled
- Debug logging active

### Production (Future)
- Kubernetes orchestration
- Horizontal scaling
- Centralized logging
- Monitoring and alerting

## Helpful Commands

### Development
```bash
npm run dev              # Start in development mode
npm test                # Run all tests
npm run mcp:status      # Check server status
npm run mcp:logs        # View server logs
```

### Debugging
```bash
lsof -i :3000-3010      # Check port usage
ps aux | grep node      # Find Node processes
docker ps               # List running containers
```

### Git Operations
```bash
git status              # Check changes
git log --oneline -10   # Recent commits
git diff                # View changes
```

## When to Escalate

Ask the user for clarification when:
- Architectural decisions needed
- Breaking changes considered
- Security implications unclear
- Performance targets changed
- External service integration required

## Resource Limits

Be aware of:
- Mac Studio memory: 192GB total
- Docker memory limit: 2GB per container
- CPU cores: 24 performance, 8 efficiency
- Disk space: Monitor availability
- Network: Local development only

This context should help you assist effectively with the MCP Workshop Servers project. Always prioritize the "5-minute magic" goal and maintain compatibility with the existing architecture.