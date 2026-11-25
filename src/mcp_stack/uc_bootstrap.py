"""Idempotent OSS Unity Catalog workshop catalog, external volume, and UDF bootstrap."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from typing import Any

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.servers.unity_catalog import UCClientAdapter


def add_numbers(a: int, b: int) -> int:
    """Add two integers and return their sum.

    Args:
        a: First integer.
        b: Second integer.
    Returns:
        Sum of a and b.
    """
    return a + b


def normalize_text(text: str) -> str:
    """Trim whitespace and collapse consecutive spaces in text.

    Args:
        text: Input string to normalize.
    Returns:
        Normalized single-spaced string.
    """
    return " ".join(text.split())


def weighted_score(quality: float, latency_ok: float, weight: float) -> float:
    """Compute a clamped weighted evaluation score between 0.0 and 1.0.

    Args:
        quality: Quality sub-score between 0.0 and 1.0.
        latency_ok: Latency sub-score between 0.0 and 1.0.
        weight: Weight applied to quality (0.0 to 1.0).
    Returns:
        Weighted floating-point score.
    """
    w = min(max(weight, 0.0), 1.0)
    return round(w * quality + (1.0 - w) * latency_ok, 4)


async def _ensure_resource(
    adapter: UCClientAdapter,
    *,
    get_path: str,
    create_path: str,
    create_body: dict[str, Any],
) -> str:
    try:
        await adapter.request("GET", get_path)
        return "exists"
    except Exception:
        await adapter.request("POST", create_path, json_body=create_body)
        return "created"


async def bootstrap_oss_unity_catalog(
    settings: MCPStackSettings,
    *,
    catalog: str = "workshop",
    schema: str = "default",
    volume: str = "memory_snapshots",
    storage_location: str = "file:///home/unitycatalog/etc/data/external/workshop/memory_snapshots",
    adapter: UCClientAdapter | None = None,
    uc_fn_client_factory: Any = None,
) -> dict[str, Any]:
    """Idempotently create clean workshop catalog, schema, volume, and sample Python UDFs."""
    uc_adapter = adapter or UCClientAdapter(settings)
    cat_status = await _ensure_resource(
        uc_adapter,
        get_path=f"catalogs/{catalog}",
        create_path="catalogs",
        create_body={"name": catalog, "comment": "MCP Workshop Python Stack Catalog"},
    )
    schema_status = await _ensure_resource(
        uc_adapter,
        get_path=f"schemas/{catalog}.{schema}",
        create_path="schemas",
        create_body={
            "catalog_name": catalog,
            "name": schema,
            "comment": "Default workshop schema for clean UDFs and volumes",
        },
    )
    volume_full = f"{catalog}.{schema}.{volume}"
    volume_status = await _ensure_resource(
        uc_adapter,
        get_path=f"volumes/{volume_full}",
        create_path="volumes",
        create_body={
            "catalog_name": catalog,
            "schema_name": schema,
            "name": volume,
            "volume_type": "EXTERNAL",
            "storage_location": storage_location,
            "comment": "Host-shared volume for Memory MCP JSON/CSV snapshots",
        },
    )

    sample_funcs = (add_numbers, normalize_text, weighted_score)
    udf_results: dict[str, str] = {}

    if uc_fn_client_factory is not None:
        for fn in sample_funcs:
            udf_results[f"{catalog}.{schema}.{fn.__name__}"] = await uc_fn_client_factory(
                fn, catalog, schema
            )
    else:
        from unitycatalog.ai.core.client import UnitycatalogFunctionClient
        from unitycatalog.client import ApiClient, Configuration

        api_base = settings.unity_catalog.effective_api_base
        token = uc_adapter._resolve_token()

        def _register_udfs() -> dict[str, str]:
            loop = asyncio.DefaultEventLoopPolicy().new_event_loop()
            asyncio.set_event_loop(loop)

            async def _run() -> dict[str, str]:
                cfg = Configuration(host=api_base)
                if token:
                    cfg.access_token = token
                api_client = ApiClient(configuration=cfg)
                if token:
                    api_client.default_headers["Authorization"] = f"Bearer {token}"
                fn_client = UnitycatalogFunctionClient(
                    api_client=api_client,
                    execution_mode=settings.unity_catalog.execution_mode,
                )
                sig = inspect.signature(fn_client.create_python_function_async)
                out: dict[str, str] = {}
                try:
                    for fn in sample_funcs:
                        full_fn = f"{catalog}.{schema}.{fn.__name__}"
                        with contextlib.suppress(Exception):
                            await uc_adapter.request("DELETE", f"functions/{full_fn}")
                        kwargs: dict[str, Any] = {
                            "func": fn,
                            "catalog": catalog,
                            "schema": schema,
                        }
                        if "replace" in sig.parameters:
                            kwargs["replace"] = True
                        await fn_client.create_python_function_async(**kwargs)
                        out[full_fn] = "registered"
                    return out
                finally:
                    await fn_client.close_async()

            try:
                return loop.run_until_complete(_run())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

        udf_results = await asyncio.to_thread(_register_udfs)

    return {
        "catalog": {"name": catalog, "status": cat_status},
        "schema": {"name": f"{catalog}.{schema}", "status": schema_status},
        "volume": {
            "name": volume_full,
            "storage_location": storage_location,
            "status": volume_status,
        },
        "functions": udf_results,
    }
