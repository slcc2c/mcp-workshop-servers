"""Shared pytest fixtures for mcp-workshop-stack tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_stack.core.config import (
    DockerSettings,
    FilesystemSettings,
    GatewaySettings,
    GitHubSettings,
    MCPStackSettings,
    MemorySettings,
    MLflowSettings,
    PhotosSettings,
    SecretsSettings,
    UnityCatalogSettings,
)


@pytest.fixture
def make_settings(tmp_path: Path):
    """Build isolated MCPStackSettings pointing into tmp_path."""

    def _factory(**overrides) -> MCPStackSettings:
        allowed_dir = tmp_path / "workspace"
        allowed_dir.mkdir(parents=True, exist_ok=True)
        photos_dir = tmp_path / "photos_exports"
        photos_dir.mkdir(parents=True, exist_ok=True)

        base = MCPStackSettings(
            _env_file=None,
            gateway=GatewaySettings(
                host="127.0.0.1",
                port=8090,
                auth_enabled=False,
            ),
            mlflow=MLflowSettings(
                tracking_uri="http://mlflow.test:5002",
                mcp_url="http://mlflow.test:9012/mcp",
                experiment_name="test-exp",
                tracing_enabled=False,
                proxy_upstream_mcp=False,
                allow_mutations=False,
            ),
            unity_catalog=UnityCatalogSettings(
                mode="oss",
                base_url="http://uc.test:8080",
                allow_mutations=False,
                enable_function_execution=True,
                dynamic_function_tools=True,
                function_allowlist=["unity.default"],
            ),
            memory=MemorySettings(
                db_path=tmp_path / "memory.db",
                legacy_json_path=tmp_path / "memory.json",
            ),
            filesystem=FilesystemSettings(
                allowed_paths=[allowed_dir],
                max_file_size=1024 * 1024,
            ),
            github=GitHubSettings(
                token=None,
                api_url="https://api.github.test",
            ),
            docker=DockerSettings(),
            photos=PhotosSettings(export_root=photos_dir),
            secrets=SecretsSettings(),
        )
        return base.model_copy(update=overrides)

    return _factory
