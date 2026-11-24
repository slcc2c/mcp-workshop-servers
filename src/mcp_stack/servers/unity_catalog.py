"""Unity Catalog MCP Server (OSS REST API 2.1 + Databricks UC + unitycatalog-ai)."""

from __future__ import annotations

import asyncio
import inspect
import io
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.function_tool import FunctionTool

from mcp_stack.core.auth import caller_uc_token_var
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.logging import get_logger
from mcp_stack.core.tracing import MLflowTracingMiddleware

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

_UC_TYPE_TO_JSON: dict[str, dict[str, Any]] = {
    "STRING": {"type": "string"},
    "TEXT": {"type": "string"},
    "VARCHAR": {"type": "string"},
    "CHAR": {"type": "string"},
    "INT": {"type": "integer"},
    "INTEGER": {"type": "integer"},
    "LONG": {"type": "integer"},
    "BIGINT": {"type": "integer"},
    "SHORT": {"type": "integer"},
    "SMALLINT": {"type": "integer"},
    "BYTE": {"type": "integer"},
    "TINYINT": {"type": "integer"},
    "FLOAT": {"type": "number"},
    "DOUBLE": {"type": "number"},
    "DECIMAL": {"type": "number"},
    "BOOLEAN": {"type": "boolean"},
    "DATE": {"type": "string"},
    "TIMESTAMP": {"type": "string"},
    "BINARY": {"type": "string"},
}


def _split_full_name(full_name: str, expected_parts: int = 3) -> list[str]:
    parts = [p.strip() for p in full_name.split(".") if p.strip()]
    if len(parts) != expected_parts:
        raise ToolError(
            f"Expected {expected_parts}-part Unity Catalog name, got '{full_name}'"
        )
    return parts


