# MCP Starter Kit - Quick Reference

## Essential Commands

### In Terminal

```bash
# Set project context
export MCP_PROJECT=my-app
export MCP_SESSION=$(date +%Y-%m-%d)

# Store memories
./scripts/memory-helper.sh store "Uses PostgreSQL" database
./scripts/memory-helper.sh store "React with TypeScript" frontend

# Search memories
./scripts/memory-helper.sh search "database"
./scripts/memory-helper.sh list

# Create session context
./scripts/memory-helper.sh context "Working on auth feature"
```

### In Claude Desktop

```
# GitHub Operations
"List my GitHub repositories"
"Create issue in [repo]: [title]"
"Show recent PRs in [repo]"
"Search for issues mentioning [keyword]"

# File Operations
"Read the package.json file"
"Search for files containing TODO"
"List all TypeScript files"
"Create a new file called config.js with [content]"

# Memory Operations
"Remember for project:my-app: Uses React 18"
"What do you know about project:my-app?"
"Show all TODOs for project:my-app"
"List architecture decisions for project:my-app"
```

## Project Context Pattern

Always include project context when storing memories:

```
"Remember for project:PROJECT_NAME: INFORMATION"
```

## Common Workflows

### Start of Day
```bash
export MCP_PROJECT=my-app
export MCP_SESSION=$(date +%Y-%m-%d)
./scripts/memory-helper.sh list
```

Then in Claude:
```
"What's the status of project:my-app?"
"Show all TODOs for project:my-app"
```

### During Development
```
"Remember for project:my-app: Decided to use JWT for auth"
"Remember for project:my-app: TODO: Add password reset flow"
"Remember for project:my-app: BUG: Login fails with special characters"
```

### End of Day
```
"Summarize today's work on project:my-app"
"List all new decisions for project:my-app from session:2025-06-28"
```

## Memory Tags Reference

### Required Tags (automatic with script)
- `project:name` - Project identifier
- `session:YYYY-MM-DD` - Date created

### Common Additional Tags
- `architecture` - Design decisions
- `todo` - Tasks to complete
- `bug` - Known issues
- `preference` - User/team preferences
- `security` - Security decisions
- `config` - Configuration
- `api` - API design
- `database` - Database schema
- `frontend` - UI/UX decisions
- `backend` - Server decisions
- `infrastructure` - Deployment/hosting
- `testing` - Test strategy
- `performance` - Optimization notes

## Troubleshooting Commands

```bash
# Validate configuration
./scripts/validate-config.sh

# Test GitHub connection
./scripts/test-github.sh

# Check current context
echo "Project: $MCP_PROJECT"
echo "Session: $MCP_SESSION"

# View Claude logs (macOS)
tail -f ~/Library/Logs/Claude/claude.log
```

## Environment Variables

```bash
# Required for memory segregation
export MCP_PROJECT=your-project-name
export MCP_SESSION=$(date +%Y-%m-%d)  # Auto-set to today

# Optional
export MCP_DEFAULT_TYPE=context        # Default memory type
export MCP_AUTO_TAG=true              # Future feature
```

## File Paths

### Config Locations
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Memory Storage
- **macOS**: `~/Library/Application Support/memory-mcp/memory.json`
- **Windows**: `%APPDATA%\memory-mcp\memory.json`
- **Linux**: `~/.config/memory-mcp/memory.json`

## Best Practices Checklist

- [ ] Always set MCP_PROJECT before starting work
- [ ] Use consistent project names (kebab-case)
- [ ] Tag memories with appropriate categories
- [ ] Search within project scope
- [ ] Create session context at start
- [ ] Summarize at end of session
- [ ] Rotate GitHub tokens every 90 days
- [ ] Back up memory.json periodically

## Quick Wins

1. **Auto-complete past decisions**: "What did we decide about authentication in project:my-app?"
2. **Track TODOs**: "Show all open TODOs for project:my-app"
3. **Remember context between sessions**: "What were we working on last time in project:my-app?"
4. **Quick architecture review**: "Describe the architecture of project:my-app"
5. **Bug tracking**: "List all known bugs in project:my-app"

---
Keep this reference handy for quick lookups!