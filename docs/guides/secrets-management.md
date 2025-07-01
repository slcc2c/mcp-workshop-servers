# Secrets Management Guide

The MCP Workshop Servers support advanced secrets management with multiple providers, including 1Password integration for secure credential storage and retrieval.

## Overview

The secrets management system provides:

- **Multiple Providers**: Environment variables, 1Password, AWS Secrets Manager, HashiCorp Vault, Azure Key Vault
- **Automatic Resolution**: Secrets are resolved transparently when accessed
- **Caching**: Configurable TTL-based caching to reduce provider calls
- **Audit Logging**: Track secret access and operations
- **Secure References**: Use special syntax to reference secrets from different providers

## Quick Start with 1Password

### 1. Install 1Password CLI

```bash
# macOS
brew install --cask 1password-cli

# Verify installation
op --version
```

### 2. Configure 1Password

#### Option A: Service Account (Recommended for Servers)

```bash
# Create a service account in 1Password
# Get the token and set it
export ONEPASSWORD_SERVICE_ACCOUNT_TOKEN="ops_..."
```

#### Option B: 1Password Connect

```bash
# For self-hosted 1Password Connect
export ONEPASSWORD_CONNECT_HOST="https://your-connect-server"
export ONEPASSWORD_CONNECT_TOKEN="your-connect-token"
```

#### Option C: Interactive Login

```bash
# Sign in interactively (for development)
op signin
```

### 3. Set Up Secrets in 1Password

Create items in 1Password for your secrets:

```bash
# Create GitHub token
op item create --category=password \
  --title="GitHub" \
  --vault="Development" \
  token[password]="ghp_your_token_here"

# Create database URL
op item create --category=database \
  --title="Database/postgres" \
  --vault="Development" \
  url[password]="postgresql://user:pass@localhost/db"
```

### 4. Configure MCP Servers

```bash
# Enable 1Password provider
export SECRETS_DEFAULT_PROVIDER=1password
export ONEPASSWORD_VAULT=Development

# Or use environment variables with secret references
export GITHUB_TOKEN="1password:GitHub:token"
export POSTGRES_URL="1password:Database/postgres:url"
```

## Secret Reference Syntax

### Basic Format

```
provider:path:field
```

Examples:
- `env:GITHUB_TOKEN` - Environment variable
- `1password:GitHub:token` - 1Password item field
- `aws:my-secret:api-key` - AWS Secrets Manager
- `vault:secret/data/app:token` - HashiCorp Vault

### URL Format

```
secret://provider/path/field
```

Examples:
- `secret://1password/GitHub/token`
- `secret://aws/prod/database-url`

## Configuration

### Environment Variables

```bash
# Secrets management configuration
SECRETS_DEFAULT_PROVIDER=1password      # Default: environment
SECRETS_CACHE_ENABLED=true             # Default: true
SECRETS_CACHE_TTL=300                  # Default: 300 (5 minutes)

# 1Password configuration
ONEPASSWORD_VAULT=Development          # Optional: default vault
ONEPASSWORD_ALLOWED_VAULTS=Development,Staging  # Optional: restrict access
ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=...  # For service accounts
ONEPASSWORD_CONNECT_HOST=...           # For Connect server
ONEPASSWORD_CONNECT_TOKEN=...          # Connect authentication
```

### Server Configuration

```json
{
  "secrets": {
    "defaultProvider": "1password",
    "providers": [
      {
        "type": "1password",
        "enabled": true,
        "config": {
          "vault": "Development",
          "cacheTtl": 300
        }
      }
    ],
    "cache": {
      "enabled": true,
      "maxSize": 100,
      "ttl": 300
    },
    "audit": {
      "enabled": true,
      "logAccess": false,
      "logRotation": true
    }
  }
}
```

## Usage Examples

### Direct Secret Access

```javascript
// Using the secrets manager directly
const secretsManager = getSecretsManager();

// Get a secret
const token = await secretsManager.getSecret('1password:GitHub:token');

// Get multiple secrets
const secrets = await secretsManager.getSecrets([
  'GITHUB_TOKEN',
  '1password:Database/postgres:url',
  'env:API_KEY'
]);
```

### Configuration Integration

```javascript
// Automatic resolution in configuration
const config = await secureConfig.get('GITHUB_TOKEN');
// If GITHUB_TOKEN="1password:GitHub:token", it will be resolved

// Server-specific secrets
const githubSecrets = await secureConfig.getServerSecrets('github');
// Returns all resolved secrets for the GitHub server
```

### Using in MCP Servers

```typescript
// In your server implementation
class MyServer extends BaseMCPServer {
  async initialize() {
    // Get resolved secret
    const apiKey = await this.config.get('API_KEY');
    
    // Initialize with secret
    this.client = new ApiClient({ apiKey });
  }
}
```

## Vault Scoping & Security

### Vault Access Control

The 1Password integration supports multiple levels of vault scoping:

#### 1. **Default Vault**
```bash
# All operations use this vault by default
ONEPASSWORD_VAULT=Development
```

