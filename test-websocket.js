#!/usr/bin/env node

/**
 * Simple WebSocket test client for MCP Gateway
 */

const WebSocket = require('ws');

const GATEWAY_URL = 'ws://localhost:3000/ws';

async function testWebSocket() {
  console.log('🚀 Testing MCP Gateway WebSocket connection...');
  
  const ws = new WebSocket(GATEWAY_URL);
  
  ws.on('open', () => {
    console.log('✅ Connected to WebSocket');
    
    // Send ping
    console.log('📤 Sending ping...');
    ws.send(JSON.stringify({
      type: 'ping',
      id: 'test-ping-1',
      data: {},
      timestamp: Date.now()
    }));
    
    // Test tool call (after a delay)
    setTimeout(() => {
      console.log('📤 Sending test tool call...');
      ws.send(JSON.stringify({
        type: 'tool_call',
        id: 'test-tool-1',
        data: {
          serverId: 'memory',
          toolName: 'memory_search',
          params: { project: 'test' }
        },
        timestamp: Date.now()
      }));
    }, 1000);
  });
  
  ws.on('message', (data) => {
    try {
      const message = JSON.parse(data.toString());
      console.log('📥 Received:', {
        type: message.type,
        id: message.id,
        timestamp: new Date(message.timestamp).toISOString()
      });
      
      if (message.data) {
        console.log('   Data:', JSON.stringify(message.data, null, 2));
      }
    } catch (error) {
      console.error('❌ Error parsing message:', error.message);
    }
  });
  
  ws.on('error', (error) => {
    console.error('❌ WebSocket error:', error.message);
  });
  
  ws.on('close', (code, reason) => {
    console.log(`🔌 Connection closed: ${code} - ${reason}`);
  });
  
  // Clean shutdown after 10 seconds
  setTimeout(() => {
    console.log('⏰ Test completed, closing connection...');
    ws.close();
  }, 10000);
}

// Test SSE endpoint
async function testSSE() {
  console.log('🌊 Testing SSE endpoint...');
  
  try {
    const response = await fetch('http://localhost:3000/api/v1/events');
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    console.log('✅ SSE connection established');
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    let eventCount = 0;
    const maxEvents = 5;
    
    while (eventCount < maxEvents) {
      const { value, done } = await reader.read();
      
      if (done) {
        console.log('📡 SSE stream ended');
        break;
      }
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6));
            console.log('📥 SSE Event:', {
              type: data.type,
              timestamp: new Date(data.timestamp).toISOString()
            });
            eventCount++;
          } catch (e) {
            // Ignore parsing errors for incomplete chunks
          }
        }
      }
    }
    
    reader.cancel();
    console.log('⏰ SSE test completed');
    
  } catch (error) {
    console.error('❌ SSE test failed:', error.message);
  }
}

// Main test function
async function runTests() {
  console.log('🧪 MCP Gateway Real-time Communication Tests');
  console.log('='.repeat(50));
  
  // First test if gateway is running
  try {
    const response = await fetch('http://localhost:3000/health');
    if (!response.ok) {
      throw new Error(`Gateway not responding: ${response.status}`);
    }
    console.log('✅ Gateway is running');
  } catch (error) {
    console.error('❌ Gateway not accessible:', error.message);
    console.log('💡 Make sure to start the gateway with: npm run mcp:start');
    process.exit(1);
  }
  
  console.log('');
  
  // Test SSE first (simpler)
  await testSSE();
  
  console.log('');
  console.log('-'.repeat(50));
  console.log('');
  
  // Test WebSocket
  await testWebSocket();
}

// Add fetch polyfill for Node.js < 18
if (typeof fetch === 'undefined') {
  global.fetch = require('node-fetch');
}

runTests().catch(error => {
  console.error('❌ Test suite failed:', error.message);
  process.exit(1);
});