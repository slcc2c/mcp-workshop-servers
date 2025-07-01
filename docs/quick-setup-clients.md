# Quick Setup: Connect AI Clients to MCP Servers

This is a quick reference guide to connect Claude Desktop, Cursor IDE, and OpenAI to your MCP servers.

## Prerequisites

1. MCP servers are running:
   ```bash
   npm run mcp:start
   ```

2. Authentication tokens are set in `.env`:
   ```bash
   MCP_CLAUDE_AUTH_TOKEN=your-claude-token
   MCP_CURSOR_AUTH_TOKEN=your-cursor-token
   MCP_OPENAI_AUTH_TOKEN=your-openai-token
   ```

## Claude Desktop Setup (2 minutes)

1. **Copy configuration:**
   ```bash
   # macOS
   cp claude-desktop-config.json ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. **Restart Claude Desktop**

3. **Test in Claude:**
   ```
   Use the github tool to search for "mcp servers"
   ```

## Cursor IDE Setup (3 minutes)

1. **Set environment variable:**
   ```bash
   export MCP_CURSOR_AUTH_TOKEN=your-cursor-token
   ```

2. **Configure in Cursor:**
   - Open Settings (Cmd/Ctrl + ,)
   - Search "MCP"
   - Set Gateway URL: `http://localhost:3000`
   - Set Auth Token: Your token from step 1

3. **Test:**
   - Command Palette → "MCP: List Tools"

## OpenAI Setup (5 minutes)

1. **Install OpenAI SDK:**
   ```bash
   pip install openai
   # or
   npm install openai
   ```

2. **Python example:**
   ```python
   import openai
   import json
   import requests
   import os
   
   # Your MCP gateway details
   MCP_URL = "http://localhost:3000/api/v1"
   MCP_TOKEN = os.getenv("MCP_OPENAI_AUTH_TOKEN")
   
   # Define MCP function
   def search_github(query):
       response = requests.post(
           f"{MCP_URL}/servers/github/execute",
           headers={"Authorization": f"Bearer {MCP_TOKEN}"},
           json={
               "id": "openai-001",
               "method": "tools/call",
               "params": {
                   "name": "search_repositories",
                   "arguments": {"query": query, "limit": 5}
               }
           }
       )
       return response.json()["result"]
   
   # Use with OpenAI
   client = openai.OpenAI()
   
   tools = [{
       "type": "function",
       "function": {
           "name": "search_github",
           "description": "Search GitHub repositories",
           "parameters": {
               "type": "object",
               "properties": {
                   "query": {"type": "string", "description": "Search query"}
               },
               "required": ["query"]
           }
       }
   }]
   
   # Create completion
   response = client.chat.completions.create(
       model="gpt-4-turbo-preview",
       messages=[{"role": "user", "content": "Find Python MCP servers"}],
       tools=tools,
       tool_choice="auto"
   )
   
   # Execute function calls
   if response.choices[0].message.tool_calls:
       for tool_call in response.choices[0].message.tool_calls:
           if tool_call.function.name == "search_github":
               args = json.loads(tool_call.function.arguments)
               result = search_github(args["query"])
               print(result)
   ```

3. **JavaScript example:**
   ```javascript
   import OpenAI from 'openai';
   import axios from 'axios';
   
   const openai = new OpenAI();
   const MCP_URL = 'http://localhost:3000/api/v1';
   const MCP_TOKEN = process.env.MCP_OPENAI_AUTH_TOKEN;
   
   // MCP function
   async function searchGitHub(query) {
     const response = await axios.post(
       `${MCP_URL}/servers/github/execute`,
       {
         id: 'openai-001',
         method: 'tools/call',
         params: {
           name: 'search_repositories',
           arguments: { query, limit: 5 }
         }
       },
       {
         headers: { Authorization: `Bearer ${MCP_TOKEN}` }
       }
     );
     return response.data.result;
   }
   
   // Use with OpenAI
   const completion = await openai.chat.completions.create({
     model: 'gpt-4-turbo-preview',
     messages: [{ role: 'user', content: 'Find Python MCP servers' }],
     tools: [{
       type: 'function',
       function: {
         name: 'search_github',
         description: 'Search GitHub repositories',
         parameters: {
           type: 'object',
           properties: {
             query: { type: 'string', description: 'Search query' }
           },
           required: ['query']
         }
       }
     }],
     tool_choice: 'auto'
   });
   
   // Execute function calls
   if (completion.choices[0].message.tool_calls) {
     for (const toolCall of completion.choices[0].message.tool_calls) {
       if (toolCall.function.name === 'search_github') {
         const args = JSON.parse(toolCall.function.arguments);
         const result = await searchGitHub(args.query);
         console.log(result);
       }
     }
   }
   ```

## Test All Connections

Run the test script to verify all connections:

```bash
# Test all clients
node scripts/test-connections.js all

# Test specific client
node scripts/test-connections.js claude
node scripts/test-connections.js cursor
node scripts/test-connections.js openai
```

## Common Issues

### "Authentication failed"
- Check token is set: `echo $MCP_CLAUDE_AUTH_TOKEN`
- Verify token in `.env` file
- Restart terminal/application after setting env vars

### "Gateway not found"
- Ensure MCP servers are running: `npm run mcp:status`
- Check gateway URL: `http://localhost:3000`
- Verify no firewall blocking port 3000

### "Tool not found"
- Use correct format: `server:tool` (e.g., `github:search_repositories`)
- Check available tools: `curl -H "Authorization: Bearer $token" http://localhost:3000/api/v1/servers/github/execute -d '{"method":"tools/list"}'`

## Next Steps

- Read full documentation: [Client Connections Guide](./client-connections.md)
- Set up SSL/TLS for production
- Configure monitoring and alerts
- Implement custom tools