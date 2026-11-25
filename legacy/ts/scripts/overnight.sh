#!/bin/bash
# Quick launcher for overnight agent collaboration
# Usage: ./overnight.sh [repo_path] [hours]

REPO="${1:-/Users/spencer/repos/mcp-server}"
HOURS="${2:-8}"

echo "🌙 Starting overnight analysis..."
echo "   Repo: $REPO"
echo "   Duration: $HOURS hours"
echo ""

# Verify tools are available
if ! command -v claude &> /dev/null; then
    echo "❌ Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-cli"
    exit 1
fi

if ! command -v codex &> /dev/null; then
    echo "❌ Codex CLI not found. Install with: brew install codex"
    exit 1
fi

# Check Claude Code flags
echo "📋 Testing Claude Code..."
claude --help | head -5

echo ""
echo "📋 Testing Codex..."
codex --help 2>&1 | head -5

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Starting in 5 seconds... (Ctrl+C to cancel)"
sleep 5

# Run in foreground (or use nohup/tmux for background)
python3 "$(dirname "$0")/overnight-agents.py" --repo "$REPO" --hours "$HOURS"
