#!/bin/bash
# 1Password setup script for MCP Servers

set -e

echo "🔐 1Password Setup for MCP Servers"
echo "================================="
echo

# Check if op CLI is installed
if ! command -v op &> /dev/null; then
    echo "❌ 1Password CLI not found!"
    echo
    echo "Please install it first:"
    echo "  brew install --cask 1password-cli"
    echo
    echo "Or download from: https://developer.1password.com/docs/cli/get-started/"
    exit 1
fi

echo "✅ 1Password CLI found: $(op --version)"
echo

# Check authentication status
echo "Checking authentication status..."
if op account list &> /dev/null; then
    echo "✅ Already signed in to 1Password"
    SIGNED_IN=true
else
    echo "📝 Not signed in to 1Password"
    SIGNED_IN=false
fi

echo
echo "Choose setup method:"
echo "1. Service Account (recommended for automation)"
echo "2. 1Password Connect (for self-hosted)"
echo "3. Interactive login (for development)"
echo
read -p "Enter choice (1-3): " CHOICE

case $CHOICE in
    1)
        echo
        echo "🔑 Service Account Setup"
        echo "========================"
        echo
        echo "1. Create a service account at: https://my.1password.com/developer-tools/infrastructure-secrets/serviceaccount"
        echo "2. Grant access to the vaults containing your secrets"
        echo "3. Copy the service account token"
        echo
        read -p "Enter service account token (ops_...): " SERVICE_TOKEN
        
        if [[ ! "$SERVICE_TOKEN" =~ ^ops_ ]]; then
            echo "❌ Invalid service account token format"
            exit 1
        fi
        
        echo
        echo "Add to your .env file:"
        echo "ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=$SERVICE_TOKEN"
        echo "SECRETS_DEFAULT_PROVIDER=1password"
        
        # Test the token
        export OP_SERVICE_ACCOUNT_TOKEN="$SERVICE_TOKEN"
        if op vault list &> /dev/null; then
            echo
            echo "✅ Service account configured successfully!"
        else
            echo
            echo "❌ Failed to authenticate with service account"
            exit 1
        fi
        ;;
        
    2)
        echo
        echo "🌐 1Password Connect Setup"
        echo "========================="
        echo
        echo "Enter your 1Password Connect server details:"
        read -p "Connect Host (e.g., https://connect.example.com): " CONNECT_HOST
        read -p "Connect Token: " CONNECT_TOKEN
        
        echo
        echo "Add to your .env file:"
        echo "ONEPASSWORD_CONNECT_HOST=$CONNECT_HOST"
        echo "ONEPASSWORD_CONNECT_TOKEN=$CONNECT_TOKEN"
        echo "SECRETS_DEFAULT_PROVIDER=1password"
        ;;
        
    3)
        echo
        echo "💻 Interactive Login"
        echo "==================="
        echo
        
        if [ "$SIGNED_IN" = false ]; then
            echo "Please sign in to 1Password:"
            op signin
        fi
        
        echo
        echo "✅ Ready for development use!"
        echo
        echo "Note: Interactive login is not suitable for production."
        echo "Consider using a service account for automation."
        ;;
        
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo
echo "🎯 Next Steps"
echo "============="
echo

# List available vaults
if [ "$SIGNED_IN" = true ] || [ ! -z "$SERVICE_TOKEN" ]; then
    echo "Available vaults:"
    op vault list --format=json 2>/dev/null | jq -r '.[] | "  - \(.name)"' || echo "  (Unable to list vaults)"
    echo
fi

echo "1. Create secrets in 1Password:"
echo "   op item create --category=password --title=\"GitHub\" --vault=\"Development\" token[password]=\"your-github-token\""
echo
echo "2. Reference in your .env file:"
echo "   GITHUB_TOKEN=1password:GitHub:token"
echo
echo "3. Or use direct references:"
echo "   export DATABASE_URL=\"1password:Database/postgres:url\""
echo
echo "4. Test the integration:"
echo "   node examples/secrets/secrets-demo.js"
echo

# Create example .env.1password if it doesn't exist
if [ ! -f .env.1password ]; then
    cat > .env.1password << 'EOF'
# 1Password Integration Configuration
# Copy these to your .env file after setup

# Provider configuration
SECRETS_DEFAULT_PROVIDER=1password
SECRETS_CACHE_ENABLED=true
SECRETS_CACHE_TTL=300

# Choose one authentication method:

# Option 1: Service Account (recommended)
# ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=ops_...

# Option 2: 1Password Connect
# ONEPASSWORD_CONNECT_HOST=https://your-connect-server
# ONEPASSWORD_CONNECT_TOKEN=your-connect-token

# Optional: Specify vault
# ONEPASSWORD_VAULT=Development

# Example secret references
# GITHUB_TOKEN=1password:GitHub:token
# POSTGRES_URL=1password:Database/postgres:url
# REDIS_URL=1password:Database/redis:url
# API_KEY=1password:MyApp/api:key
EOF
    echo "📄 Created .env.1password with example configuration"
fi

echo
echo "✨ Setup complete!"