#!/usr/bin/env node

// Fix server startup by adding initialization code to each server

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const servers = [
  'docker',
  'memory', 
  'jupyter',
  'kubernetes',
  'mongodb',
  'neo4j',
  'postgresql',
  'redis'
];

const startupCode = `
// Auto-start server when run directly
if (import.meta.url === \`file://\${process.argv[1]}\`) {
    const server = new ${serverName}Server();
    server.start().catch(error => {
        console.error('Failed to start server:', error);
        process.exit(1);
    });
}
`;

servers.forEach(serverName => {
  const serverPath = path.join('/Users/spencer/repos/mcp-server/dist/servers', serverName, 'index.js');
  
  try {
    let content = fs.readFileSync(serverPath, 'utf8');
    
    // Get the correct class name
    const classMatch = content.match(/export class (\w+Server)/);
    if (!classMatch) {
      console.error(`Could not find server class in ${serverName}`);
      return;
    }
    
    const className = classMatch[1];
    const code = startupCode.replace(/\${serverName}/g, className.replace('Server', ''));
    
    // Check if already has startup code
    if (content.includes('import.meta.url')) {
      console.log(`${serverName} already has startup code`);
      return;
    }
    
    // Add the startup code at the end
    content += code;
    
    fs.writeFileSync(serverPath, content);
    console.log(`✅ Fixed ${serverName} server startup`);
    
  } catch (error) {
    console.error(`Error fixing ${serverName}:`, error.message);
  }
});

console.log('\nDone! Servers should now start properly.');