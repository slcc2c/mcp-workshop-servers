# MCP Workshop Stack — Developer & Agent Guide

## Stack Overview
This repository implements the modern Python 3.12 (`uv`) **FastMCP + FastAPI + MLflow 3.x + Unity Catalog** MCP stack.
Legacy TypeScript files are preserved recoverably in `legacy/ts/`.

## Key Commands
```bash
# Sync dependencies
uv sync --extra dev

# Run unified Streamable HTTP gateway (127.0.0.1:8090)
uv run mcp-stack serve gateway

# Run individual server over stdio (stderr-only logs, clean JSON-RPC stdout)
uv run mcp-stack serve <server> --transport stdio
# Servers: unity-catalog | mlflow | memory | filesystem | github | docker |
#   postgresql | redis | mongodb | neo4j | kubernetes | jupyter |
#   photos (macOS only) | xcodebuild (macOS only)

# Environment diagnostics & UC bootstrap
uv run mcp-stack doctor
uv run mcp-stack uc bootstrap

# LaunchAgents, log rotation & MLflow GenAI trace evaluation
uv run mcp-stack service status
uv run mcp-stack service restart
uv run mcp-stack eval run --experiment mcp-workshop-servers --limit 20

# Open MCP Registry manifests & MLflow 3.15+ MCP Registry sync
uv run mcp-stack registry sync --dry-run
uv run mcp-stack registry sync

# Client config generation & safe live installation (with backups)
uv run mcp-stack config generate --target all --write
uv run mcp-stack config install --client codex --client claude-code --client claude-desktop

# Quality & tests
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not live and not databricks" -v
```

## Conventions & Guardrails
- **Stdio cleanliness**: Never write logs to `stdout`. All logging goes to `sys.stderr` via `mcp_stack.core.logging`.
- **Safe defaults**: `UC_ALLOW_MUTATIONS=false` and `MLFLOW_ALLOW_MUTATIONS=false` by default; `UC_FUNCTION_ALLOWLIST` defaults to `unity.default`.
- **Gateway auth**: Disabled on loopback (`127.0.0.1`/`localhost`) unless `MCP_AUTH_ENABLED=true`; automatically enforced on non-loopback binds (e.g., `0.0.0.0` in Docker).
- **MLflow tracing**: Fail-open middleware with a 60s circuit breaker (`SpanType.TOOL` under `MLFLOW_EXPERIMENT_NAME`).
- **macOS Photos**: Host-only (`sys.platform == "darwin"`) via `osascript` JXA; requires `PHOTOS_EXPORT_ROOT`.
