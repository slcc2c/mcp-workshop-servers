# MCP Servers Auto-start on macOS

This guide explains how to configure MCP servers to start automatically when you log into your Mac.

## Overview

The auto-start feature uses macOS's native `launchd` service manager to:
- Start MCP servers automatically after user login
- Restart servers if they crash
- Log all output for debugging
- Provide easy management commands

## Quick Start

### Enable Auto-start
```bash
npm run mcp:autostart:setup
```

### Disable Auto-start
```bash
npm run mcp:autostart:remove
```

## How It Works

1. **launchd Configuration**: A property list (plist) file defines the service
2. **Wrapper Script**: `scripts/launchd-start.sh` sets up the environment and starts the servers
3. **Process Management**: Uses existing `start-servers.js` infrastructure
4. **Logging**: All output is captured in the `logs/` directory

## File Locations

- **Launch Agent**: `~/Library/LaunchAgents/com.mcp-workshop.servers.plist`
- **Logs**: 
  - `logs/launchd.log` - Main startup log
  - `logs/launchd-stdout.log` - Standard output
  - `logs/launchd-stderr.log` - Error output
  - Individual server logs in `logs/<server-name>.log`

## Management Commands

### Check Service Status
```bash
launchctl list | grep mcp
```

### View Logs
```bash
# All logs
tail -f logs/launchd*.log

# Specific server
tail -f logs/github.log
```

### Manual Control
```bash
# Stop service (servers will not restart)
launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist

# Start service
launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist

# Restart service
launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
launchctl load ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
```

## Configuration

The launchd service is configured with:
- **RunAtLoad**: Starts when you log in
- **KeepAlive**: Restarts if servers crash
- **ThrottleInterval**: 30-second delay between restart attempts
- **ProcessType**: Interactive (has access to user session)

## Troubleshooting

### Servers Not Starting

1. Check the logs:
   ```bash
   cat logs/launchd-stderr.log
   ```

2. Verify Node.js is in PATH:
   ```bash
   which npm
   ```

3. Check service status:
   ```bash
   launchctl list com.mcp-workshop.servers
   ```
   Look for the PID (process ID) and LastExitStatus

### Permission Issues

If you see permission errors:
```bash
# Fix script permissions
chmod +x scripts/launchd-start.sh
chmod +x scripts/setup-autostart.sh
chmod +x scripts/remove-autostart.sh

# Fix plist permissions
chmod 644 ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
```

### Environment Variables

The service runs with a minimal environment. If your servers need specific environment variables:

1. Add them to the plist file's `EnvironmentVariables` section
2. Or source them in `scripts/launchd-start.sh`

### Node Version Issues

If you use nvm or similar Node version managers, the launchd script attempts to source nvm. If this fails, you may need to:

1. Use a system-wide Node installation
2. Modify `scripts/launchd-start.sh` to point to your Node installation
3. Set the full path to npm in the script

## Security Considerations

- The service runs as your user account
- No root/sudo access required
- Servers have same permissions as when run manually
- All file access is limited to your user permissions

## Alternatives

If launchd doesn't meet your needs, consider:

1. **PM2**: Process manager with more features but requires additional dependency
2. **Manual Startup**: Add to your shell profile (.zshrc/.bash_profile)
3. **Login Items**: System Preferences > Users & Groups > Login Items (less reliable)

## Uninstalling

To completely remove auto-start:

1. Run the removal script:
   ```bash
   npm run mcp:autostart:remove
   ```

2. Or manually:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
   rm ~/Library/LaunchAgents/com.mcp-workshop.servers.plist
   ```

3. Remove the plist from the project:
   ```bash
   rm com.mcp-workshop.servers.plist
   ```