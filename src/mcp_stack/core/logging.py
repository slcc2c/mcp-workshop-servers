"""Stderr-only structured logging configuration safe for stdio MCP transports."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, TextIO, cast

import structlog

# Silence MLflow import-time hint chatter that could pollute logs.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


class _DynamicStderr:
    """Delegate dynamically to sys.stderr so pytest stream replacement never closes it."""

    def write(self, data: str) -> int:
        return sys.stderr.write(data)

    def flush(self) -> None:
        sys.stderr.flush()

    def isatty(self) -> bool:
        return bool(getattr(sys.stderr, "isatty", lambda: False)())


def configure_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure structlog and stdlib logging strictly to sys.stderr."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    for noisy_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        noisy = logging.getLogger(noisy_name)
        noisy.handlers.clear()
        noisy.propagate = True

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=cast(TextIO, _DynamicStderr())),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(service=name)
