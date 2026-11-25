#!/bin/bash
# Diagnostic: Check codex CLI installation and flags

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "CODEX CLI DIAGNOSTIC"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "📍 Which codex:"
which codex

echo ""
echo "📦 Version:"
codex --version 2>&1 || codex -v 2>&1 || echo "(no version flag)"

echo ""
echo "📋 Help output:"
codex --help 2>&1

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "CLAUDE CODE DIAGNOSTIC"  
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "📍 Which claude:"
which claude

echo ""
echo "📦 Version:"
claude --version 2>&1

echo ""
echo "📋 Key flags:"
claude --help 2>&1 | grep -E "(print|dangerously|prompt|-p)" | head -10
