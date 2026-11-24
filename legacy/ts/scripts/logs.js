#!/usr/bin/env node

/**
 * View and manage MCP server logs
 */

import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const LOGS_DIR = path.join(__dirname, '..', 'logs');

async function getLogFiles() {
  try {
    const files = await fs.promises.readdir(LOGS_DIR);
    return files.filter(file => file.endsWith('.log'));
  } catch (error) {
    return [];
  }
}

async function showLogFile(filename, options = {}) {
  const logPath = path.join(LOGS_DIR, filename);
  
  try {
    await fs.promises.access(logPath);
  } catch (error) {
    console.error(`❌ Log file not found: ${filename}`);
    return;
  }

  console.log(`📜 Viewing ${filename}:`);
  console.log('─'.repeat(60));

  if (options.follow) {
    // Use tail -f for live following
    const tail = spawn('tail', ['-f', logPath], {
      stdio: 'inherit'
    });
    
    process.on('SIGINT', () => {
      tail.kill();
      process.exit(0);
    });
  } else {
    // Show last N lines
    const lines = options.lines || 50;
    
    try {
      const tail = spawn('tail', ['-n', lines.toString(), logPath], {
        stdio: 'inherit'
      });
      
      tail.on('close', (code) => {
        if (code !== 0) {
          console.error(`❌ Failed to read log file (exit code: ${code})`);
        }
      });
    } catch (error) {
      // Fallback to fs.readFile for environments without tail
      const content = await fs.promises.readFile(logPath, 'utf-8');
      const logLines = content.split('\n');
      const displayLines = logLines.slice(-lines);
      console.log(displayLines.join('\n'));
    }
  }
}

async function listLogFiles() {
  const logFiles = await getLogFiles();
  
  if (logFiles.length === 0) {
    console.log('ℹ️  No log files found');
    console.log('💡 Start some servers to generate logs: npm run mcp:start');
    return;
  }

  console.log('📜 Available log files:\n');

  for (const file of logFiles) {
    const logPath = path.join(LOGS_DIR, file);
    
    try {
      const stats = await fs.promises.stat(logPath);
      const sizeKB = Math.round(stats.size / 1024);
      const modifiedDate = stats.mtime.toLocaleString();
      
      console.log(`📄 ${file}`);
      console.log(`   Size: ${sizeKB} KB`);
      console.log(`   Modified: ${modifiedDate}`);
      console.log(`   Path: ${logPath}`);
      console.log();
    } catch (error) {
      console.log(`📄 ${file} (error reading stats)`);
    }
  }
}

async function clearLogs() {
  const logFiles = await getLogFiles();
  
  if (logFiles.length === 0) {
    console.log('ℹ️  No log files to clear');
    return;
  }

  console.log(`🗑️  Clearing ${logFiles.length} log file(s)...`);
  
  for (const file of logFiles) {
    const logPath = path.join(LOGS_DIR, file);
    
    try {
      await fs.promises.writeFile(logPath, '');
      console.log(`✅ Cleared ${file}`);
    } catch (error) {
      console.error(`❌ Failed to clear ${file}:`, error.message);
    }
  }
  
  console.log('🎉 Log files cleared');
}

async function searchLogs(query, options = {}) {
  const logFiles = await getLogFiles();
  
  if (logFiles.length === 0) {
    console.log('ℹ️  No log files to search');
    return;
  }

  console.log(`🔍 Searching for "${query}" in log files...\n`);
  
  for (const file of logFiles) {
    const logPath = path.join(LOGS_DIR, file);
    
    try {
      // Use grep for better performance
      const grep = spawn('grep', [
        options.ignoreCase ? '-i' : '',
        options.lineNumbers ? '-n' : '',
        query,
        logPath
      ].filter(Boolean), {
        stdio: ['pipe', 'pipe', 'pipe']
      });
      
      let output = '';
      let hasResults = false;
      
      grep.stdout.on('data', (data) => {
        if (!hasResults) {
          console.log(`📄 ${file}:`);
          hasResults = true;
        }
        output += data.toString();
      });
      
      await new Promise((resolve) => {
        grep.on('close', (code) => {
          if (hasResults) {
            console.log(output);
            console.log();
          }
          resolve();
        });
      });
    } catch (error) {
      // Fallback to manual search
      try {
        const content = await fs.promises.readFile(logPath, 'utf-8');
        const lines = content.split('\n');
        const searchTerm = options.ignoreCase ? query.toLowerCase() : query;
        
        const matches = lines.filter((line, index) => {
          const searchLine = options.ignoreCase ? line.toLowerCase() : line;
          return searchLine.includes(searchTerm);
        });
        
        if (matches.length > 0) {
          console.log(`📄 ${file}:`);
          matches.forEach(match => console.log(`   ${match}`));
          console.log();
        }
      } catch (readError) {
        console.error(`❌ Error searching ${file}:`, readError.message);
      }
    }
  }
}

function showUsage() {
  console.log('📜 MCP Server Logs Utility\n');
  console.log('Usage:');
  console.log('  npm run mcp:logs                    List all log files');
  console.log('  npm run mcp:logs <server>           Show recent logs for server');
  console.log('  npm run mcp:logs <server> --follow  Follow logs in real-time');
  console.log('  npm run mcp:logs --clear            Clear all log files');
  console.log('  npm run mcp:logs --search <term>    Search logs for term');
  console.log();
  console.log('Options:');
  console.log('  --lines <n>     Number of lines to show (default: 50)');
  console.log('  --follow, -f    Follow logs in real-time');
  console.log('  --clear         Clear all log files');
  console.log('  --search <term> Search logs for term');
  console.log('  --ignore-case   Case-insensitive search');
  console.log();
}

async function main() {
  const args = process.argv.slice(2);
  
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    showUsage();
    await listLogFiles();
    return;
  }

  if (args.includes('--clear')) {
    await clearLogs();
    return;
  }

  const searchIndex = args.indexOf('--search');
  if (searchIndex !== -1 && searchIndex + 1 < args.length) {
    const query = args[searchIndex + 1];
    const options = {
      ignoreCase: args.includes('--ignore-case'),
      lineNumbers: true
    };
    await searchLogs(query, options);
    return;
  }

  // Show specific log file
  const serverName = args[0];
  
  if (!serverName || serverName.startsWith('--')) {
    await listLogFiles();
    return;
  }

  const logFile = `${serverName}.log`;
  const options = {
    follow: args.includes('--follow') || args.includes('-f'),
    lines: 50
  };

  // Check for --lines option
  const linesIndex = args.indexOf('--lines');
  if (linesIndex !== -1 && linesIndex + 1 < args.length) {
    options.lines = parseInt(args[linesIndex + 1], 10) || 50;
  }

  await showLogFile(logFile, options);
}

if (require.main === module) {
  main().catch(error => {
    console.error('❌ Logs utility failed:', error.message);
    process.exit(1);
  });
}