# MCP Servers Auto-start Guide

This guide explains how to configure MCP servers to start automatically when you log in to your Mac.

## Overview

The auto-start feature uses macOS's native `launchd` service to:
- Start MCP servers automatically at login
- Restart servers if they crash
- Log output for debugging
- Manage server lifecycle

## Quick Setup

### Enable Auto-start

```bash
npm run autostart:setup
```

This command will:
1. Create necessary log directories
2. Install the launch agent configuration
3. Start the MCP servers immediately
4. Configure them to start on every login

### Check Status

```bash
npm run autostart:status
```

Shows:
- Whether auto-start is configured
- If servers are currently running
- Process information and PID
- Recent error messages (if any)
- Log file locations

### Disable Auto-start

```bash
npm run autostart:remove
```

This will:
1. Stop running MCP servers
2. Remove the auto-start configuration
3. Optionally clean up log files

## How It Works

### Components

1. **Launch Agent** (`com.mcp-workshop.servers.plist`)
   - Defines the service configuration
   - Specifies when to start (at login)
   - Sets restart behavior
   - Configures logging

2. **Startup Script** (`scripts/launchd-start.sh`)
   - Sets up environment variables
   - Loads .env configuration
   - Starts the MCP servers
   - Handles logging

3. **Management Scripts**
   - `setup-autostart.sh` - Installs the service
   - `remove-autostart.sh` - Uninstalls the service
   - `check-autostart.sh` - Shows current status

### File Locations

- **Configuration**: `~/Library/LaunchAgents/com.mcp-workshop.servers.plist`
- **Logs**: `~/Library/Logs/MCP/`
  - `startup.log` - Startup messages
  - `server.log` - Server output
  - `mcp-servers.out.log` - Standard output
  - `mcp-servers.err.log` - Error output

## Manual Control

Even with auto-start enabled, you can manually control the servers:

### Stop Servers
```bash
launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
```

### Start Servers
```bash
launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
```

### View Logs
```bash
# Real-time server logs
tail -f ~/Library/Logs/MCP/server.log

# Error logs
tail -f ~/Library/Logs/MCP/mcp-servers.err.log

# All logs
ls -la ~/Library/Logs/MCP/
```

## Configuration

### Environment Variables

The startup script loads your `.env` file automatically. Make sure all required environment variables are set there.

### Which Servers Start

By default, the servers configured in your environment will start:
- Gateway server
- GitHub server (if configured)
- Filesystem server
- Any other enabled servers

To change which servers start, modify your `.env` or `config/servers.json`.

### Resource Limits

The launch agent sets:
- File descriptor limit: 4096
- Nice value: 0 (normal priority)
- Restart delay: 10 seconds

## Troubleshooting

### Servers Won't Start

1. Check logs:
   ```bash
   cat ~/Library/Logs/MCP/startup.log
   cat ~/Library/Logs/MCP/mcp-servers.err.log
   ```

2. Verify Node.js is accessible:
   ```bash
   which node
   ```

3. Check if already running:
   ```bash
   launchctl list | grep mcp
   ps aux | grep "mcp:start"
   ```

### Permission Issues

Make sure scripts are executable:
```bash
chmod +x scripts/*.sh
```

### Path Issues

The startup script adds common paths:
- `/opt/homebrew/bin` (Apple Silicon)
- `/usr/local/bin` (Intel)
- Standard system paths

If Node.js is installed elsewhere, update the PATH in:
- `com.mcp-workshop.servers.plist`
- `scripts/launchd-start.sh`

### Servers Keep Restarting

Check for startup errors:
```bash
tail -f ~/Library/Logs/MCP/mcp-servers.err.log
```

Common causes:
- Missing environment variables
- Port already in use
- Database connection failures

## Advanced Configuration

### Custom Launch Arguments

Edit `com.mcp-workshop.servers.plist` to:
- Change restart behavior
- Modify environment variables
- Adjust resource limits
- Set different log locations

### Multiple Instances

To run multiple MCP server sets:
1. Create separate plist files with unique labels
2. Use different ports in each configuration
3. Set unique log paths

### Integration with Other Services

The MCP servers can be configured to:
- Wait for other services (like databases)
- Send notifications on startup/failure
- Integrate with monitoring systems

## Security Considerations

- The servers run with your user permissions
- Logs may contain sensitive information
- Environment variables are loaded from `.env`
- No root/admin privileges required

## Best Practices

1. **Monitor Logs**: Regularly check logs for errors
2. **Update Paths**: Keep paths absolute in the plist
3. **Test Changes**: After config changes, test with manual start/stop
4. **Backup Config**: Keep a copy of your working plist file
5. **Resource Usage**: Monitor CPU/memory if running many servers

## Uninstalling

To completely remove auto-start:

```bash
# Remove configuration
npm run autostart:remove

# Clean up logs (optional)
rm -rf ~/Library/Logs/MCP

# Remove plist from project (optional)
rm com.mcp-workshop.servers.plist
```

The MCP servers can still be run manually with `npm run mcp:start`.