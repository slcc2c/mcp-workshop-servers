# 🚀 Real-time Communication Features

The MCP Gateway now supports real-time communication through two protocols:

## 🌐 WebSocket Support

WebSocket endpoint: `ws://localhost:3000/ws`

### Features
- **Bidirectional communication** for real-time tool execution
- **Client authentication** and session management
- **Message-based protocol** with typed messages
- **Error handling** and connection management

### Message Types

#### Client → Server Messages

**Ping Message**
```json
{
  "type": "ping",
  "id": "unique-id",
  "data": {},
  "timestamp": 1640995200000
}
```

**Tool Call Message**
```json
{
  "type": "tool_call",
  "id": "unique-id",
  "data": {
    "serverId": "memory",
    "toolName": "memory_search",
    "params": { "project": "my-project" }
  },
  "timestamp": 1640995200000
}
```

#### Server → Client Messages

**Status Message**
```json
{
  "type": "status",
  "data": {
    "message": "Connected to MCP Gateway WebSocket",
    "clientId": "abc123",
    "requiresAuth": true
  },
  "timestamp": 1640995200000
}
```

**Tool Response Message**
```json
{
  "type": "tool_response",
  "id": "matching-request-id",
  "data": {
    "success": true,
    "result": { "memories": [...] },
    "serverId": "memory",
    "toolName": "memory_search"
  },
  "timestamp": 1640995200000
}
```

**Error Message**
```json
{
  "type": "error",
  "id": "matching-request-id",
  "data": {
    "error": "Authentication required",
    "code": "auth_required"
  },
  "timestamp": 1640995200000
}
```

### JavaScript Client Example

```javascript
const ws = new WebSocket('ws://localhost:3000/ws');

ws.onopen = () => {
  console.log('Connected to MCP Gateway');
  
  // Call a tool
  ws.send(JSON.stringify({
    type: 'tool_call',
    id: 'search-1',
    data: {
      serverId: 'memory',
      toolName: 'memory_search',
      params: { project: 'my-project' }
    },
    timestamp: Date.now()
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};
```

## 📡 Server-Sent Events (SSE)

SSE endpoint: `http://localhost:3000/api/v1/events`

### Features
- **Unidirectional streaming** from server to client
- **Real-time status updates** and notifications
- **Heartbeat mechanism** to keep connections alive
- **Standard HTTP** - no special client libraries needed

### Event Types

**Connection Event**
```json
{
  "type": "connected",
  "timestamp": 1640995200000,
  "message": "Connected to MCP Gateway events"
}
```

**Heartbeat Event**
```json
{
  "type": "heartbeat",
  "timestamp": 1640995200000
}
```

### JavaScript Client Example

```javascript
const eventSource = new EventSource('http://localhost:3000/api/v1/events');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('SSE Event:', data);
};

eventSource.onerror = (error) => {
  console.error('SSE Error:', error);
};
```

## 🧪 Testing

Use the included test script to verify functionality:

```bash
# Make sure gateway is running
npm run mcp:start

# Run tests
node test-websocket.js
```

## 🔐 Authentication

WebSocket connections require authentication through the same token system used for HTTP requests. Clients must provide valid authentication before making tool calls.

## 🚀 Use Cases

### Real-time Development
- **Live code execution** in Jupyter notebooks
- **Real-time file watching** and updates
- **Docker container streaming** logs and stats

### AI Collaboration
- **Streaming tool responses** for better UX
- **Real-time context sharing** between AI instances
- **Live progress updates** for long-running operations

### Workshop Scenarios
- **Live demonstration** of tool capabilities
- **Real-time debugging** and troubleshooting
- **Interactive learning** with immediate feedback

## 🔧 Configuration

WebSocket and SSE features are enabled by default when the gateway starts. No additional configuration is required.

## 📊 Monitoring

WebSocket connections are logged with client information:
- Connection/disconnection events
- Message handling and errors
- Authentication status
- Client metadata (user agent, connection time)

Check gateway logs for real-time communication activity:

```bash
tail -f logs/gateway.log | grep -E "(websocket|sse)"
```