#!/bin/bash

# Setup script for GitHub MCP health monitoring cron job

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Setting up GitHub MCP health monitoring..."

# Create cron job script
cat > "$SCRIPT_DIR/github-daily-check.sh" << 'EOF'
#!/bin/bash

# Daily GitHub MCP health check script
export PATH="/usr/local/bin:/usr/bin:/bin"
export NODE_PATH="/usr/local/lib/node_modules"

# Load environment variables from user profile
source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null || true

# Change to project directory
cd "$(dirname "$0")/.." || exit 1

# Create log directory
mkdir -p logs

# Run health check
echo "=== GitHub MCP Daily Health Check ===" >> logs/daily-health-check.log
echo "Date: $(date)" >> logs/daily-health-check.log

# Validate token
node scripts/validate-github-token.js >> logs/daily-health-check.log 2>&1
TOKEN_STATUS=$?

# Run health check
node scripts/github-health-check.js >> logs/daily-health-check.log 2>&1
HEALTH_STATUS=$?

# Check for alerts
if [ -f data/github-alerts.log ]; then
    ALERTS=$(tail -n 10 data/github-alerts.log)
    if [ ! -z "$ALERTS" ]; then
        echo "Recent alerts:" >> logs/daily-health-check.log
        echo "$ALERTS" >> logs/daily-health-check.log
        
        # Send notification on macOS
        if command -v osascript &> /dev/null; then
            osascript -e 'display notification "GitHub MCP server has alerts. Check logs." with title "MCP Health Alert"'
        fi
    fi
fi

# Summary
echo "" >> logs/daily-health-check.log
if [ $TOKEN_STATUS -eq 0 ] && [ $HEALTH_STATUS -eq 0 ]; then
    echo "✓ All checks passed" >> logs/daily-health-check.log
else
    echo "✗ Some checks failed" >> logs/daily-health-check.log
    
    # Send failure notification
    if command -v osascript &> /dev/null; then
        osascript -e 'display notification "GitHub MCP health check failed. Check logs." with title "MCP Health Check Failed"'
    fi
fi

echo "----------------------------------------" >> logs/daily-health-check.log

# Rotate logs if too large (>10MB)
if [ -f logs/daily-health-check.log ]; then
    SIZE=$(du -k logs/daily-health-check.log | cut -f1)
    if [ $SIZE -gt 10240 ]; then
        mv logs/daily-health-check.log logs/daily-health-check.log.old
        tail -n 1000 logs/daily-health-check.log.old > logs/daily-health-check.log
        rm logs/daily-health-check.log.old
    fi
fi
EOF

chmod +x "$SCRIPT_DIR/github-daily-check.sh"

# Create LaunchAgent plist for macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/com.mcp.github-health-check.plist"
    
    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mcp.github-health-check</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/github-daily-check.sh</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/cron-stdout.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/cron-stderr.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

    echo "Created LaunchAgent at: $PLIST_PATH"
    echo ""
    echo "To activate the daily health check (runs at 9:00 AM):"
    echo "  launchctl load $PLIST_PATH"
    echo ""
    echo "To deactivate:"
    echo "  launchctl unload $PLIST_PATH"
    echo ""
    echo "To run manually:"
    echo "  $SCRIPT_DIR/github-daily-check.sh"
    
else
    # For Linux, create crontab entry
    echo "To add to crontab (runs at 9:00 AM daily):"
    echo "  crontab -e"
    echo "  Add: 0 9 * * * $SCRIPT_DIR/github-daily-check.sh"
fi

echo ""
echo "Setup complete! The health check will:"
echo "  • Validate GitHub tokens daily"
echo "  • Check MCP server health"
echo "  • Send notifications on failures (macOS)"
echo "  • Log results to logs/daily-health-check.log"