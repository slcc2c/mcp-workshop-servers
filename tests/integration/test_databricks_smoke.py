"""Opt-in read-only Databricks Unity Catalog smoke test against configured profile."""

from __future__ import annotations

import os

import pytest

from mcp_stack.core.config import load_settings
from mcp_stack.servers.unity_catalog import UCClientAdapter

pytestmark = pytest.mark.databricks


async def test_databricks_unity_catalog_read_only_probe() -> None:
    settings = load_settings()
    settings.unity_catalog.mode = "databricks"
    settings.unity_catalog.databricks_profile = os.getenv(
        "UC_DATABRICKS_PROFILE", "dbc-c2cf8933-0714"
    )
    adapter = UCClientAdapter(settings)
    result = await adapter.databricks_probe()
    assert result["ok"] is True, f"Databricks probe failed: {result}"
