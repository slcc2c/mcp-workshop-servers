# MCP Server Reference

This document provides a comprehensive reference for all implemented MCP servers in the project.

## Overview

The MCP Workshop Servers project implements a three-tier architecture:

1. **Tier 1 - Essential Foundation**: Core servers for basic operations
2. **Tier 2 - Database & Services**: Database and caching servers
3. **Tier 3 - Advanced Tools**: Specialized servers for production deployment

## Tier 1: Essential Foundation Servers

### GitHub Server
**Purpose**: Source code management and collaboration
**Package**: `@modelcontextprotocol/server-github`
**Status**: External (npm package)

**Key Features**:
- Repository management
- Issue and PR operations
- Code search
- Commit history
- Release management

**Configuration**:
```bash
GITHUB_TOKEN=1password:AI/GitHub Token:notesPlain
```

### Filesystem Server
**Purpose**: Local file system operations
**Status**: Implemented

**Key Features**:
- Sandboxed file access
- Read/write operations
- Directory management
- File watching
- Pattern matching

**Tools**: 15+
- `fs_read_file`
- `fs_write_file`
- `fs_list_directory`
- `fs_create_directory`
- `fs_delete`
- `fs_move`
- `fs_search`
- `fs_watch`

### Memory Server
**Purpose**: Persistent context and knowledge management
**Status**: Implemented

**Key Features**:
- In-memory knowledge graph
- Project/session segregation via tags
- Relationship management
- JSON persistence
- Search and filtering

**Tools**: 10+
- `memory_store`
- `memory_search`
- `memory_get`
- `memory_update`
- `memory_delete`
- `memory_list_tags`
- `memory_get_related`
- `memory_export`

### Docker Server
**Purpose**: Container management and deployment
**Status**: Implemented

**Key Features**:
- Container lifecycle management
- Image operations
- Network and volume management
- Resource limits (2GB RAM default)
- Container statistics

**Tools**: 20+
- `docker_create_container`
- `docker_start_container`
- `docker_stop_container`
- `docker_list_containers`
- `docker_container_logs`
- `docker_pull_image`
- `docker_build_image`
- `docker_create_network`

## Tier 2: Database & Service Servers

### PostgreSQL Server
**Purpose**: Relational database operations
**Status**: Implemented

**Key Features**:
- Connection pooling (20 connections max)
- Transaction support
- Schema management
- Prepared statements
- Query builder operations

**Tools**: 11
- `postgres_query`
- `postgres_transaction`
- `postgres_list_tables`
- `postgres_table_info`
- `postgres_create_table`
- `postgres_select`
- `postgres_insert`
- `postgres_update`
- `postgres_delete`
- `postgres_stats`

**Configuration**:
```bash
POSTGRES_URL=1password:Server-Configurations/PostgreSQL Connection:notesPlain
```

### Redis Server
**Purpose**: In-memory data store and caching
**Status**: Implemented

**Key Features**:
- All data types support
- Pub/Sub messaging
- Pipeline operations
- TTL management
- Pattern scanning

**Tools**: 20+
- `redis_set` / `redis_get`
- `redis_hset` / `redis_hget`
- `redis_list_push` / `redis_list_range`
- `redis_set_add` / `redis_set_members`
- `redis_zadd` / `redis_zrange`
- `redis_publish` / `redis_subscribe`
- `redis_pipeline`
- `redis_expire` / `redis_ttl`

**Configuration**:
```bash
REDIS_URL=1password:Server-Configurations/Redis URL:notesPlain
```

### MongoDB Server
**Purpose**: NoSQL document database
**Status**: Implemented

**Key Features**:
- Flexible schema
- Aggregation pipelines
- Index management
- ObjectId handling
- Collection operations

**Tools**: 18
- `mongodb_find` / `mongodb_find_one`
- `mongodb_insert_one` / `mongodb_insert_many`
- `mongodb_update_one` / `mongodb_update_many`
- `mongodb_delete_one` / `mongodb_delete_many`
- `mongodb_aggregate`
- `mongodb_create_index`
- `mongodb_list_collections`
- `mongodb_create_collection`
- `mongodb_count`
- `mongodb_distinct`

**Configuration**:
```bash
MONGODB_URL=1password:Server-Configurations/MongoDB Connection:notesPlain
```

## Tier 3: Advanced Tool Servers

