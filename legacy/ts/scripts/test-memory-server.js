#!/usr/bin/env node
/**
 * Test Memory Server directly
 */

import { MemoryServer } from '../dist/servers/memory/index.js';

async function test() {
  console.log('Testing Memory Server...\n');
  
  const server = new MemoryServer();
  
  try {
    // Initialize
    await server.initialize();
    console.log('✓ Server initialized');
    
    // List tools
    const tools = server.listTools();
    console.log(`\n✓ Found ${tools.length} tools:`);
    tools.forEach(tool => {
      console.log(`  - ${tool.name}: ${tool.description}`);
    });
    
    // Test storing memory
    console.log('\n✓ Testing memory storage...');
    const storeResult = await server.executeTool('memory_store', {
      content: 'Test memory entry',
      type: 'fact',
      tags: ['test'],
      metadata: { test: true }
    });
    console.log('  Stored:', storeResult);
    
    // Test searching memory
    console.log('\n✓ Testing memory search...');
    const searchResult = await server.executeTool('memory_search', {
      query: 'test',
      limit: 10
    });
    console.log('  Found:', searchResult);
    
    // Shutdown
    await server.shutdown();
    console.log('\n✓ Server shut down successfully');
    
  } catch (error) {
    console.error('\n✗ Error:', error);
  }
}

test();