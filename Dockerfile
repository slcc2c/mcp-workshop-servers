# syntax=docker/dockerfile:1

FROM node:22-slim AS web-builder

WORKDIR /app

RUN npm install -g pnpm@12.23.0

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./web/
RUN pnpm --dir web install --frozen-lockfile

COPY web ./web
RUN pnpm --dir web build


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml .python-version README.md ./
COPY src ./src
COPY --from=web-builder /app/src/mcp_stack/gateway/static ./src/mcp_stack/gateway/static

RUN uv sync --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1001 mcp \
    && useradd -u 1001 -g mcp -m -s /bin/bash mcp

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY pyproject.toml .python-version README.md ./

RUN mkdir -p /app/data /app/manifests && chown -R mcp:mcp /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    EXECUTOR_MAX_MEMORY_LIMIT=4096 \
    UC_EXECUTION_MODE=sandbox \
    MCP_GATEWAY_HOST=0.0.0.0 \
    MCP_GATEWAY_PORT=8090

USER mcp

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["mcp-stack", "serve", "gateway", "--host", "0.0.0.0", "--port", "8090"]
