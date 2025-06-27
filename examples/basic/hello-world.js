#!/usr/bin/env node

/**
 * Basic example: Hello World with MCP servers
 * 
 * This example demonstrates:
 * - Making basic requests to MCP servers
 * - Handling responses
 * - Error handling
 */

const http = require('http');

async function makeRequest(method, params = {}) {
  const requestData = JSON.stringify({
    id: `req-${Date.now()}`,
    method,
    params,
    server: 'memory' // Using memory server for this example
  });

  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: '/api/v1/execute',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(requestData)
      }
    }, (res) => {
      let data = '';
      
      res.on('data', chunk => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          if (response.error) {
            reject(new Error(response.error.message));
          } else {
            resolve(response.result);
          }
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('error', reject);
    req.write(requestData);
    req.end();
  });
}

async function main() {
  console.log('🚀 Hello World MCP Example\n');

  try {
    // Store a simple memory
    console.log('📝 Storing a memory...');
    const storeResult = await makeRequest('executeTool', {
      tool: 'memory_store',
      arguments: {
        content: 'Hello World! This is my first memory.',
        type: 'experience',
        tags: ['hello-world', 'first', 'example'],
        metadata: {
          example: 'hello-world',
          timestamp: new Date().toISOString()
        }
      }
    });
    
    console.log('✅ Memory stored:', storeResult);
    const memoryId = storeResult.id;
    
    // Retrieve the memory
    console.log('\n🔍 Retrieving the memory...');
    const getResult = await makeRequest('executeTool', {
      tool: 'memory_get',
      arguments: {
        id: memoryId
      }
    });
    
    console.log('✅ Memory retrieved:', {
      id: getResult.id,
      content: getResult.content,
      type: getResult.type,
      tags: getResult.tags
    });
    
    // Search for memories
    console.log('\n🔍 Searching for memories...');
    const searchResult = await makeRequest('executeTool', {
      tool: 'memory_search',
      arguments: {
        query: 'hello',
        limit: 5
      }
    });
    
    console.log('✅ Search results:', {
      query: searchResult.query,
      totalResults: searchResult.totalResults,
      firstResult: searchResult.results[0]?.content
    });
    
    // List available tags
    console.log('\n🏷️  Listing tags...');
    const tagsResult = await makeRequest('executeTool', {
      tool: 'memory_list_tags',
      arguments: {}
    });
    
    console.log('✅ Available tags:', tagsResult);
    
    console.log('\n🎉 Hello World example completed successfully!');
    
  } catch (error) {
    console.error('❌ Error:', error.message);
    console.log('\n💡 Make sure the MCP servers are running:');
    console.log('   npm run mcp:start');
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}