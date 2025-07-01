# Memory MCP Segregation Strategy

## Overview
Since the Memory MCP server doesn't have built-in project/session segregation, we use a consistent tagging convention to organize memories by project and session.

## Tagging Convention

### Required Tags
Every memory entry should include:
- `project:<project-name>` - Identifies the project
- `session:<date>` - Identifies the work session (YYYY-MM-DD format)

### Example Tags
```
["project:mcp-server", "session:2025-06-28", "setup", "1password"]
```

## Usage in Claude

### Storing Memories with Project Context
```
// Store a fact about the project
"Remember: This project uses TypeScript and 1Password for secrets"
Tags: project:mcp-server, session:2025-06-28, architecture

// Store a preference
"Remember my preference: Always use environment variables for configuration"  
Tags: project:mcp-server, session:2025-06-28, preference, config

// Store context about current work
"Remember: We implemented vault scoping for security"
Tags: project:mcp-server, session:2025-06-28, security, implementation
```

### Searching Project-Specific Memories
```
// Search all memories for current project
"What do you know about project:mcp-server?"

// Search specific topics within project
"Search for security decisions in project:mcp-server"

// List all preferences for the project
"Show all preferences tagged with project:mcp-server"
```

### Creating Session Context
At the start of each session:
```
"Remember session context: Working on MCP server Docker integration"
Tags: project:mcp-server, session:2025-06-28, session-start, context
```

## Helper Script Usage

```bash
# Set project for current terminal session
export MCP_PROJECT=mcp-server
export MCP_SESSION=2025-06-28

# Store a memory
./scripts/memory-helper.sh store "User prefers TypeScript" preference "language"

# Search project memories
./scripts/memory-helper.sh search "typescript"

# List all project memories
./scripts/memory-helper.sh list

# Create session context
./scripts/memory-helper.sh context "Working on Docker integration"

# Show current configuration
./scripts/memory-helper.sh config
```

## Best Practices

### 1. Always Include Project Tags
Never store memories without project tags to avoid cross-project contamination.

### 2. Use Consistent Project Names
- Use kebab-case: `mcp-server`, `web-app`, `api-backend`
- Avoid spaces or special characters

### 3. Session Tags for Temporal Context
- Use ISO date format: `2025-06-28`
- Helps track when decisions were made
- Useful for reviewing progress over time

### 4. Additional Categorization
Common additional tags:
- `architecture` - Design decisions
- `security` - Security-related choices
- `todo` - Future tasks
- `bug` - Known issues
- `preference` - User preferences
- `config` - Configuration decisions
- `implementation` - Code implementation details

### 5. Relationship Connections
Link related memories:
```
// When storing related memories
"This security decision relates to the vault-scoping memory"
```

## Example Workflow

### Starting a New Project
```bash
export MCP_PROJECT=new-api
export MCP_SESSION=$(date +%Y-%m-%d)

# In Claude:
"Remember: Starting new API project using FastAPI and PostgreSQL"
Tags: project:new-api, session:2025-06-28, architecture, start
```

### Continuing Existing Project
```bash
export MCP_PROJECT=mcp-server
export MCP_SESSION=$(date +%Y-%m-%d)

# In Claude:
"What do we know about project:mcp-server?"
"Show all TODOs for project:mcp-server"
```

### Switching Between Projects
```bash
# Project A
export MCP_PROJECT=web-frontend
./scripts/memory-helper.sh list

# Project B  
export MCP_PROJECT=mobile-app
./scripts/memory-helper.sh list
```

## Limitations and Workarounds

### Limitation: Global Storage
All projects share the same memory.json file.

**Workaround**: Always filter by project tag when searching.

### Limitation: No Access Control
Any session can read any project's memories.

**Workaround**: This is acceptable for single-user development. For teams, run separate Memory MCP instances.

### Limitation: No Automatic Cleanup
Old session data accumulates over time.

**Workaround**: Periodically export and archive old sessions:
```
"Export all memories for project:old-project"
```

## Integration with Claude

When using Claude with the Memory MCP server:

1. **Start of session**: State your project and session
   ```
   "I'm working on project:mcp-server for session:2025-06-28"
   ```

2. **Store with context**: Always mention the project
   ```
   "Remember for project:mcp-server: We use 1Password for secrets"
   ```

3. **Search with scope**: Include project in searches
   ```
   "What does project:mcp-server use for authentication?"
   ```

This strategy provides practical project segregation while working within the Memory MCP server's current limitations.