# 🚀 Attach Your Project to MCP Servers - 2 Minute Guide

This guide shows you how to quickly attach your project to Claude Desktop using MCP servers. After setup, Claude will have full access to your project files, memory context, and development tools.

## Quick Start (< 2 minutes)

### Step 1: Run the Attachment Script

```bash
# From the MCP server directory
./scripts/attach-project.sh /path/to/your/project
```

This script will:
- ✅ Configure filesystem access to your project
- ✅ Set up memory segregation for your project context
- ✅ Update Claude Desktop configuration
- ✅ Create project-specific environment variables

### Step 2: Restart Claude Desktop

After running the script, restart Claude Desktop to load the new configuration.

### Step 3: Test Your Setup

In Claude, try these commands to verify:

```
List files in my project
```

```
Remember that this project is about [your project description]
```

## Manual Setup (Alternative Method)

If you prefer manual configuration or need custom settings:

### 1. Configure Filesystem Access

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-filesystem": {
      "command": "npx",
      "args": [
        "-y", 
        "@modelcontextprotocol/server-filesystem",
        "/path/to/your/project"  // 👈 Your project path here
      ]
    }
  }
}
```

### 2. Set Up Project Memory

Add project-specific memory configuration:

```json
{
  "mcpServers": {
    "mcp-memory": {
      "command": "node",
      "args": ["/path/to/mcp-server/dist/servers/memory/index.js"],
      "env": {
        "MEMORY_PROJECT": "my-awesome-project",  // 👈 Your project name
        "MEMORY_STORAGE_PATH": "~/.mcp/memory"
      }
    }
  }
}
```

### 3. Configure Additional Servers (Optional)

For full development capabilities, add these servers:

```json
{
  "mcpServers": {
    // Existing servers...
    
    "mcp-github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "env:GITHUB_TOKEN"
      }
    },
    
    "mcp-docker": {
      "command": "node",
      "args": ["/path/to/mcp-server/dist/servers/docker/index.js"],
      "env": {
        "DOCKER_HOST": "unix:///var/run/docker.sock"
      }
    }
  }
}
```

## Project Templates

Use our templates for common project types:

### Web Application
```bash
./scripts/attach-project.sh /path/to/project --template=web-app
```

### API Service
```bash
./scripts/attach-project.sh /path/to/project --template=api
```

### Mobile App
```bash
./scripts/attach-project.sh /path/to/project --template=mobile
```

### Data Science
```bash
./scripts/attach-project.sh /path/to/project --template=data-science
```

## Working with Multiple Projects

### Option 1: Project Switching
```bash
# Switch between projects
./scripts/switch-project.sh project-a
./scripts/switch-project.sh project-b
```

### Option 2: Multiple Filesystem Servers
```json
{
  "mcpServers": {
    "project-a-files": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project-a"]
    },
    "project-b-files": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project-b"]
    }
  }
}
```

## Project-Specific Environment Variables

Create a `.mcp-env` file in your project root:

```bash
# .mcp-env
PROJECT_NAME=my-awesome-project
PROJECT_TYPE=web-app
GITHUB_REPO=username/repo
DATABASE_URL=postgresql://localhost/myapp
API_ENDPOINT=http://localhost:3000
```

The attachment script will automatically load these variables.

## Common Use Cases

### 1. Full-Stack Web App
```bash
# Attach a Next.js + PostgreSQL project
./scripts/attach-project.sh /path/to/nextjs-app --template=web-app --with-db=postgresql
```

### 2. Microservices Project
```bash
# Attach a multi-service project
./scripts/attach-project.sh /path/to/services --template=microservices --with-docker --with-k8s
```

### 3. iOS/macOS Development
```bash
# Attach an Xcode project
./scripts/attach-project.sh /path/to/ios-app --template=ios --with-simulator
```

## Verification Checklist

After attaching your project, verify these work in Claude:

- [ ] **File Access**: "Show me the files in my project"
- [ ] **Memory**: "Remember that this project uses React and TypeScript"
- [ ] **Search**: "Search for TODO comments in my code"
- [ ] **Build**: "Run the build command for my project"
- [ ] **Git**: "Show me recent commits"

## Troubleshooting

### "Cannot access files"
- Check the project path in your config
- Ensure the filesystem server is in the allowed paths
- Restart Claude Desktop after config changes

### "Memory not persisting"
- Verify MEMORY_PROJECT is set correctly
- Check ~/.mcp/memory directory exists
- Use "Remember that..." to store context

### "Tools not showing up"
- Restart Claude Desktop
- Check server logs: `npm run mcp:logs`
- Verify all dependencies are installed

## Advanced Configuration

### Custom Allowed Paths
```json
{
  "env": {
    "ALLOWED_PATHS": "/path/to/project:/path/to/shared-libs:/path/to/docs"
  }
}
```

### Project-Specific Tool Restrictions
```json
{
  "env": {
    "ALLOWED_TOOLS": "read,write,search",
    "BLOCKED_TOOLS": "delete,execute"
  }
}
```

### Memory Tagging Strategy
```javascript
// Automatic tagging for your project
memory_add({
  content: "Project architecture details...",
  tags: ["project:myapp", "architecture", "v2.0"]
})
```

## Next Steps

1. **Explore Templates**: Check `/templates` for pre-configured project setups
2. **Customize Tools**: Add project-specific MCP servers
3. **Share Configs**: Export and share your configuration with your team
4. **Automate Workflows**: Create project-specific scripts and commands

## Quick Reference Card

```bash
# Attach new project
./scripts/attach-project.sh /path/to/project

# Switch projects
./scripts/switch-project.sh project-name

# Update configuration
./scripts/update-project-config.sh

# List attached projects
./scripts/list-projects.sh

# Remove project
./scripts/detach-project.sh project-name
```

---

💡 **Pro Tip**: Save your project configuration as a git-tracked file (`.mcp-config.json`) in your project root for easy team sharing!