# Database MCP Servers

This document describes the PostgreSQL and Redis MCP servers that enable database operations through the Model Context Protocol.

## PostgreSQL Server

The PostgreSQL server provides comprehensive database operations with connection pooling and transaction support.

### Features
- Connection pooling (up to 20 connections per database)
- Transaction support with automatic rollback on error
- Prepared statements for security
- Schema inspection and table management
- CRUD operations with builder patterns
- Database statistics and monitoring

### Available Tools

#### Query Operations
- `postgres_query` - Execute any SQL query with optional parameters
- `postgres_transaction` - Execute multiple queries in a transaction

#### Table Management
- `postgres_list_tables` - List all tables in a schema
- `postgres_table_info` - Get detailed column information
- `postgres_create_table` - Create new tables with column definitions

#### Data Operations
- `postgres_select` - Query data with filtering, ordering, and pagination
- `postgres_insert` - Insert data with optional RETURNING clause
- `postgres_update` - Update data with WHERE conditions
- `postgres_delete` - Delete data with WHERE conditions

#### Monitoring
- `postgres_stats` - Get database size, connections, and pool status

### Configuration

Set your PostgreSQL connection string in 1Password:
```bash
# Run the setup script
./scripts/add-database-connections.sh

# Or manually add to 1Password
op item create --category="Database" \
  --title="PostgreSQL Connection" \
  --vault="Server-Configurations" \
  notesPlain="postgresql://user:password@localhost:5432/mydb"
```

Environment variable:
```bash
POSTGRES_URL=1password:Server-Configurations/PostgreSQL Connection:notesPlain
```

### Usage Examples

#### Basic Query
```
Tool: postgres_query
Input: {
  "query": "SELECT * FROM users WHERE active = $1",
  "params": [true]
}
```

#### Transaction
```
Tool: postgres_transaction
Input: {
  "queries": [
    {"query": "INSERT INTO orders (user_id, total) VALUES ($1, $2)", "params": [123, 99.99]},
    {"query": "UPDATE users SET last_order = NOW() WHERE id = $1", "params": [123]}
  ]
}
```

#### Create Table
```
Tool: postgres_create_table
Input: {
  "table": "products",
  "columns": [
    {"name": "id", "type": "SERIAL", "primaryKey": true},
    {"name": "name", "type": "VARCHAR(255)", "nullable": false},
    {"name": "price", "type": "DECIMAL(10,2)", "nullable": false},
    {"name": "created_at", "type": "TIMESTAMP", "default": "NOW()"}
  ]
}
```

## Redis Server

The Redis server provides key-value operations with pub/sub support and advanced data structures.

### Features
- All Redis data types (strings, hashes, lists, sets, sorted sets)
- Pub/Sub messaging system
- Pipeline operations for batching
- TTL and expiration management
- Pattern-based key scanning
- Connection retry logic

### Available Tools

#### Basic Operations
- `redis_set` - Set key-value with optional TTL
- `redis_get` - Get value by key
- `redis_delete` - Delete keys
- `redis_exists` - Check key existence
- `redis_keys` - Find keys by pattern
- `redis_expire` - Set key expiration
- `redis_ttl` - Get remaining TTL

#### Hash Operations
- `redis_hset` - Set hash field value
- `redis_hget` - Get hash field or entire hash

#### List Operations
- `redis_list_push` - Push to list (left or right)
- `redis_list_range` - Get list elements in range

#### Set Operations
- `redis_set_add` - Add members to set
- `redis_set_members` - Get all set members
- `redis_set_operations` - Union, intersect, diff operations

#### Sorted Set Operations
- `redis_zadd` - Add members with scores
- `redis_zrange` - Get members by rank range

#### Pub/Sub
- `redis_publish` - Publish message to channel
- `redis_subscribe` - Subscribe and receive messages

#### Advanced
- `redis_pipeline` - Execute multiple commands atomically
- `redis_info` - Get server information

### Configuration

Set your Redis connection in 1Password:
```bash
# Run the setup script
./scripts/add-database-connections.sh

# Or manually add to 1Password
op item create --category="Database" \
  --title="Redis URL" \
  --vault="Server-Configurations" \
  notesPlain="redis://user:password@localhost:6379/0"
```

Environment variable:
```bash
REDIS_URL=1password:Server-Configurations/Redis URL:notesPlain
```

### Usage Examples

#### Set with TTL
```
Tool: redis_set
Input: {
  "key": "session:123",
  "value": "{\"user\": \"john\", \"role\": \"admin\"}",
  "ttl": 3600
}
```

#### Hash Operations
```
Tool: redis_hset
Input: {
  "key": "user:123",
  "field": "last_login",
  "value": "2025-06-28T10:30:00Z"
}
```

#### Pub/Sub
```
Tool: redis_publish
Input: {
  "channel": "notifications",
  "message": "{\"type\": \"alert\", \"text\": \"System update\"}"
}
```

#### Pipeline
```
Tool: redis_pipeline
Input: {
  "commands": [
    {"command": "set", "args": ["key1", "value1"]},
    {"command": "expire", "args": ["key1", 3600]},
    {"command": "hset", "args": ["hash1", "field1", "value1"]}
  ]
}
```

## Security Considerations

1. **Connection Strings**: Always store in 1Password, never in code
2. **SQL Injection**: Use parameterized queries (PostgreSQL)
3. **Access Control**: Configure database user permissions appropriately
4. **Network Security**: Use SSL/TLS connections in production
5. **Resource Limits**: Connection pools prevent resource exhaustion

## Troubleshooting

### PostgreSQL

**Connection Failed**
- Check connection string format
- Verify database server is running
- Check firewall/security group rules
- Verify user permissions

**Pool Exhausted**
- Increase pool size in server configuration
- Check for connection leaks
- Monitor long-running queries

### Redis

**Connection Refused**
- Verify Redis server is running
- Check bind address configuration
- Verify authentication credentials
- Check maxclients setting

**Pub/Sub Not Receiving**
- Ensure subscriber is active before publishing
- Check channel name spelling
- Verify no network issues

## Performance Tips

### PostgreSQL
- Use indexes for frequently queried columns
- Batch operations in transactions
- Use prepared statements for repeated queries
- Monitor slow queries with pg_stat_statements

### Redis
- Use pipelining for multiple operations
- Set appropriate TTLs to manage memory
- Use Redis data types appropriately
- Monitor memory usage with INFO command

## Next Steps

1. Add your database connections to 1Password
2. Test connectivity with basic operations
3. Build your application with database integration
4. Monitor performance and optimize as needed