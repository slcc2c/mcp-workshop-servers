# MCP Workshop Stack (Modern Python FastMCP + MLflow 3.x + Unity Catalog)

A modern Python 3.12 (`uv`) Model Context Protocol ecosystem built on **FastMCP 3.x**, **FastAPI**, **MLflow 3.x**, and **Unity Catalog**, aligned with the `Server-Configs` / Atelier stack.

> [!NOTE]
> The previous TypeScript/Node prototype has been recoverably quarantined under [`legacy/ts/`](./legacy/ts/).

## Architecture

- **Unified Gateway (`:8090`)**: FastAPI + FastMCP Streamable HTTP gateway exposing:
  - `/mcp` — Full composed MCP endpoint across all enabled servers
  - `/profiles/{core,data,ops,macos}/mcp` — Curated toolset profiles (`MCP_DEFAULT_CLIENT_PROFILE=core` default for Codex/Claude Code to keep context lean; override via `MCP_PROFILES_JSON`)
  - `/servers/<slug>/mcp` — Isolated per-server Streamable HTTP endpoints
  - Zero-`307` path normalization on `/mcp`, `/profiles/<name>/mcp`, and `/servers/<slug>/mcp`
  - `/ui` self-contained interactive Gateway Dashboard + `/health`, `/ready`, `/api/v1/{servers,profiles,tools,watchdog,traces}`, `/api/v1/actions/*`, and `/metrics` (Prometheus)
  - Pure ASGI Bearer auth (auto-enforced on non-loopback binds), client server allowlists, rate limiting, and `X-UC-Token` on-behalf-of passthrough
  - Fail-open MLflow 3.x `SpanType.TOOL` tracing middleware with sensitive-key redaction and a 60s circuit breaker
- **Modern Data & AI Governance Servers**:
  - **`unity-catalog`**: OSS Unity Catalog REST API 2.1 (`localhost:8082`) + Databricks UC switch (`UC_MODE=databricks` with Databricks SDK Files API support for `/Volumes/...`), `unitycatalog-ai` function execution with schema allowlists (`UC_FUNCTION_ALLOWLIST`), dynamic UC function tools (`uc_fn_*`), UC Volume creation & mapping (`UC_VOLUME_LOCAL_PREFIX_MAP`), MLflow lineage cross-linking (`uc_get_model_lineage`), and opt-in mutations (`UC_ALLOW_MUTATIONS=true`).
  - **`mlflow`**: Complementary MLflow 3.x tools (experiments, runs, `mlflow_compare_runs`, `LoggedModel`s, Prompt Registry + `mlflow_get_prompt_versions`, UC Model Registry aliases + metric-gated `mlflow_promote_model_alias`, Eval Datasets) + resilient proxy to `mlflow[mcp]` (`localhost:9012/mcp`).
- **Ported Tier-1, Tier-2 & Host Servers**:
  - **`memory`**: SQLite + FTS5 persistent knowledge graph with `data/memory.json` auto-import and bidirectional UC Volume sync (`memory_export` + `memory_import`).
  - **`filesystem`**: Strict `Path.resolve().is_relative_to()` sandboxing and symlink-escape protection.
  - **`github`**: Async GitHub REST API v3 client with lazy token resolution (`env:` / optional 1Password `op://`).
  - **`docker`**: Docker Engine container lifecycle management with image allowlists and default resource limits.
  - **`postgresql`**, **`redis`**, **`mongodb`**, **`neo4j`**, **`kubernetes`**, **`jupyter`**: Lazy-connecting Phase 2 servers (all read-only / execution-disabled by default; `*_ALLOW_MUTATIONS=true` or `JUPYTER_ALLOW_EXECUTION=true` to write).
  - **`photos`** & **`xcodebuild`** (macOS host-only): Apple Photos discovery/export (`PHOTOS_EXPORT_ROOT`) and Xcode/SwiftPM/CoreSimulator tools (`XCODE_ALLOW_MUTATIONS=true` for builds/launches).

## Quick Start

```bash
# 1. Install Python 3.12 environment with uv
uv sync --extra dev

# 2. Configure environment
cp .env.example .env

# 3. Check local Atelier MLflow, mlflow[mcp], Unity Catalog, and Docker readiness
uv run mcp-stack doctor

# 4. Start the unified Streamable HTTP gateway on http://127.0.0.1:8090
uv run mcp-stack serve gateway

# Or run any individual server over stdio (stdout stays 100% JSON-RPC clean)
uv run mcp-stack serve unity-catalog --transport stdio
uv run mcp-stack serve photos --transport stdio
```

## MLflow MCP Registry & Client Configs

