# MCP Servers Quick Start Guide

Get up and running with MCP servers in under 5 minutes!

## Prerequisites

- Node.js 18+ installed
- 1Password CLI (optional but recommended)
- Docker Desktop (for Docker server)
- Database installations (PostgreSQL, Redis, MongoDB) or Docker

## 1. Installation

```bash
# Clone the repository
git clone https://github.com/your-org/mcp-server.git
cd mcp-server

# Install dependencies
npm install

# Set up 1Password (recommended)
brew install 1password-cli  # macOS
# or download from https://1password.com/downloads/command-line/
```

## 2. Quick Setup Options

### Option A: Basic Setup (No Secrets Management)

```bash
# Copy example environment
cp .env.example .env

# Edit .env with your values
nano .env

# Start servers
npm run mcp:start
```

### Option B: Secure Setup with 1Password (Recommended)

```bash
# Run the MCP Starter Kit setup
cd mcp-starter-kit
./setup-with-1password.sh

# Follow the prompts to:
# 1. Configure 1Password vaults
# 2. Add API keys
# 3. Set up Claude Desktop
```

## 3. Adding Database Connections

```bash
# Add your database connection strings to 1Password
./scripts/add-database-connections.sh

# Example inputs:
# PostgreSQL: postgresql://user:password@localhost:5432/mydb
# Redis: redis://localhost:6379
# MongoDB: mongodb://localhost:27017/mydb
```

## 4. Configure Claude Desktop

The setup script automatically configures Claude Desktop. To verify:

```bash
# Check configuration
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Restart Claude Desktop
# Quit and reopen the Claude app
```

## 5. Test Your Setup

### In Claude Desktop

Ask Claude to use the MCP servers:

```
"List my GitHub repositories"
"Create a file called test.txt with 'Hello, MCP!'"
"Remember for project:mcp-test: Setup completed successfully"
```

### Using Individual Servers

#### PostgreSQL
```
"Create a PostgreSQL table called users with id, name, and email"
"Insert a user: John Doe, john@example.com"
"Show all users in the database"
```

#### Redis
```
"Set Redis key 'app:version' to '1.0.0'"
"Get the value of 'app:version' from Redis"
"Publish 'Hello subscribers!' to channel 'notifications'"
```

#### MongoDB
```
"Create a MongoDB collection called products"
"Insert a product: {name: 'Widget', price: 29.99, stock: 100}"
"Find all products with price less than 50"
```

#### Kubernetes
```
"Show Kubernetes cluster info"
"List all pods in the default namespace"
"Create a deployment: nginx with 3 replicas"
```

## 6. Common Workflows

### Development Workflow
```bash
# 1. Start servers for development
export MCP_PROJECT=my-app
npm run mcp:start -- --servers filesystem,memory,github

# 2. Use in Claude
"Remember for project:my-app: Starting new feature development"
"Create a new branch called feature/user-auth"
"Create initial auth module structure"
```

### Database Development
```bash
# 1. Start database servers
npm run mcp:start -- --servers postgresql,redis

# 2. Use in Claude
"Create database schema for a blog application"
"Implement caching layer with Redis"
```

### Container Management
```bash
# 1. Start container servers
npm run mcp:start -- --servers docker,kubernetes

# 2. Use in Claude
"Build a Docker image from the current directory"
"Deploy the image to Kubernetes with 2 replicas"
```

## 7. Project Organization

### Quick Project Attachment (NEW!)

```bash
# Use the interactive script to attach your project
./scripts/attach-project.sh

# This will:
# 1. Configure filesystem access to your project
# 2. Set up memory segregation
# 3. Create project-specific configuration
# 4. Update Claude Desktop config automatically
```

### Manual Project Setup

Use memory segregation for multiple projects:

```bash
# Set project context
export MCP_PROJECT=project-a
export MCP_SESSION=$(date +%Y-%m-%d)

# In Claude
"Remember for project:project-a: Using React with TypeScript"
"What do we know about project:project-a?"
```

### Using Project Templates

```bash
# Copy a template to your project
cp -r templates/web-app/* /path/to/your/project/

# Run the attachment script
./scripts/attach-project.sh
```

See the [Project Attachment Guide](./attach-project-guide.md) for detailed instructions.

## 8. Troubleshooting

### Servers Won't Start
```bash
# Check logs
npm run mcp:logs

# Verify environment
npm run mcp:status

# Test individual server
LOG_LEVEL=debug npm run mcp:start -- --server postgresql
```

### Connection Issues
```bash
# Test 1Password
op vault list

# Test database connections
psql $POSTGRES_URL -c "SELECT 1"
redis-cli ping
mongosh $MONGODB_URL --eval "db.stats()"
```

### Claude Desktop Issues
```bash
# Validate configuration
./scripts/validate-claude-desktop.sh

# Restart MCP servers
npm run mcp:stop
npm run mcp:start
```

## 9. Best Practices

1. **Always Use Project Tags**: Segregate memories by project
   ```
   "Remember for project:app-name: Design decision"
   ```

2. **Store Secrets in 1Password**: Never hardcode credentials
   ```bash
   GITHUB_TOKEN=1password:AI/GitHub Token:notesPlain
   ```

3. **Monitor Resource Usage**: Check server stats regularly
   ```
   "Show PostgreSQL connection pool status"
   "Get Redis memory info"
   ```

4. **Use Transactions**: For critical database operations
   ```
   "Execute PostgreSQL transaction: transfer funds between accounts"
   ```

5. **Implement Proper Error Handling**: Check operation results
   ```
   "Try to create user, handle if email already exists"
   ```

## 10. Next Steps

1. **Explore Advanced Features**:
   - Read [Database Servers Guide](./database-servers.md)
   - Check [Server Reference](./server-reference.md)
   - Review [Memory Segregation](./memory-segregation.md)

2. **Customize Your Setup**:
   - Enable/disable servers in config
   - Add custom environment variables
   - Create project-specific scripts

3. **Contribute**:
   - Report issues on GitHub
   - Submit pull requests
   - Share your workflows

## Quick Reference Card

```bash
# Start all servers
npm run mcp:start

# Start specific servers
npm run mcp:start -- --servers postgres,redis

# Stop all servers
npm run mcp:stop

# Check status
npm run mcp:status

# View logs
npm run mcp:logs

# Add database connection
./scripts/add-database-connections.sh

# Refresh tokens from 1Password
./scripts/refresh-tokens.sh
```

## Example: 5-Minute Blog Setup

```bash
# 1. Start servers (30 seconds)
npm run mcp:start -- --servers postgresql,redis,filesystem

# 2. In Claude (4.5 minutes)
"Create PostgreSQL schema for a blog with users, posts, and comments"
"Add indexes for performance"
"Set up Redis caching for popular posts"
"Create example blog post API endpoints in api/posts.js"
"Write tests for the post creation endpoint"

# Done! You have a working blog backend with caching
```

Remember: The goal is "5-minute magic" - from idea to working code!