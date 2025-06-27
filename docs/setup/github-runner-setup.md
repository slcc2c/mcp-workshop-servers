# GitHub Self-Hosted Runner Setup for Mac Studio

This guide walks through setting up a self-hosted GitHub Actions runner on your Mac Studio M3 Ultra to leverage local computing power for CI/CD workflows.

## Benefits of Self-Hosted Runners

- **Performance**: Utilize Mac Studio M3 Ultra's processing power
- **Cost**: No GitHub Actions minutes consumed
- **Control**: Full control over runner environment
- **Speed**: No queue times, instant job execution
- **Cache**: Persistent local caches between runs

## Prerequisites

- macOS 13.0 or later
- Admin access to the repository
- Homebrew installed
- At least 10GB free disk space

## Quick Setup

1. **Run the setup script**:
   ```bash
   ./scripts/setup-runner.sh
   ```

2. **Get a registration token**:
   - Navigate to: https://github.com/slcc2c/mcp-workshop-servers/settings/actions/runners/new
   - Copy the registration token
   - Paste when prompted by the script

3. **Verify runner is connected**:
   - Check https://github.com/slcc2c/mcp-workshop-servers/settings/actions/runners
   - You should see "mac-studio-m3-ultra" listed as "Idle"

## Manual Setup (Alternative)

If you prefer manual setup:

```bash
# Create runner directory
mkdir ~/actions-runner && cd ~/actions-runner

# Download runner (Apple Silicon version)
curl -o actions-runner-osx-arm64.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-osx-arm64-2.311.0.tar.gz

# Extract
tar xzf ./actions-runner-osx-arm64.tar.gz

# Configure
./config.sh --url https://github.com/slcc2c/mcp-workshop-servers \
  --token YOUR_TOKEN_HERE \
  --name "mac-studio-m3-ultra" \
  --labels "self-hosted,macOS,ARM64,mac-studio"

# Run
./run.sh
```

## Runner Management

### Start runner as a service:
```bash
cd ~/actions-runner
./svc.sh install
./svc.sh start
```

### Check runner status:
```bash
./svc.sh status
```

### View runner logs:
```bash
tail -f ~/actions-runner/_diag/Runner_*.log
```

### Stop runner:
```bash
./svc.sh stop
```

### Uninstall runner:
```bash
./svc.sh uninstall
./config.sh remove --token YOUR_REMOVAL_TOKEN
```

## Optimizing for Mac Studio

### Parallel job execution:
The Mac Studio can handle multiple parallel jobs. Configure in your workflows:

```yaml
jobs:
  test:
    runs-on: self-hosted
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - run: npm test -- --shard=${{ matrix.shard }}/4
```

### Using Mac-specific features:
```yaml
- name: Use macOS Keychain
  run: security find-generic-password -s "github-token" -w

- name: Leverage GPU acceleration
  run: npm run test:gpu
```

### Caching strategies:
```yaml
- name: Cache dependencies
  uses: actions/cache@v3
  with:
    path: |
      ~/.npm
      ~/.cache
      node_modules
    key: ${{ runner.os }}-deps-${{ hashFiles('**/package-lock.json') }}
```

## Security Considerations

1. **Network isolation**: Runner operates in your local network
2. **Token security**: Registration tokens expire after 1 hour
3. **Access control**: Only repository admins can manage runners
4. **Environment variables**: Stored securely in runner configuration

## Troubleshooting

### Runner not starting:
```bash
# Check for port conflicts
lsof -i :443
# Verify network connectivity
curl https://api.github.com
```

### Permission issues:
```bash
# Fix permissions
chmod -R 755 ~/actions-runner
```

### Runner appears offline:
1. Check internet connectivity
2. Verify firewall settings allow outbound HTTPS
3. Restart the runner service

## Performance Monitoring

Monitor runner performance:
```bash
# CPU usage during builds
top -pid $(pgrep Runner.Listener)

# Disk I/O
iostat -w 1

# Memory pressure
vm_stat 1
```

## Next Steps

- Configure workflow files to use `runs-on: self-hosted`
- Set up runner groups for different workload types
- Implement custom runner images with pre-installed tools
- Configure runner auto-scaling based on queue depth