#### 2. **Allowed Vaults List**
```bash
# Restrict access to specific vaults only
ONEPASSWORD_ALLOWED_VAULTS=Development,Staging,SharedSecrets
```

#### 3. **Per-Secret Vault**
```bash
# Reference format: 1password:vault/item:field
GITHUB_TOKEN=1password:Development/GitHub:token
PROD_API_KEY=1password:Production/API:key
```

#### 4. **Service Account Scoping**
When creating service accounts, limit vault access:
- Development SA → Development vault only
- Production SA → Production vault only
- CI/CD SA → CI vault + specific shared vaults

### Example: Multi-Environment Setup

```bash
# Development environment
ONEPASSWORD_VAULT=Development
ONEPASSWORD_ALLOWED_VAULTS=Development,Shared
ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=ops_dev_...

# Staging environment  
ONEPASSWORD_VAULT=Staging
ONEPASSWORD_ALLOWED_VAULTS=Staging,Shared
ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=ops_staging_...

# Production environment
ONEPASSWORD_VAULT=Production
ONEPASSWORD_ALLOWED_VAULTS=Production
ONEPASSWORD_SERVICE_ACCOUNT_TOKEN=ops_prod_...
```

## Security Best Practices

### 1. Use Least Privilege

- Create separate 1Password vaults for different environments
- Use service accounts with minimal permissions
- Restrict secret access to specific servers
- Enable vault allowlists in production

### 2. Rotate Secrets Regularly

```bash
# Rotate a secret in 1Password
op item edit GitHub token[password]="new_token_here"

# Clear the cache to use new value immediately
npm run mcp:secrets:refresh
```

### 3. Audit Secret Access

Enable audit logging to track secret usage:

```json
{
  "secrets": {
    "audit": {
      "enabled": true,
      "logAccess": true,
      "logRotation": true
    }
  }
}
```

### 4. Environment-Specific Configuration

```bash
# Development
export ONEPASSWORD_VAULT=Development
export SECRETS_CACHE_TTL=3600  # Longer cache for dev

# Production
export ONEPASSWORD_VAULT=Production
export SECRETS_CACHE_TTL=60    # Shorter cache for prod
export SECRETS_AUDIT_ENABLED=true
```

## Troubleshooting

### 1Password CLI Not Found

```bash
# Check installation
which op

# Add to PATH if needed
export PATH="/usr/local/bin:$PATH"
```

### Authentication Issues

```bash
# Check if signed in
op account list

# For service accounts, verify token
op whoami
```

### Secret Not Found

```bash
# List available items
op item list --vault=Development

# Check specific item
op item get GitHub --vault=Development
```

### Cache Issues

```bash
# Clear secrets cache
curl -X POST http://localhost:3000/api/v1/secrets/cache/clear

# Check cache stats
curl http://localhost:3000/api/v1/secrets/cache/stats
```

## Migration Guide

### From Environment Variables

1. **Create 1Password items** for existing secrets:
   ```bash
   # For each secret in .env
   op item create --category=password \
     --title="MyApp/github-token" \
     --vault="Development" \
     value[password]="$GITHUB_TOKEN"
   ```

2. **Update references** in your configuration:
   ```bash
   # Old
   GITHUB_TOKEN=ghp_actual_token
   
   # New
   GITHUB_TOKEN=1password:MyApp/github-token:value
   ```

3. **Test resolution**:
   ```bash
   npm run mcp:secrets:test
   ```

### Gradual Migration

You can migrate gradually by using the fallback chain:

```javascript
// This will try in order:
// 1. Direct environment variable
// 2. Secret reference resolution
// 3. Default value
const token = await secureConfig.get('GITHUB_TOKEN', 'default-token');
```

## API Reference

### Secrets Manager

```typescript
class SecretsManager {
  // Get a single secret
  getSecret(reference: string | SecretReference): Promise<string>
  
  // Get multiple secrets
  getSecrets(references: Array<string | SecretReference>): Promise<Map<string, string>>
  
  // List available secrets
  listSecrets(provider?: SecretProvider, prefix?: string): Promise<SecretMetadata[]>
  
  // Cache management
  clearCache(): void
  getCacheStats(): CacheStats
  
  // Provider management
  getAvailableProviders(): SecretProvider[]
  isProviderAvailable(provider: SecretProvider): Promise<boolean>
}
```

### Secure Config Manager

```typescript
class SecureConfigManager {
  // Get configuration value with secret resolution
  get<T>(key: string, defaultValue?: T): Promise<T>
  
  // Get specific secrets
  getGitHubToken(): Promise<string | undefined>
  getDatabaseUrl(db: string): Promise<string | undefined>
  getServerSecrets(serverName: string): Promise<Record<string, string>>
  
  // Management
  refreshSecrets(): Promise<void>
  getSecretsManager(): SecretsManager | undefined
}
```

## Next Steps

- [Security Architecture](../architecture/security.md) - Learn about the security model
- [Server Development](./custom-servers.md) - Build servers with secrets support
- [API Documentation](../api/secrets.md) - Complete API reference