#!/bin/bash
# Quick setup script for 2-vault configuration

set -e

echo "🔐 Setting up 1Password with 2 Vaults"
echo "===================================="
echo

# Check if op CLI is installed
if ! command -v op &> /dev/null; then
    echo "❌ 1Password CLI not found!"
    echo "Installing with Homebrew..."
    brew install --cask 1password-cli
fi

echo "✅ 1Password CLI: $(op --version)"
echo

# Get vault names
echo "📁 Listing your available vaults..."
echo

if op vault list &> /dev/null 2>&1; then
    echo "Your vaults:"
    op vault list --format=json | jq -r '.[].name' | sed 's/^/  - /'
    echo
else
    echo "Please sign in first:"
    op signin
    echo
    echo "Your vaults:"
    op vault list --format=json | jq -r '.[].name' | sed 's/^/  - /'
    echo
fi

# Get the two vault names
read -p "Enter your FIRST vault name: " VAULT1
read -p "Enter your SECOND vault name: " VAULT2

# Create .env file
echo
echo "📝 Creating .env configuration..."

cat > .env << EOF
# MCP Workshop Servers Environment Configuration
# Generated on $(date)

# Basic Configuration
NODE_ENV=development
PORT=3000
LOG_LEVEL=info

# 1Password Configuration (2 Vaults)
ONEPASSWORD_ALLOWED_VAULTS=$VAULT1,$VAULT2
ONEPASSWORD_VAULT=$VAULT1                    # Default vault

# Secrets Management
SECRETS_DEFAULT_PROVIDER=1password
SECRETS_CACHE_ENABLED=true
SECRETS_CACHE_TTL=300

# Example Secret References
# GITHUB_TOKEN=1password:GitHub:token
# DATABASE_URL=1password:$VAULT1/Database:url
# API_KEY=1password:$VAULT2/API:key

# File System Configuration  
ALLOWED_PATHS=$HOME/repos
MAX_FILE_SIZE=10485760

# Performance
MAX_CONCURRENT_OPERATIONS=10
REQUEST_TIMEOUT=30000
CACHE_TTL=3600
EOF

echo "✅ Created .env file with your vault configuration"
echo

# Show example items in vaults
echo "📋 Checking for existing secrets in your vaults..."
echo

for vault in "$VAULT1" "$VAULT2"; do
    echo "Vault: $vault"
    if op item list --vault="$vault" --format=json 2>/dev/null | jq -r '.[].title' | head -5 > /tmp/vault_items; then
        if [ -s /tmp/vault_items ]; then
            cat /tmp/vault_items | sed 's/^/  - /'
            item_count=$(op item list --vault="$vault" --format=json 2>/dev/null | jq length)
            if [ $item_count -gt 5 ]; then
                echo "  ... and $((item_count - 5)) more items"
            fi
        else
            echo "  (empty)"
        fi
    else
        echo "  (unable to list)"
    fi
    echo
done

# Create example secrets
echo "🔑 Would you like to create example secrets for testing?"
read -p "Create examples? (y/n): " CREATE_EXAMPLES

if [[ "$CREATE_EXAMPLES" == "y" ]]; then
    echo
    echo "Creating example secrets..."
    
    # GitHub token
    if ! op item get "GitHub" --vault="$VAULT1" &> /dev/null; then
        echo "Creating GitHub token in $VAULT1..."
        echo "Enter a GitHub personal access token (or press Enter to skip):"
        read -s GITHUB_TOKEN_VALUE
        if [ ! -z "$GITHUB_TOKEN_VALUE" ]; then
            echo "$GITHUB_TOKEN_VALUE" | op item create \
                --category=password \
                --title="GitHub" \
                --vault="$VAULT1" \
                token[password]=- \
                notes="GitHub personal access token for MCP servers"
            echo "✅ Created GitHub token"
        fi
    else
        echo "✅ GitHub item already exists in $VAULT1"
    fi
    
    # Example API key
    if ! op item get "MCP-API" --vault="$VAULT2" &> /dev/null; then
        echo
        echo "Creating example API key in $VAULT2..."
        EXAMPLE_KEY="mcp_$(openssl rand -hex 16)"
        echo "$EXAMPLE_KEY" | op item create \
            --category=password \
            --title="MCP-API" \
            --vault="$VAULT2" \
            key[password]=- \
            notes="Example API key for MCP demonstration"
        echo "✅ Created MCP-API key"
    fi
fi

# Test configuration
echo
echo "🧪 Testing configuration..."
echo

# Create test script
cat > test-secrets.js << 'EOF'
const http = require('http');

async function testSecret(reference) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 3000,
      path: '/api/v1/secrets/get',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          resolve(result);
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.write(JSON.stringify({ reference }));
    req.end();
  });
}

// Test after servers are running
console.log('Run this after starting MCP servers:');
console.log('  npm run mcp:start');
console.log('  node test-secrets.js');
EOF

# Final instructions
echo
echo "✅ Setup Complete!"
echo "================="
echo
echo "Your configuration:"
echo "  Default vault: $VAULT1"
echo "  Allowed vaults: $VAULT1, $VAULT2"
echo
echo "📚 Next steps:"
echo
echo "1. Start the MCP servers:"
echo "   npm run mcp:start"
echo
echo "2. Test secret access:"
echo "   node examples/secrets/secrets-demo.js test 1password:GitHub:token"
echo
echo "3. Use in your .env:"
echo "   GITHUB_TOKEN=1password:GitHub:token"
echo "   DATABASE_URL=1password:$VAULT1/Database:url"
echo "   API_KEY=1password:$VAULT2/MCP-API:key"
echo
echo "4. Reference secrets in code:"
echo "   const token = await secureConfig.get('GITHUB_TOKEN');"
echo

# Cleanup
rm -f /tmp/vault_items