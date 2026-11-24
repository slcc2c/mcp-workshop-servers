"""Optional live probes against running Atelier MLflow and OSS Unity Catalog."""

from __future__ import annotations

import httpx
import pytest

from mcp_stack.core.config import load_settings
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint

pytestmark = pytest.mark.live


async def test_live_mlflow_and_unity_catalog_reachability() -> None:
    settings = load_settings()

    async with httpx.AsyncClient(timeout=3.0) as client:
        mlflow_api = await client.get(
            f"{settings.mlflow.tracking_uri.rstrip('/')}/api/2.0/mlflow/experiments/search",
            params={"max_results": 1},
        )
        assert mlflow_api.status_code == 200

        uc_catalogs = await client.get(
            f"{settings.unity_catalog.effective_api_base}/catalogs",
            params={"max_results": 5},
        )
        assert uc_catalogs.status_code == 200

    upstream = await probe_mcp_http_endpoint(settings.mlflow.mcp_url, timeout=3.0)
    assert upstream["reachable"] is True
