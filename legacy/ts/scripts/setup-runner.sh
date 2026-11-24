#!/bin/bash

# Setup script for GitHub self-hosted runner on Mac Studio

echo "🏃 Setting up GitHub self-hosted runner for MCP Workshop Servers"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is designed for macOS (Mac Studio)"
    exit 1
fi

# Create runner directory
RUNNER_DIR="$HOME/actions-runner"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

# Download latest runner
echo "📥 Downloading latest GitHub Actions runner..."
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/')
curl -o actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz

# Extract runner
echo "📦 Extracting runner..."
tar xzf ./actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz
rm actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz

# Install dependencies
echo "📚 Installing dependencies..."
./bin/installdependencies.sh

# Configure runner
echo "🔧 Configuring runner..."
echo "Please get a runner registration token from:"
echo "https://github.com/slcc2c/mcp-workshop-servers/settings/actions/runners/new"
echo ""
read -p "Enter registration token: " RUNNER_TOKEN

./config.sh --url https://github.com/slcc2c/mcp-workshop-servers \
    --token "$RUNNER_TOKEN" \
    --name "mac-studio-m3-ultra" \
    --labels "self-hosted,macOS,ARM64,mac-studio" \
    --work "_work" \
    --replace

# Create LaunchAgent for auto-start
echo "🚀 Creating LaunchAgent for auto-start..."
cat > ~/Library/LaunchAgents/actions.runner.slcc2c.mcp-workshop-servers.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>actions.runner.slcc2c.mcp-workshop-servers</string>
    <key>ProgramArguments</key>
    <array>
        <string>$RUNNER_DIR/runsvc.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$RUNNER_DIR</string>
    <key>StandardOutPath</key>
    <string>$RUNNER_DIR/runner.log</string>
    <key>StandardErrorPath</key>
    <string>$RUNNER_DIR/runner.err</string>
</dict>
</plist>
EOF

# Load the LaunchAgent
launchctl load ~/Library/LaunchAgents/actions.runner.slcc2c.mcp-workshop-servers.plist

echo "✅ GitHub Actions runner setup complete!"
echo ""
echo "The runner will start automatically on system boot."
echo "To start it now: ./run.sh"
echo "To run as a service: ./svc.sh install && ./svc.sh start"