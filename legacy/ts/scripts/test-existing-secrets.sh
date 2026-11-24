#!/bin/bash
# Test integration with your existing vault entries

echo "🔐 Testing Your Existing 1Password Entries"
echo "=========================================="
echo

# Check authentication
if ! op account list &> /dev/null; then
    echo "📝 Signing in to 1Password..."
    op signin
fi

echo "✅ Connected to 1Password"
echo

# List entries in AI vault
echo "🤖 AI Vault Contents:"
echo "--------------------"
op item list --vault=AI --format=json | jq -r '.[] | "  - " + .title + " (" + .category + ")"' 2>/dev/null || echo "  Error listing items"
echo

# List entries in Server-Configurations vault
echo "🖥️  Server-Configurations Vault Contents:"
echo "---------------------------------------"
op item list --vault=Server-Configurations --format=json | jq -r '.[] | "  - " + .title + " (" + .category + ")"' 2>/dev/null || echo "  Error listing items"
echo

# Test retrieving some common fields
echo "🧪 Testing Secret Retrieval:"
echo "---------------------------"
echo

# Function to safely test a secret
test_secret() {
    local vault=$1
    local item=$2
    local field=$3
    local reference="1password:$vault/$item:$field"
    
    echo -n "Testing $reference ... "
    
    if op item get "$item" --vault="$vault" --fields="$field" &> /dev/null; then
        echo "✅ Found"
        echo "  Reference: $reference"
    else
        # Try without field (might be a different field name)
        if op item get "$item" --vault="$vault" &> /dev/null; then
            echo "⚠️  Item exists but field '$field' not found"
            echo "  Available fields:"
            op item get "$item" --vault="$vault" --format=json | jq -r '.fields[]? | select(.value != null) | "    - " + .label' 2>/dev/null || true
        else
            echo "❌ Not found"
        fi
    fi
    echo
}

# Test common patterns in AI vault
echo "From AI vault:"
test_secret "AI" "GitHub" "token"
test_secret "AI" "OpenAI" "api_key"
test_secret "AI" "Anthropic" "api_key"

# Test common patterns in Server-Configurations
echo "From Server-Configurations vault:"
test_secret "Server-Configurations" "postgres" "url"
test_secret "Server-Configurations" "postgresql" "url"
test_secret "Server-Configurations" "database" "postgres_url"
test_secret "Server-Configurations" "redis" "url"

echo
echo "📝 Update your .env file with the correct references:"
echo "===================================================="
echo
echo "Based on what's in your vaults, update .env with references like:"
echo
echo "# From AI vault"
echo "GITHUB_TOKEN=1password:AI/[YourGitHubItemName]:[fieldname]"
echo "OPENAI_API_KEY=1password:AI/[YourOpenAIItemName]:[fieldname]"
echo
echo "# From Server-Configurations vault"
echo "POSTGRES_URL=1password:Server-Configurations/[YourPostgresItemName]:[fieldname]"
echo
echo "💡 Tip: Use the exact item names and field names shown above"