### Kubernetes Server
**Purpose**: Container orchestration for production
**Status**: Implemented

**Key Features**:
- Multi-namespace support
- Deployment management
- Service discovery
- ConfigMap/Secret management
- Job scheduling
- Pod logs and events

**Tools**: 20+
- `k8s_list_namespaces` / `k8s_create_namespace`
- `k8s_list_pods` / `k8s_create_pod`
- `k8s_list_deployments` / `k8s_create_deployment`
- `k8s_scale_deployment`
- `k8s_create_service`
- `k8s_create_configmap`
- `k8s_create_secret`
- `k8s_create_job`
- `k8s_get_logs`
- `k8s_get_events`
- `k8s_cluster_info`

**Configuration**:
```bash
KUBECONFIG=/path/to/kubeconfig  # Optional, uses default if not set
```

### Neo4j Server
**Purpose**: Graph database operations
**Status**: Implemented

**Key Features**:
- Full Cypher query support
- Node and relationship CRUD
- Shortest path algorithms
- Schema management (indexes, constraints)
- Graph algorithms (PageRank, community detection)
- Database statistics

**Tools**: 13
- `neo4j_query`
- `neo4j_create_node` / `neo4j_update_node` / `neo4j_delete_node`
- `neo4j_create_relationship`
- `neo4j_find_nodes` / `neo4j_find_path`
- `neo4j_create_index` / `neo4j_create_constraint`
- `neo4j_schema` / `neo4j_stats`
- `neo4j_algorithm`

**Configuration**:
```bash
NEO4J_URL=1password:Server-Configurations/Neo4j Connection:notesPlain
NEO4J_USER=1password:Server-Configurations/Neo4j User:notesPlain
NEO4J_PASSWORD=1password:Server-Configurations/Neo4j Password:notesPlain
```

### Jupyter Server
**Purpose**: Data science and notebook execution
**Status**: Implemented

**Key Features**:
- Notebook creation and management
- Cell execution (code and markdown)
- Variable inspection
- Plot generation with matplotlib
- Multiple kernel support
- Export to HTML, PDF, Markdown, Python
- Session management

**Tools**: 11
- `jupyter_create_notebook` / `jupyter_open_notebook`
- `jupyter_execute_cell` / `jupyter_execute_notebook`
- `jupyter_get_variable`
- `jupyter_plot`
- `jupyter_list_kernels` / `jupyter_kernel_control`
- `jupyter_save_notebook` / `jupyter_export`
- `jupyter_list_sessions`

**Configuration**:
```bash
JUPYTER_PORT=8888
JUPYTER_TOKEN=1password:Server-Configurations/Jupyter Token:notesPlain
```

### XcodeBuildMCP Server
**Purpose**: iOS/macOS development and Xcode project management
**Status**: Implemented
**Platform**: macOS only

**Key Features**:
- Xcode project and workspace management
- Swift package dependency operations
- iOS simulator control and management
- Physical device detection and management
- App installation and launching
- Build configuration and scheme management
- Code signing and provisioning profile handling

**Tools**: 25+

**Xcode Project Management**:
- `xcode_list_projects` - List all Xcode projects in a directory
- `xcode_project_info` - Get detailed project information
- `xcode_list_targets` - List all targets in a project
- `xcode_list_schemes` - List available schemes
- `xcode_list_configurations` - List build configurations

**Swift Package Operations**:
- `swift_package_init` - Initialize a new Swift package
- `swift_package_add_dependency` - Add a package dependency
- `swift_package_remove_dependency` - Remove a package dependency
- `swift_package_update` - Update package dependencies
- `swift_package_resolve` - Resolve package dependencies
- `swift_package_list_dependencies` - List current dependencies

**iOS Simulator Control**:
- `simulator_list` - List all available simulators
- `simulator_create` - Create a new simulator
- `simulator_delete` - Delete a simulator
- `simulator_boot` - Boot a simulator
- `simulator_shutdown` - Shutdown a simulator
- `simulator_install_app` - Install an app on simulator
- `simulator_launch_app` - Launch an app on simulator
- `simulator_uninstall_app` - Uninstall an app from simulator

**Physical Device Management**:
- `device_list` - List connected physical devices
- `device_info` - Get detailed device information
- `device_install_app` - Install app on physical device
- `device_launch_app` - Launch app on physical device

**App Utilities**:
- `app_info` - Get app bundle information
- `codesign_verify` - Verify code signing status

