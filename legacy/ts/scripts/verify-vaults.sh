#!/bin/bash
# Verify AI and Server-Configurations vaults setup

echo "🔐 Verifying 1Password Vault Configuration"
echo "=========================================="
echo
echo "Configured vaults: AI, Server-Configurations"
echo

# Check if signed in
if ! op account list &> /dev/null; then
    echo "📝 Not signed in. Signing in..."
    op signin
fi

# Verify vaults exist
echo "✅ Checking vault access..."
echo

for vault in "AI" "Server-Configurations"; do
    echo "Vault: $vault"
    if op vault get "$vault" &> /dev/null; then
        echo "  ✅ Accessible"
        
        # Count items
        item_count=$(op item list --vault="$vault" --format=json 2>/dev/null | jq length || echo "0")
        echo "  📄 Items: $item_count"
        
        # List first few items
        if [ "$item_count" -gt 0 ]; then
            echo "  📋 Recent items:"
            op item list --vault="$vault" --format=json | jq -r '.[0:3] | .[] | "     - " + .title' 2>/dev/null || true
        fi
    else
        echo "  ❌ Not found or not accessible"
        echo "  💡 Create it in 1Password app or web interface"
    fi
    echo
done

# Suggest common secrets for each vault
echo "💡 Suggested Secrets Structure:"
echo "==============================="
echo
echo "AI Vault (for API keys and tokens):"
echo "  - GitHub (with 'token' field)"
echo "  - OpenAI (with 'api_key' field)"
echo "  - Anthropic (with 'api_key' field)"
echo "  - HuggingFace (with 'token' field)"
echo
echo "Server-Configurations Vault (for infrastructure):"
echo "  - Database/postgres (with 'url' field)"
echo "  - Database/redis (with 'url' field)"
echo "  - Database/mongodb (with 'url' field)"
echo "  - Auth (with 'secret' field)"
echo "  - Docker (with 'registry_token' field)"
echo

# Quick test
echo "🧪 Quick Test Commands:"
echo "======================="
echo
echo "# List items in AI vault:"
echo "op item list --vault=AI"
echo
echo "# Create a GitHub token in AI vault:"
echo 'op item create --vault=AI --title=GitHub --category=password token[password]="ghp_your_token"'
echo
echo "# Get a secret value:"
echo "op item get GitHub --vault=AI --fields=token"
echo