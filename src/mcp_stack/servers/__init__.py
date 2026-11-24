"""FastMCP server implementations for the modern MLflow + Unity Catalog stack."""

from mcp_stack.servers.docker_server import create_docker_server
from mcp_stack.servers.filesystem import create_filesystem_server
from mcp_stack.servers.github import create_github_server
from mcp_stack.servers.memory import create_memory_server
from mcp_stack.servers.mlflow_server import (
    create_mlflow_server,
    create_mlflow_upstream_proxy,
    probe_mcp_http_endpoint,
)
from mcp_stack.servers.photos import create_photos_server
from mcp_stack.servers.unity_catalog import create_unity_catalog_server, sync_uc_function_tools

__all__ = [
    "create_docker_server",
    "create_filesystem_server",
    "create_github_server",
    "create_memory_server",
    "create_mlflow_server",
    "create_mlflow_upstream_proxy",
    "create_photos_server",
    "create_unity_catalog_server",
    "probe_mcp_http_endpoint",
    "sync_uc_function_tools",
]