```bash
# Generate open MCP Registry server.json manifests under manifests/
uv run mcp-stack registry sync --dry-run

# Sync manifests into MLflow 3.15+ MCP Registry
uv run mcp-stack registry sync

# Generate / update configs for Claude Code, Claude Desktop, Codex, and Cursor
uv run mcp-stack config generate --target all --write

# Safely merge into live host client configs (creates .bak-<timestamp> backups; defaults to /profiles/core/mcp)
uv run mcp-stack config install --client codex --client claude-code --client claude-desktop

# Install guarded silent token-autoload block into ~/.zshrc (creates backup)
uv run mcp-stack config install-shell-hook

# Manage LaunchAgents, 60s background watchdog & log rotation (~/Library/Logs/mcp-workshop-stack/)
uv run mcp-stack service status
uv run mcp-stack service install
uv run mcp-stack service restart
uv run mcp-stack service watchdog-once
uv run mcp-stack service rotate-logs --max-mb 10

# Bootstrap clean UC workshop catalog + external volume + sample UDFs
uv run mcp-stack uc bootstrap

# Evaluate recent gateway traces & run golden GenAI benchmark (optional local Ollama judge)
uv run mcp-stack eval sync-dataset
uv run mcp-stack eval sync-scorers
uv run mcp-stack eval benchmark
uv run mcp-stack eval run --experiment mcp-workshop-servers --limit 20
# uv run mcp-stack eval run --with-llm-judge --judge-model ollama:/qwen3.8:27b
```

> [!NOTE]
> Visit `http://127.0.0.1:8090/ui` when the gateway is running for the interactive Web Dashboard (status cards, searchable tool browser, watchdog history, MLflow traces/evals, and Bearer-protected operational actions).

> [!NOTE]
> When `MCP_AUTH_ENABLED=true`, generated configs in [`.mcp.json`](file:///Users/spencer/repos/mcp-server/.mcp.json), [`cursor-mcp-config.json`](file:///Users/spencer/repos/mcp-server/cursor-mcp-config.json), and [`config/codex-mcp-snippet.toml`](file:///Users/spencer/repos/mcp-server/config/codex-mcp-snippet.toml) reference env-var Bearer tokens (`${MCP_CLAUDE_AUTH_TOKEN}`, `${env:MCP_CURSOR_AUTH_TOKEN}`, `MCP_CODEX_AUTH_TOKEN`) with zero plaintext secrets stored on disk.

## Native macOS LaunchAgents (Recommended on macOS)

For full host `mlflow[mcp]` composition, live MLflow `:5002` tracing, and macOS `photos_*` support alongside containerized OSS Unity Catalog (`:8082`), install the launchd wrappers from `deploy/launchd/`:

```bash
mkdir -p ~/Library/Logs/mcp-workshop-stack
cp deploy/launchd/com.spencer.mcp-mlflow-mcp.plist ~/Library/LaunchAgents/
cp deploy/launchd/com.spencer.mcp-workshop-gateway.plist ~/Library/LaunchAgents/
```

Logs are written to `~/Library/Logs/mcp-workshop-stack/`. Secrets remain in `.env` (gitignored), never inside `.plist` or wrapper files.

## Docker Deployment

```bash
# Attach to existing atelier-core network (reaches host Atelier MLflow 5002/9012)
docker compose up -d --build

# Standalone mode with optional OSS Unity Catalog (:8082 if :8080 is busy)
UC_PORT=8082 EXECUTOR_MAX_MEMORY_LIMIT=4096 docker compose -f docker-compose.yml -f docker-compose.standalone.yml --profile uc up -d

# Optional Tier-2 dev databases (postgres:15432, redis:16379, mongodb:27018, neo4j:17474/17687)
docker-compose -f docker-compose.yml -f docker-compose.standalone.yml --profile tier2 up -d postgres redis mongodb neo4j
```

> [!NOTE]
> MLflow 3.x enables DNS-rebinding `Host` header validation (`--allowed-hosts`) by default, allowing only `localhost` and RFC-1918 private IPs. On macOS with OrbStack or Docker Desktop, `host.docker.internal` can trigger HTTP `403 Invalid Host header` when hitting a native host `:5002` MLflow server. Choose one of three supported topologies:
> 1. **Native macOS gateway + Docker UC** *(full MLflow tracing + host-only `photos`)*: keep `unity-catalog` in Docker (`UC_PORT=8082`) and run `uv run mcp-stack serve gateway` directly on macOS against `http://localhost:5002`.
> 2. **Containerized gateway + host MLflow**: start your host MLflow server with `--allowed-hosts "localhost:*,127.0.0.1:*,host.docker.internal:*"`.
> 3. **Compose-managed MLflow**: run `--profile mlflow` with an alternate host port if `:5002` is in use (`MLFLOW_SERVER_PORT=5003 DOCKER_MLFLOW_TRACKING_URI=http://mlflow-server:5002 docker compose -f docker-compose.yml -f docker-compose.standalone.yml --profile uc --profile mlflow up -d`).

## Testing & Quality

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not live and not databricks and not tier2" -v
uv run pytest -m tier2 -v       # Live integration tests against --profile tier2 containers
uv run pytest -m live -v         # Live probes against running MLflow & OSS UC
uv run pytest -m databricks -v   # Opt-in read-only probe against UC_DATABRICKS_PROFILE
```

## Phase 4 Status

- All Phase 1–4 deliverables are implemented: Python 3.12 FastMCP 3.x servers, curated profiles, 60s macOS watchdog, MLflow 3.x golden evals & local Ollama judge support, Databricks UC Files API volume sync, `--profile tier2` dev compose stack, and Gateway `/ui` dashboard.
