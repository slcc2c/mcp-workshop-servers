# Memory Segregation Guide

## Overview

The Memory MCP server provides persistent context across Claude sessions, but by default it stores all memories in a single global space. This guide explains our tagging strategy to segregate memories by project and session, preventing cross-project contamination.

## The Challenge

Without segregation:
- Memories from different projects mix together
- Context from one project can interfere with another
- Hard to find project-specific information
- No way to clean up old project data

## Our Solution: Consistent Tagging

Every memory is tagged with:
- `project:<name>` - Identifies the project
- `session:<date>` - Tracks when created (YYYY-MM-DD format)

## Implementation

### 1. Manual Tagging in Claude

When storing memories, always include project context:

```
"Remember for project:my-app: We use PostgreSQL 15 with TimescaleDB"
Tags: project:my-app, session:2025-06-28, database, architecture
```

### 2. Using the Memory Helper Script

The included `memory-helper.sh` script automates tagging:

```bash
# Set your project context
export MCP_PROJECT=my-app
export MCP_SESSION=2025-06-28

# Store memories with automatic tagging
./scripts/memory-helper.sh store "Database is PostgreSQL" architecture

# This automatically adds: project:my-app, session:2025-06-28
```

### 3. Searching Within Projects

Always scope searches to your project:

```
# In Claude
"What databases are used in project:my-app?"

# Using script
./scripts/memory-helper.sh search "database"
# Automatically filters by current MCP_PROJECT
```

## Best Practices

### Project Naming Convention
- Use kebab-case: `my-app`, `api-server`, `web-client`
- Be consistent across sessions
- Avoid spaces or special characters

### Session Management
- Use ISO date format: `2025-06-28`
- Start each work session with context:
  ```
  "Starting session for project:my-app on 2025-06-28"
  ```

### Memory Categories
Common tags to add alongside project/session:
- `architecture` - Design decisions
- `todo` - Tasks to complete
- `bug` - Known issues
- `preference` - User/team preferences
- `security` - Security decisions
- `config` - Configuration choices

## Example Workflows

### Starting a New Project

```bash
# Set up environment
export MCP_PROJECT=new-api
export MCP_SESSION=$(date +%Y-%m-%d)

# Create initial context
./scripts/memory-helper.sh context "Building REST API with FastAPI"

# In Claude
"Remember for project:new-api: Using Python 3.11 with FastAPI framework"
"Remember for project:new-api: PostgreSQL for main database, Redis for caching"
```

### Resuming Work

```bash
# Set project context
export MCP_PROJECT=my-app
export MCP_SESSION=$(date +%Y-%m-%d)

# Check what we know
./scripts/memory-helper.sh list

# In Claude
"What do we know about project:my-app?"
"Show all TODOs for project:my-app"
```

### Switching Projects

```bash
# Project A
export MCP_PROJECT=frontend
./scripts/memory-helper.sh list

# Project B
export MCP_PROJECT=backend
./scripts/memory-helper.sh list

# Memories are completely separate!
```

## Advanced Usage

### Linking Related Memories

When storing related information:
```
"Remember for project:my-app: Switched to JWT auth (relates to previous session auth discussion)"
```

### Archiving Old Projects

Periodically export project memories:
```
"Export all memories tagged with project:old-project"
```

Save the export before cleaning up.

### Team Collaboration

For shared projects, establish naming conventions:
```
project:team-projectname
session:2025-06-28-username
```

## Troubleshooting

### Memories Not Found
- Check your MCP_PROJECT environment variable
- Verify you're using consistent project names
- Include project tag in searches

### Cross-Project Contamination
- Always include project tags when storing
- Use the helper script for consistency
- Review memories without project tags and update them

### Performance Issues
- Archive old sessions periodically
- Use specific searches rather than listing all
- Consider separate Memory MCP instances for very large projects

## Integration Examples

### CI/CD Pipeline
```yaml
- name: Store deployment context
  run: |
    export MCP_PROJECT=${{ github.repository }}
    ./scripts/memory-helper.sh store "Deployed version ${{ github.sha }} to production" deployment
```

### Git Hooks
```bash
# .git/hooks/post-commit
export MCP_PROJECT=$(basename `git rev-parse --show-toplevel`)
./scripts/memory-helper.sh store "Committed: $(git log -1 --pretty=%B)" commit
```

## Limitations

1. **No Built-in Segregation**: This is a tagging convention, not enforced isolation
2. **Manual Discipline Required**: Forgetting tags causes contamination
3. **No Access Control**: Any session can read any project's memories
4. **Storage Limits**: All projects share the same memory.json file

## Future Enhancements

Consider these improvements:
- Automated tag injection via MCP wrapper
- Project-specific memory files
- Memory garbage collection by date
- Export/import tools for project archival

This segregation strategy provides practical project isolation while working within the Memory MCP server's current architecture.