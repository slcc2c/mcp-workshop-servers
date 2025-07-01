# Project Attachment Flow

## Visual Flow Diagram

```mermaid
graph TD
    A[Start] --> B{New or Existing Project?}
    
    B -->|New Project| C[Choose Template]
    B -->|Existing Project| D[Select Project Path]
    
    C --> C1[Web App Template]
    C --> C2[API Template]
    C --> C3[Data Science Template]
    C --> C4[Mobile Template]
    
    C1 --> D
    C2 --> D
    C3 --> D
    C4 --> D
    
    D --> E[Run attach-project.sh]
    
    E --> F[Enter Project Details]
    F --> F1[Project Path]
    F --> F2[Project Name]
    F --> F3[Configuration Level]
    
    F3 --> G{Config Level}
    G -->|Basic| H1[Filesystem Only]
    G -->|Standard| H2[Filesystem + Memory]
    G -->|Full| H3[All Servers]
    
    H1 --> I[Update Claude Config]
    H2 --> I
    H3 --> I
    
    I --> J[Create Project Files]
    J --> J1[.mcp/context.md]
    J --> J2[.env.mcp]
    J --> J3[mcp-helper.sh]
    
    J --> K[Restart Claude Desktop]
    K --> L[Test Connection]
    
    L --> M{Working?}
    M -->|Yes| N[Start Coding!]
    M -->|No| O[Troubleshoot]
    
    O --> O1[Check Logs]
    O --> O2[Validate Config]
    O --> O3[Fix Issues]
    O3 --> K
```

## Step-by-Step Process

### 1. Choose Your Project
- **New Project**: Select a template (web-app, api, data-science, mobile)
- **Existing Project**: Navigate to your project directory

### 2. Run Attachment Script
```bash
./scripts/attach-project.sh
```

### 3. Configure Project
- **Project Path**: Full path to your project directory
- **Project Name**: Unique identifier for memory segregation
- **Config Level**:
  - Basic: Filesystem access only
  - Standard: Filesystem + Memory (recommended)
  - Full: All servers including GitHub, Docker, databases

### 4. Automatic Setup
The script will:
- Back up existing Claude config
- Add MCP server configurations
- Create project metadata files
- Set up helper scripts

### 5. Restart and Test
- Quit Claude Desktop completely
- Reopen Claude Desktop
- Test with: "List files in my project"

## Configuration Examples

### Basic Setup
```json
{
  "mcp-filesystem-myapp": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]
  }
}
```

### Standard Setup
```json
{
  "mcp-filesystem-myapp": { ... },
  "mcp-memory-myapp": {
    "command": "node",
    "args": ["path/to/memory/server"],
    "env": {
      "MEMORY_PROJECT": "myapp"
    }
  }
}
```

### Full Setup
```json
{
  "mcp-filesystem-myapp": { ... },
  "mcp-memory-myapp": { ... },
  "mcp-github": { ... },
  "mcp-docker": { ... },
  "mcp-postgresql": { ... }
}
```

## Common Patterns

### Single Developer, Single Project
- Use standard setup (filesystem + memory)
- Simple project name
- Default paths

### Multiple Projects
- Use project-specific server names
- Separate memory contexts
- Consider workspace organization

### Team Development
- Standardize project names
- Use shared templates
- Document conventions in .mcp/context.md

### CI/CD Integration
- Export configs to environment
- Use memory for build context
- Track deployment history