def _uc_schema_for_function(func_meta: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    input_params = (func_meta.get("input_params") or {}).get("parameters") or []
    for param in input_params:
        pname = param.get("name")
        if not pname:
            continue
        type_name = str(param.get("type_name") or "STRING").upper()
        prop = dict(_UC_TYPE_TO_JSON.get(type_name, {"type": "string"}))
        if param.get("comment"):
            prop["description"] = str(param["comment"])
        properties[pname] = prop
        if param.get("parameter_default") is None:
            required.append(pname)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _sanitize_tool_name(full_name: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in full_name)
    return f"uc_fn_{safe}"


class UCClientAdapter:
    """Async Unity Catalog REST API 2.1 client with OBO token resolution."""

    def __init__(
        self,
        settings: MCPStackSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._uc = settings.unity_catalog
        self._external_client = http_client

    def _resolve_token(self) -> str | None:
        obo = caller_uc_token_var.get()
        if obo:
            return obo
        if self._uc.token is not None:
            val = self._uc.token.get_secret_value().strip()
            if val:
                return val
        return None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        token = self._resolve_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._uc.effective_api_base}/{path.lstrip('/')}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        if self._external_client is not None:
            response = await self._external_client.request(
                method,
                url,
                params=clean_params,
                json=json_body,
                headers=self._headers(),
            )
        else:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(
                    method,
                    url,
                    params=clean_params,
                    json=json_body,
                    headers=self._headers(),
                )

        if response.status_code >= 400:
            detail = response.text[:500]
            try:
                err_json = response.json()
                detail = err_json.get("message") or err_json.get("detail") or detail
            except Exception:
                pass
            raise ToolError(
                f"Unity Catalog API {method} {path} failed ({response.status_code}): {detail}"
            )
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"items": data}

    async def execute_function(
        self,
        full_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if self._uc.mode == "databricks":
            try:
                from unitycatalog.ai.databricks.client import DatabricksFunctionClient
            except ImportError as exc:
                raise ToolError(
                    "Databricks UC function execution requires extra 'databricks': "
                    "uv sync --extra databricks"
                ) from exc

            def _run_db() -> Any:
                client = DatabricksFunctionClient(
                    profile=self._uc.databricks_profile,
                )
                return client.execute_function(full_name, parameters=parameters)

            result = await asyncio.to_thread(_run_db)
            return {
                "function": full_name,
                "value": getattr(result, "value", result),
                "error": getattr(result, "error", None),
            }

        from unitycatalog.ai.core.client import UnitycatalogFunctionClient
        from unitycatalog.client import ApiClient, Configuration

        token = self._resolve_token()
        api_base = self._uc.effective_api_base

        def _run_oss_in_asyncio_thread() -> Any:
            # unitycatalog-ai calls nest_asyncio internally, which cannot patch uvloop,
            # while unitycatalog-client needs a running stdlib asyncio loop for aiohttp.
            loop = asyncio.DefaultEventLoopPolicy().new_event_loop()
            asyncio.set_event_loop(loop)

            async def _exec() -> Any:
                cfg = Configuration(host=api_base)
                if token:
                    cfg.access_token = token
                api_client = ApiClient(configuration=cfg)
                if token:
                    api_client.default_headers["Authorization"] = f"Bearer {token}"

                uc_fn_client = UnitycatalogFunctionClient(
                    api_client=api_client,
                    execution_mode=self._uc.execution_mode,
                )
                try:
                    return await uc_fn_client.execute_function_async(
                        function_name=full_name,
                        parameters=parameters,
                    )
                finally:
                    await uc_fn_client.close_async()

            try:
                return loop.run_until_complete(_exec())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

        exec_res = await asyncio.to_thread(_run_oss_in_asyncio_thread)
        return {
            "function": full_name,
            "value": getattr(exec_res, "value", exec_res),
            "error": getattr(exec_res, "error", None),
        }

    @staticmethod
    def validate_volume_filename(filename: str) -> str:
        """Validate a single-segment filename for UC Volume upload/download."""
        clean = filename.strip()
        if (
            not clean
            or "/" in clean
            or "\\" in clean
            or clean in {".", ".."}
            or ".." in Path(clean).parts
        ):
            raise ToolError(f"Invalid UC Volume filename '{filename}': must be a flat file name")
        return clean

    def _build_databricks_workspace_client(self, profile: str | None = None) -> Any:
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError as exc:
            raise ToolError(
                "Databricks SDK requires extra 'databricks': uv sync --extra databricks"
            ) from exc

        kwargs: dict[str, Any] = {}
        host = self._uc.databricks_host
        if host:
            kwargs["host"] = host
        token = self._resolve_token()
        if token:
            kwargs["token"] = token
        else:
            prof = profile or self._uc.databricks_profile
            if prof:
                kwargs["profile"] = prof
        return WorkspaceClient(**kwargs)

    async def upload_volume_file(
        self,
        full_volume_name: str,
        filename: str,
        content: bytes,
        *,
        overwrite: bool = True,
        workspace_client: Any = None,
    ) -> dict[str, Any]:
        """Upload bytes to a Databricks UC Volume via WorkspaceClient.files.upload."""
        cat, schema, vol = _split_full_name(full_volume_name, 3)
        safe_name = self.validate_volume_filename(filename)
        volume_path = f"/Volumes/{cat}/{schema}/{vol}/{safe_name}"

        def _upload() -> None:
            ws = workspace_client or self._build_databricks_workspace_client()
            ws.files.upload(volume_path, io.BytesIO(content), overwrite=overwrite)

        try:
            await asyncio.to_thread(_upload)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(
                f"Databricks UC Volume upload failed for '{volume_path}': {exc}"
            ) from exc

        return {
            "volume": full_volume_name,
            "filePath": volume_path,
            "bytes": len(content),
            "overwrite": overwrite,
        }

    async def download_volume_file(
        self,
        full_volume_name: str,
        filename: str | None = None,
        *,
        prefix: str = "memory-export-",
        suffix: str = ".json",
        workspace_client: Any = None,
    ) -> tuple[str, bytes]:
        """Download a file (or newest matching snapshot) from a Databricks UC Volume."""
        cat, schema, vol = _split_full_name(full_volume_name, 3)
        volume_dir = f"/Volumes/{cat}/{schema}/{vol}"
        chosen_name = self.validate_volume_filename(filename) if filename else None

        def _download() -> tuple[str, bytes]:
            ws = workspace_client or self._build_databricks_workspace_client()
            target_name = chosen_name
            if target_name is None:
                entries = list(ws.files.list_directory_contents(volume_dir))
                candidates = []
                for entry in entries:
                    if getattr(entry, "is_directory", False):
                        continue
                    name = str(getattr(entry, "name", "") or "")
                    if not name and getattr(entry, "path", None):
                        name = str(entry.path).rsplit("/", 1)[-1]
                    if name.startswith(prefix) and name.endswith(suffix):
                        modified = int(getattr(entry, "last_modified", 0) or 0)
                        candidates.append((modified, name))
                if not candidates:
                    raise ToolError(
                        f"No {prefix}*{suffix} snapshots found in '{volume_dir}'"
                    )
                candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
                target_name = self.validate_volume_filename(candidates[0][1])

            file_path = f"{volume_dir}/{target_name}"
            resp = ws.files.download(file_path)
            stream = getattr(resp, "contents", resp)
            raw = stream.read() if hasattr(stream, "read") else stream
            data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            return file_path, data

        try:
            return await asyncio.to_thread(_download)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(
                f"Databricks UC Volume download failed for '{volume_dir}': {exc}"
            ) from exc

    async def databricks_probe(self, profile: str | None = None) -> dict[str, Any]:
        """Perform a read-only Databricks UC catalog listing probe."""
        prof = profile or self._uc.databricks_profile

        def _probe() -> dict[str, Any]:
            ws = self._build_databricks_workspace_client(profile=prof)
            catalogs = [c.name for c in ws.catalogs.list()][:20]
            return {"ok": True, "profile": prof, "catalogs": catalogs}

        try:
            return await asyncio.to_thread(_probe)
        except ToolError as exc:
            return {"ok": False, "profile": prof, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "profile": prof, "error": str(exc)}


async def resolve_volume_local_dir(
    adapter: UCClientAdapter,
    settings: MCPStackSettings,
    full_name: str,
) -> Path:
    """Resolve an OSS Unity Catalog Volume storage_location to a validated local Path."""
    _split_full_name(full_name, 3)
    meta = await adapter.request("GET", f"volumes/{full_name}")
    storage = str(meta.get("storage_location") or "").strip()
    if not storage:
        raise ToolError(f"Volume '{full_name}' has no storage_location")

    for prefix, local_root_raw in settings.unity_catalog.volume_local_prefix_map.items():
        clean_prefix = prefix.rstrip("/")
        if storage == clean_prefix or storage.startswith(clean_prefix + "/"):
            rel = storage[len(clean_prefix) :].lstrip("/")
            base = Path(local_root_raw).resolve()
            resolved = (base / rel).resolve() if rel else base
            if not resolved.is_relative_to(base):
                raise ToolError(f"Mapped volume path '{resolved}' escapes '{base}'")
            return resolved

    if storage.startswith("file://"):
        local_direct = Path(storage.removeprefix("file://"))
        if local_direct.exists():
            return local_direct.resolve()

    raise ToolError(
        f"Volume '{full_name}' storage_location '{storage}' has no host mapping. "
        "Configure UC_VOLUME_LOCAL_PREFIX_MAP in .env."
    )


def _is_schema_allowlisted(catalog: str, schema: str, allowlist: list[str]) -> bool:
    if "*" in allowlist or "*.*" in allowlist:
        return True
    target = f"{catalog}.{schema}"
    return target in allowlist or f"{catalog}.*" in allowlist


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.unity_catalog.allow_mutations:
        raise ToolError(
            "Unity Catalog mutations are disabled by policy. "
            "Set UC_ALLOW_MUTATIONS=true to enable write operations."
        )


async def sync_uc_function_tools(
    mcp: FastMCP,
    adapter: UCClientAdapter,
    settings: MCPStackSettings,
    *,
    function_executor: Callable[[str, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Discover allowlisted UC functions and register them as dynamic FastMCP tools."""
    logger = get_logger("unity_catalog.sync")
    if not settings.unity_catalog.dynamic_function_tools:
        return {"registered": [], "skipped": "dynamic_function_tools=false"}

    registered: list[str] = []
    errors: list[dict[str, str]] = []

    for pattern in settings.unity_catalog.function_allowlist:
        if "*" in pattern:
            continue
        parts = [p.strip() for p in pattern.split(".") if p.strip()]
        if len(parts) != 2:
            continue
        catalog_name, schema_name = parts
        try:
            data = await adapter.request(
                "GET",
                "functions",
                params={"catalog_name": catalog_name, "schema_name": schema_name},
            )
        except Exception as exc:
            errors.append({"schema": pattern, "error": str(exc)})
            logger.debug("Skipping dynamic UC function sync", schema=pattern, error=str(exc))
            continue

        for fn_meta in data.get("functions", []):
            full_name = fn_meta.get("full_name")
            if not full_name:
                continue
            tool_name = _sanitize_tool_name(full_name)
            description = (
                fn_meta.get("comment")
                or f"Execute Unity Catalog function {full_name}"
            )
            schema = _uc_schema_for_function(fn_meta)

            async def _invoke(
                _fn_name: str = full_name,
                **kwargs: Any,
            ) -> dict[str, Any]:
                if not settings.unity_catalog.enable_function_execution:
                    raise ToolError("UC function execution is disabled")
                if function_executor is not None:
                    out = function_executor(_fn_name, kwargs)
                    if inspect.isawaitable(out):
                        out = await out
                    return out if isinstance(out, dict) else {"function": _fn_name, "value": out}
                return await adapter.execute_function(_fn_name, kwargs)

            tool = FunctionTool(
                name=tool_name,
                description=f"[UC Function: {full_name}] {description}",
                parameters=schema,
                fn=_invoke,
            )
            mcp.add_tool(tool)
            registered.append(tool_name)

    return {"registered": registered, "errors": errors}


def create_unity_catalog_server(
    settings: MCPStackSettings,
    *,
    adapter: UCClientAdapter | None = None,
    function_executor: Callable[[str, dict[str, Any]], Any] | None = None,
    mlflow_client_factory: Callable[[], Any] | None = None,
) -> FastMCP:
    """Create the Unity Catalog MCP server."""
    uc_adapter = adapter or UCClientAdapter(settings)
    mcp = FastMCP("unity-catalog")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "unity_catalog"))

    async def _exec_fn(full_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if function_executor is not None:
            out = function_executor(full_name, parameters)
            if inspect.isawaitable(out):
                out = await out
            return out if isinstance(out, dict) else {"function": full_name, "value": out}
        return await uc_adapter.execute_function(full_name, parameters)

    # --- Catalogs & Schemas ---

    @mcp.tool()
    async def uc_list_catalogs(max_results: int = 100) -> dict[str, Any]:
        """List catalogs in Unity Catalog."""
        return await uc_adapter.request("GET", "catalogs", params={"max_results": max_results})

    @mcp.tool()
    async def uc_get_catalog(name: str) -> dict[str, Any]:
        """Get metadata for a single Unity Catalog catalog."""
        return await uc_adapter.request("GET", f"catalogs/{name}")

    @mcp.tool()
    async def uc_list_schemas(catalog_name: str, max_results: int = 100) -> dict[str, Any]:
        """List schemas inside a Unity Catalog catalog."""
        return await uc_adapter.request(
            "GET",
            "schemas",
            params={"catalog_name": catalog_name, "max_results": max_results},
        )

    @mcp.tool()
    async def uc_get_schema(full_name: str) -> dict[str, Any]:
        """Get metadata for a schema using its two-part name (catalog.schema)."""
        _split_full_name(full_name, 2)
        return await uc_adapter.request("GET", f"schemas/{full_name}")

    # --- Tables & Volumes ---

    @mcp.tool()
    async def uc_list_tables(
        catalog_name: str,
        schema_name: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """List tables inside a catalog.schema namespace."""
        return await uc_adapter.request(
            "GET",
            "tables",
            params={
                "catalog_name": catalog_name,
                "schema_name": schema_name,
                "max_results": max_results,
            },
        )

    @mcp.tool()
    async def uc_get_table(full_name: str) -> dict[str, Any]:
        """Get table metadata and columns by three-part name (catalog.schema.table)."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request("GET", f"tables/{full_name}")

    @mcp.tool()
    async def uc_list_volumes(
        catalog_name: str,
        schema_name: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """List volumes inside a catalog.schema namespace."""
        return await uc_adapter.request(
            "GET",
            "volumes",
            params={
                "catalog_name": catalog_name,
                "schema_name": schema_name,
                "max_results": max_results,
            },
        )

    @mcp.tool()
    async def uc_get_volume(full_name: str) -> dict[str, Any]:
        """Get volume metadata by three-part name (catalog.schema.volume)."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request("GET", f"volumes/{full_name}")

    # --- Functions ---

    @mcp.tool()
    async def uc_list_functions(
        catalog_name: str,
        schema_name: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """List Unity Catalog functions in a catalog.schema namespace."""
        return await uc_adapter.request(
            "GET",
            "functions",
            params={
                "catalog_name": catalog_name,
                "schema_name": schema_name,
                "max_results": max_results,
            },
        )

    @mcp.tool()
    async def uc_get_function(full_name: str) -> dict[str, Any]:
        """Get Unity Catalog function definition by three-part name (catalog.schema.func)."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request("GET", f"functions/{full_name}")

    @mcp.tool()
    async def uc_execute_function(
        full_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an allowlisted Unity Catalog function via unitycatalog-ai."""
        if not settings.unity_catalog.enable_function_execution:
            raise ToolError(
                "Unity Catalog function execution is disabled (UC_ENABLE_FUNCTION_EXECUTION=false)"
            )
        catalog, schema, _ = _split_full_name(full_name, 3)
        if not _is_schema_allowlisted(
            catalog, schema, settings.unity_catalog.function_allowlist
        ):
            raise ToolError(
                f"Function '{full_name}' is outside UC_FUNCTION_ALLOWLIST "
                f"({settings.unity_catalog.function_allowlist})"
            )
        return await _exec_fn(full_name, parameters or {})

    @mcp.tool()
    async def uc_refresh_function_tools() -> dict[str, Any]:
        """Discover and register dynamic tools for allowlisted Unity Catalog functions."""
        return await sync_uc_function_tools(
            mcp, uc_adapter, settings, function_executor=function_executor
        )

    # --- Models & MLflow Lineage ---

    @mcp.tool()
    async def uc_list_models(
        catalog_name: str | None = None,
        schema_name: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """List registered models in Unity Catalog."""
        return await uc_adapter.request(
            "GET",
            "models",
            params={
                "catalog_name": catalog_name,
                "schema_name": schema_name,
                "max_results": max_results,
            },
        )

    @mcp.tool()
    async def uc_get_model(full_name: str) -> dict[str, Any]:
        """Get registered model metadata by three-part name (catalog.schema.model)."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request("GET", f"models/{full_name}")

    @mcp.tool()
    async def uc_list_model_versions(full_name: str, max_results: int = 100) -> dict[str, Any]:
        """List versions for a Unity Catalog registered model."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request(
            "GET",
            f"models/{full_name}/versions",
            params={"max_results": max_results},
        )

    @mcp.tool()
    async def uc_get_model_version(full_name: str, version: int) -> dict[str, Any]:
        """Get metadata for a specific Unity Catalog model version."""
        _split_full_name(full_name, 3)
        return await uc_adapter.request("GET", f"models/{full_name}/versions/{version}")

    @mcp.tool()
    async def uc_get_model_lineage(full_name: str, version: int) -> dict[str, Any]:
        """Cross-link a UC model version with MLflow run metrics, params, and traces."""
        _split_full_name(full_name, 3)
        mv = await uc_adapter.request("GET", f"models/{full_name}/versions/{version}")
        run_id = mv.get("run_id")
        lineage: dict[str, Any] = {
            "model": full_name,
            "version": version,
            "model_version": mv,
            "mlflow_run": None,
            "mlflow_traces": [],
        }
        if not run_id:
            return lineage

        def _fetch_mlflow_lineage() -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
            if mlflow_client_factory is not None:
                client = mlflow_client_factory()
            else:
                import mlflow

                client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

            run = client.get_run(run_id)
            run_info = {
                "run_id": run.info.run_id,
                "experiment_id": run.info.experiment_id,
                "status": run.info.status,
                "metrics": dict(run.data.metrics),
                "params": dict(run.data.params),
                "tags": dict(run.data.tags),
            }
            traces: list[dict[str, Any]] = []
            try:
                found = client.search_traces(
                    locations=[run.info.experiment_id],
                    filter_string=f"metadata.mlflow.sourceRun = '{run_id}'",
                    max_results=10,
                )
                for tr in found:
                    info = getattr(tr, "info", tr)
                    traces.append(
                        {
                            "trace_id": getattr(info, "trace_id", None)
                            or getattr(info, "request_id", None),
                            "state": str(getattr(info, "state", "")),
                            "execution_duration_ms": getattr(
                                info, "execution_duration", None
                            ),
                        }
                    )
            except Exception:
                pass
            return run_info, traces

        try:
            run_info, traces = await asyncio.to_thread(_fetch_mlflow_lineage)
            lineage["mlflow_run"] = run_info
            lineage["mlflow_traces"] = traces
        except Exception as exc:
            lineage["mlflow_error"] = str(exc)

        return lineage

    # --- Opt-in Mutations ---

    @mcp.tool()
    async def uc_create_catalog(name: str, comment: str = "") -> dict[str, Any]:
        """Create a catalog in Unity Catalog (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        return await uc_adapter.request(
            "POST", "catalogs", json_body={"name": name, "comment": comment}
        )

    @mcp.tool()
    async def uc_create_schema(
        catalog_name: str,
        name: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Create a schema inside a catalog (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        return await uc_adapter.request(
            "POST",
            "schemas",
            json_body={"catalog_name": catalog_name, "name": name, "comment": comment},
        )

    @mcp.tool()
    async def uc_create_volume(
        catalog_name: str,
        schema_name: str,
        name: str,
        storage_location: str | None = None,
        volume_type: str = "EXTERNAL",
        comment: str = "",
    ) -> dict[str, Any]:
        """Create a volume in Unity Catalog (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        body: dict[str, Any] = {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "name": name,
            "volume_type": volume_type.upper(),
        }
        if storage_location:
            body["storage_location"] = storage_location
        if comment.strip():
            body["comment"] = comment.strip()
        return await uc_adapter.request("POST", "volumes", json_body=body)

    @mcp.tool()
    async def uc_create_function(
        catalog_name: str,
        schema_name: str,
        name: str,
        routine_definition: str,
        data_type: str = "STRING",
        input_params: list[dict[str, str]] | None = None,
        comment: str = "",
    ) -> dict[str, Any]:
        """Create a Python/SQL function in Unity Catalog (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        params_payload = input_params or []
        body: dict[str, Any] = {
            "function_info": {
                "catalog_name": catalog_name,
                "schema_name": schema_name,
                "name": name,
                "input_params": {"parameters": params_payload},
                "data_type": data_type,
                "full_data_type": data_type,
                "parameter_style": "S",
                "is_deterministic": True,
                "sql_data_access": "CONTAINS_SQL",
                "is_null_call": False,
                "security_type": "DEFINER",
                "routine_body": "EXTERNAL",
                "routine_definition": routine_definition,
                "external_language": "PYTHON",
                "comment": comment,
            }
        }
        return await uc_adapter.request("POST", "functions", json_body=body)

    @mcp.tool()
    async def uc_delete_function(full_name: str) -> dict[str, Any]:
        """Delete a Unity Catalog function (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        _split_full_name(full_name, 3)
        await uc_adapter.request("DELETE", f"functions/{full_name}")
        return {"deleted": True, "full_name": full_name}

    @mcp.tool()
    async def uc_set_model_version_alias(
        full_name: str,
        alias: str,
        version: int,
    ) -> dict[str, Any]:
        """Assign an alias to a Unity Catalog model version (requires UC_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)
        _split_full_name(full_name, 3)
        try:
            return await uc_adapter.request(
                "PUT",
                f"models/{full_name}/aliases/{alias}",
                json_body={"version": version},
            )
        except ToolError:
            # Fallback for OSS UC / MLflow UC registry alias route when supported via MlflowClient
            def _set_via_mlflow() -> dict[str, Any]:
                if mlflow_client_factory is not None:
                    client = mlflow_client_factory()
                else:
                    import mlflow

                    client = mlflow.MlflowClient(
                        tracking_uri=settings.mlflow.tracking_uri,
                        registry_uri=settings.effective_mlflow_registry_uri,
                    )
                client.set_registered_model_alias(full_name, alias, str(version))
                return {"model": full_name, "alias": alias, "version": version}

            return await asyncio.to_thread(_set_via_mlflow)

    return mcp
