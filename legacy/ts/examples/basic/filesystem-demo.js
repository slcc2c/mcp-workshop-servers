#!/usr/bin/env node

/**
 * Filesystem MCP Server Demo
 * 
 * This example demonstrates:
 * - Secure file operations
 * - Directory management
 * - File watching
 * - Search capabilities
 */

const http = require('http');
const path = require('path');

async function makeFilesystemRequest(tool, args = {}) {
  const requestData = JSON.stringify({
    id: `fs-${Date.now()}`,
    method: 'executeTool',
    params: {
      tool,
      arguments: args
    },
    server: 'filesystem'
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
  console.log('📁 Filesystem MCP Server Demo\n');

  try {
    // Get working directory info
    console.log('📍 Getting working directory information...');
    const cwdInfo = await makeFilesystemRequest('fs_get_working_directory');
    console.log('✅ Working directory:', {
      current: cwdInfo.cwd,
      allowed: cwdInfo.allowed
    });

    // Create a demo directory
    const demoDir = 'mcp-demo';
    console.log(`\n📁 Creating demo directory: ${demoDir}`);
    await makeFilesystemRequest('fs_create_directory', {
      path: demoDir,
      recursive: true
    });
    console.log('✅ Directory created');

    // Write some files
    console.log('\n📝 Creating demo files...');
    
    const files = [
      {
        path: path.join(demoDir, 'readme.md'),
        content: '# MCP Demo\n\nThis is a demonstration of the Filesystem MCP server.\n\n## Features\n- Secure file operations\n- Directory management\n- File watching\n- Search capabilities'
      },
      {
        path: path.join(demoDir, 'config.json'),
        content: JSON.stringify({
          name: 'MCP Demo',
          version: '1.0.0',
          features: ['filesystem', 'security', 'watching']
        }, null, 2)
      },
      {
        path: path.join(demoDir, 'script.js'),
        content: 'console.log("Hello from MCP Filesystem server!");'
      }
    ];

    for (const file of files) {
      await makeFilesystemRequest('fs_write_file', {
        path: file.path,
        content: file.content
      });
      console.log(`✅ Created: ${file.path}`);
    }

    // List directory contents
    console.log(`\n📋 Listing contents of ${demoDir}:`);
    const listResult = await makeFilesystemRequest('fs_list_directory', {
      path: demoDir,
      details: true
    });
    
    console.log(`Found ${listResult.count} items:`);
    listResult.items.forEach(item => {
      console.log(`   ${item.type === 'directory' ? '📁' : '📄'} ${item.name} (${item.size} bytes)`);
    });

    // Read a file
    console.log('\n📖 Reading readme.md:');
    const readResult = await makeFilesystemRequest('fs_read_file', {
      path: path.join(demoDir, 'readme.md')
    });
    console.log('✅ File content:');
    console.log(readResult.content);

    // Get file statistics
    console.log('\n📊 Getting file statistics:');
    const statsResult = await makeFilesystemRequest('fs_get_stats', {
      path: path.join(demoDir, 'config.json')
    });
    console.log('✅ File stats:', {
      type: statsResult.type,
      size: statsResult.size,
      created: new Date(statsResult.created).toLocaleString(),
      modified: new Date(statsResult.modified).toLocaleString(),
      readable: statsResult.isReadable,
      writable: statsResult.isWritable
    });

    // Search for files
    console.log('\n🔍 Searching for files containing "MCP":');
    const searchResult = await makeFilesystemRequest('fs_search_files', {
      path: demoDir,
      query: 'MCP',
      searchContent: true,
      searchNames: true,
      maxResults: 10
    });
    
    console.log(`✅ Found ${searchResult.count} matches:`);
    searchResult.results.forEach(result => {
      console.log(`   📄 ${result.name} (${result.size} bytes)`);
    });

    // Copy a file
    console.log('\n📋 Copying config.json to backup.json:');
    await makeFilesystemRequest('fs_copy_file', {
      source: path.join(demoDir, 'config.json'),
      destination: path.join(demoDir, 'backup.json')
    });
    console.log('✅ File copied');

    // Set up file watching
    console.log('\n👁️  Setting up file watcher:');
    const watchResult = await makeFilesystemRequest('fs_watch_path', {
      path: demoDir,
      events: ['change', 'add', 'unlink'],
      recursive: true
    });
    console.log(`✅ Watcher created: ${watchResult.watcherId}`);

    // List active watchers
    const watchersResult = await makeFilesystemRequest('fs_list_watchers');
    console.log(`📊 Active watchers: ${watchersResult.count}`);

    // Modify a file to trigger watcher (watcher events are logged)
    console.log('\n✏️  Modifying a file to demonstrate watching:');
    await makeFilesystemRequest('fs_write_file', {
      path: path.join(demoDir, 'modified.txt'),
      content: `File modified at ${new Date().toISOString()}`
    });
    console.log('✅ File modified (check server logs for watcher events)');

    // Check operation tracking
    console.log('\n📈 Checking operation tracking:');
    const trackingResult = await makeFilesystemRequest('getRecentOperations');
    console.log('✅ Tracking status:', {
      enabled: trackingResult.trackingEnabled,
      note: trackingResult.note
    });

    // Stop the watcher
    console.log('\n🛑 Stopping file watcher:');
    await makeFilesystemRequest('fs_unwatch_path', {
      watcherId: watchResult.watcherId
    });
    console.log('✅ Watcher stopped');

    // Clean up - delete demo directory
    console.log('\n🗑️  Cleaning up demo files:');
    await makeFilesystemRequest('fs_delete_directory', {
      path: demoDir,
      recursive: true
    });
    console.log('✅ Demo directory cleaned up');

    console.log('\n🎉 Filesystem demo completed successfully!');
    console.log('\n💡 Key capabilities demonstrated:');
    console.log('   • Secure file and directory operations');
    console.log('   • Path sandboxing and access control');
    console.log('   • File content and metadata operations');
    console.log('   • Real-time file watching');
    console.log('   • Advanced search capabilities');
    console.log('   • Operation tracking for AI context');

  } catch (error) {
    console.error('❌ Error:', error.message);
    
    if (error.message.includes('Permission denied')) {
      console.log('\n💡 Security features working:');
      console.log('   The filesystem server enforces path sandboxing');
      console.log('   Only allowed directories can be accessed');
    } else {
      console.log('\n💡 Make sure the MCP servers are running:');
      console.log('   npm run mcp:start');
    }
    
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}