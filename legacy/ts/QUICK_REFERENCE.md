# MCP Servers Quick Reference

## 🔑 1Password Vaults
- **AI**: API keys and tokens
- **Server-Configurations**: Infrastructure settings

## 🚀 Available MCP Servers

### GitHub (`slcc2c`)
```bash
# Token from: 1password:AI/GitHub Token:notesPlain
# Operations: repos, issues, PRs, commits, search
# Rate limit: 5000/hour
```

### Filesystem
```bash
# Root: /Users/spencer/repos
# Operations: read, write, search, watch
# Sandboxed for security
```

### Memory
```bash
# Operations: store, retrieve, search, relate
# Perfect for: context, todos, knowledge graph
```

### Docker
```bash
# Operations: containers, images, volumes, networks
# Status: Ready (if Docker Desktop running)
```

## 📝 Common Commands in Claude

### GitHub
- "List my repositories"
- "Show recent commits in [repo]"
- "Create issue: [title] in [repo]"
- "Search for [code] in my repos"

### Files
- "Read [filename]"
- "Search for files containing [text]"
- "Create file [name] with [content]"
- "Show directory structure"

### Memory (with Project Segregation)
- "Remember for project:mcp-server: [important fact]"
- "What do you know about project:mcp-server?"
- "Search project:mcp-server for [topic]"
- "Show all memories tagged project:mcp-server"

**Always use tags**: `project:mcp-server, session:2025-06-28`

## 🔧 Management Scripts

```bash
# Update secrets from 1Password
./setup-claude-desktop.sh

# Verify setup
./verify-claude-desktop.sh

# Test vaults
./scripts/test-existing-secrets.sh

# Add new API keys
./scripts/add-api-keys.sh
```

## 🎯 Secret References

```bash
# Pattern: 1password:vault/item:field
GITHUB_TOKEN=1password:AI/GitHub Token:notesPlain
REDIS_HOST=1password:Server-Configurations/Redis Host:notesPlain
```

## ⚡ Quick Test

In Claude, try:
1. "What GitHub repos do I have?"
2. "Read the package.json file"
3. "Remember that I use 1Password for secrets"

---
*All secrets secured via 1Password • No plaintext credentials*