**Configuration**:
```bash
# XcodeBuildMCP uses system Xcode installation
# Ensure Xcode Command Line Tools are installed:
# xcode-select --install

# For physical device operations, ensure proper provisioning profiles
# are installed in Xcode
```

**Requirements**:
- macOS 12.0 or later
- Xcode 14.0 or later
- Xcode Command Line Tools
- Valid Apple Developer account (for device deployment)

**Example Usage**:

```typescript
// List all iOS simulators
await xcode.simulator_list();

// Create a new iPhone 15 Pro simulator
await xcode.simulator_create({
  name: "iPhone 15 Pro Test",
  deviceType: "iPhone 15 Pro",
  runtime: "iOS 17.0"
});

// Build and install app on simulator
await xcode.simulator_install_app({
  simulatorId: "ABCD-1234",
  appPath: "/path/to/MyApp.app"
});

// Add a Swift package dependency
await xcode.swift_package_add_dependency({
  projectPath: "/path/to/MyProject",
  url: "https://github.com/Alamofire/Alamofire.git",
  version: "5.8.0"
});
```

## Server Management

### Starting Servers

1. **Individual Server**:
   ```bash
   npm run mcp:start -- --server postgres
   ```

2. **Multiple Servers**:
   ```bash
   npm run mcp:start -- --servers postgres,redis,mongodb
   ```

3. **All Enabled Servers**:
   ```bash
   npm run mcp:start
   ```

### Configuration

Servers are configured in `/src/types/config.ts`:

```typescript
servers: {
  github: {
    enabled: true,
    autoStart: true,
    // ...
  },
  postgresql: {
    enabled: false,  // Enable as needed
    autoStart: false,
    // ...
  }
}
```

### Environment Variables

All sensitive configuration uses 1Password references:

```bash
# Database connections
POSTGRES_URL=1password:Server-Configurations/PostgreSQL Connection:notesPlain
REDIS_URL=1password:Server-Configurations/Redis URL:notesPlain
MONGODB_URL=1password:Server-Configurations/MongoDB Connection:notesPlain

# API Keys
GITHUB_TOKEN=1password:AI/GitHub Token:notesPlain
OPENAI_API_KEY=1password:AI/OpenAI API Key:notesPlain
```

## Security Considerations

1. **Credential Management**: All secrets stored in 1Password
2. **Connection Pooling**: Prevents resource exhaustion
3. **Input Validation**: Zod schemas for all inputs
4. **Error Handling**: Sanitized error messages
5. **Resource Limits**: Docker containers limited to 2GB RAM
6. **Path Sandboxing**: Filesystem access restricted

## Performance Optimization

1. **Connection Pooling**: PostgreSQL (20), MongoDB (10)
2. **Caching**: Secrets cached for 5 minutes
3. **Batch Operations**: Pipeline support in Redis
4. **Lazy Loading**: Servers loaded on demand
5. **Auto-restart**: Failed servers retry with backoff

## Monitoring

Each server provides:
- Initialization logs
- Operation metrics
- Error tracking
- Connection status
- Resource usage (where applicable)

## Troubleshooting

### Common Issues

1. **Connection Failed**:
   - Check environment variables
   - Verify 1Password access
   - Test network connectivity

2. **Permission Denied**:
   - Check filesystem permissions
   - Verify Docker socket access
   - Review Kubernetes RBAC

3. **Resource Exhausted**:
   - Monitor connection pools
   - Check memory limits
   - Review query patterns

### Debug Mode

Enable debug logging:
```bash
LOG_LEVEL=debug npm run mcp:start
```

## Best Practices

1. **Use Connection Strings**: Store in 1Password
2. **Implement Retries**: Handle transient failures
3. **Monitor Resources**: Track pool usage
4. **Validate Input**: Use schema validation
5. **Handle Errors**: Provide meaningful feedback
6. **Document Tools**: Clear descriptions and examples
7. **Test Integration**: Verify cross-server communication

## Future Enhancements

1. **Additional Servers**:
   - Elasticsearch for search
   - RabbitMQ for messaging
   - Prometheus for metrics

2. **Features**:
   - Multi-tenancy support
   - Rate limiting per server
   - Webhook integration
   - GraphQL support

3. **Operations**:
   - Automated backups
   - Disaster recovery
   - Performance profiling
   - A/B testing support