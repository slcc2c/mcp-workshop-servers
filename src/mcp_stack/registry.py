"""Open MCP Registry (server.json) manifest generation and MLflow 3.15+ sync."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp_stack import __version__
from mcp_stack.core.config import MCPStackSettings

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

SERVER_DESCRIPTIONS: dict[str, str] = {
    "gateway": (
        "Unified FastMCP + FastAPI gateway composing MLflow, Unity Catalog, and core MCP tools"
    ),
    "unity-catalog": (
        "Unity Catalog REST 2.1 governance, model lineage, and unitycatalog-ai function server"
    ),
    "mlflow": (
        "MLflow 3.x Prompt Registry, LoggedModels, UC Model Registry, and Eval Datasets server"
    ),
    "memory": "SQLite + FTS5 persistent AI memory and relationship knowledge graph",
    "filesystem": "Path-sandboxed filesystem operations server",
    "github": "Async GitHub REST API v3 repository, issue, PR, and workflow server",
    "docker": "Docker Engine container, image, volume, and network management server",
    "photos": "macOS host-only Apple Photos library discovery and sandboxed export server",
    "postgresql": "PostgreSQL relational SQL server with READ ONLY default transactions",
    "redis": "Redis cache, data structures, and pub/sub server with cursor SCAN listing",
    "mongodb": "MongoDB document store and aggregation server with read-only defaults",
    "neo4j": "Neo4j graph database Cypher server with READ routing defaults",
    "kubernetes": "Kubernetes cluster server with namespace allowlists and read-only defaults",
    "jupyter": "Jupyter notebook inspection, export, and sandboxed kernel execution server",
    "xcodebuild": "macOS host-only Xcode, SwiftPM, and CoreSimulator MCP server",
    "omnigent": (
        "Local or Tailscale Omnigent hub sessions, workflows, automations, and Inbox bridge"
    ),
    "mac-mini": (
        "Mac mini SSH delegation server for isolated git-worktree Antigravity coding jobs"
    ),
}


def build_server_manifests(settings: MCPStackSettings) -> dict[str, dict[str, Any]]:
    """Build standard MCP Registry server.json payloads for gateway and each server."""
    base_http = f"http://{settings.gateway.host}:{settings.gateway.port}"
    manifests: dict[str, dict[str, Any]] = {}

    manifests["gateway"] = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
        "name": "io.github.slcc2c/mcp-workshop-gateway",
        "title": "MCP Workshop Stack Gateway",
        "description": SERVER_DESCRIPTIONS["gateway"],
        "version": __version__,
        "remotes": [
            {
                "type": "streamable-http",
                "url": f"{base_http}/mcp",
            }
        ],
        "packages": [
            {
                "registryType": "pypi",
                "identifier": "mcp-workshop-stack",
                "version": __version__,
                "transport": {"type": "streamable-http"},
            }
        ],
    }

    for slug, desc in SERVER_DESCRIPTIONS.items():
        if slug == "gateway":
            continue
        is_host_only = slug in {"photos", "xcodebuild"}
        entry: dict[str, Any] = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
            "name": f"io.github.slcc2c/mcp-{slug}",
            "title": f"MCP {slug.replace('-', ' ').title()} Server",
            "description": desc,
            "version": __version__,
            "packages": [
                {
                    "registryType": "pypi",
                    "identifier": "mcp-workshop-stack",
                    "version": __version__,
                    "transport": {"type": "stdio"},
                    "runtimeHint": "uv",
                    "packageArguments": [
                        {"type": "positional", "value": "serve"},
                        {"type": "positional", "value": slug},
                        {"type": "named", "name": "--transport", "value": "stdio"},
                    ],
                }
            ],
        }
        if not is_host_only:
            entry["remotes"] = [
                {
                    "type": "streamable-http",
                    "url": f"{base_http}/servers/{slug}/mcp",
                }
            ]
        manifests[slug] = entry

    for profile_name, raw_members in settings.gateway.profiles.items():
        clean_profile = profile_name.strip()
        if not clean_profile:
            continue
        member_slugs = ", ".join(m.strip().replace("_", "-") for m in raw_members)
        manifests[f"profile-{clean_profile}"] = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
            "name": f"io.github.slcc2c/mcp-profile-{clean_profile}",
            "title": f"MCP Profile: {clean_profile.replace('-', ' ').title()}",
            "description": f"Curated MCP toolset profile '{clean_profile}' ({member_slugs})",
            "version": __version__,
            "remotes": [
                {
                    "type": "streamable-http",
                    "url": f"{base_http}/profiles/{clean_profile}/mcp",
                }
            ],
            "packages": [
                {
                    "registryType": "pypi",
                    "identifier": "mcp-workshop-stack",
                    "version": __version__,
                    "transport": {"type": "streamable-http"},
                }
            ],
        }

    return manifests


def write_manifests(
    settings: MCPStackSettings,
    output_dir: Path = Path("manifests"),
) -> list[Path]:
    """Write server.json manifests to output_dir and return written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = build_server_manifests(settings)
    written: list[Path] = []
    for slug, payload in manifests.items():
        target = output_dir / f"{slug}.server.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written


def _resolve_gateway_access_headers(settings: MCPStackSettings) -> dict[str, str] | None:
    """Return Bearer auth headers for MLflow MCP Registry endpoint checks, if configured."""
    clients = settings.gateway.clients
    if not clients:
        return None
    for token, policy in clients.items():
        if policy.client_id == "claude" and token.strip():
            return {"Authorization": f"Bearer {token.strip()}"}
    for token in clients:
        if token.strip():
            return {"Authorization": f"Bearer {token.strip()}"}
    return None


def sync_mcp_registry(
    settings: MCPStackSettings,
    *,
    dry_run: bool = False,
    output_dir: Path = Path("manifests"),
    genai_module: Any = None,
) -> dict[str, Any]:
    """Write manifests and optionally register them in MLflow 3.15+ MCP Registry."""
    written = write_manifests(settings, output_dir=output_dir)
    manifests = build_server_manifests(settings)

    if dry_run:
        return {
            "dry_run": True,
            "tracking_uri": settings.mlflow.tracking_uri,
            "manifest_files": [str(p) for p in written],
            "results": {
                slug: {"status": "dry_run", "name": m["name"]}
                for slug, m in manifests.items()
            },
        }

    if genai_module is None:
        import mlflow
        import mlflow.genai

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        genai_module = mlflow.genai

    register_fn = getattr(genai_module, "register_mcp_server", None)
    if register_fn is None:
        return {
            "dry_run": False,
            "tracking_uri": settings.mlflow.tracking_uri,
            "manifest_files": [str(p) for p in written],
            "results": {
                slug: {
                    "status": "skipped_unsupported_mlflow",
                    "reason": (
                        "mlflow.genai.register_mcp_server is unavailable "
                        "(requires MLflow >= 3.15)"
                    ),
                }
                for slug in manifests
            },
        }

    access_headers = _resolve_gateway_access_headers(settings)
    results: dict[str, Any] = {}
    refresh_fn = getattr(genai_module, "refresh_mcp_server_version_tools", None)
    alias_fn = getattr(genai_module, "set_mcp_server_alias", None)
    tag_fn = getattr(genai_module, "set_mcp_server_tag", None)

    def _apply_alias_and_tags(
        slug_key: str,
        srv_name: str,
        srv_ver: str,
        has_rem: bool,
        gateway_route: str = "",
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        if callable(alias_fn):
            try:
                alias_fn(name=srv_name, alias="production", version=srv_ver)
                meta["alias"] = "production"
            except Exception as alias_exc:
                meta["alias_error"] = str(alias_exc)
        if callable(tag_fn):
            scope = (
                "gateway"
                if slug_key == "gateway"
                else ("profile" if slug_key.startswith("profile-") else "server")
            )
            desired_tags: dict[str, str] = {
                "scope": scope,
                "governance": "read-only-default",
                "transport": "streamable-http" if has_rem else "stdio",
            }
            if gateway_route:
                desired_tags["gateway_route"] = gateway_route
            applied_tags: dict[str, str] = {}
            for tk, tv in desired_tags.items():
                try:
                    tag_fn(name=srv_name, key=tk, value=tv)
                    applied_tags[tk] = tv
                except Exception:
                    pass
            if applied_tags:
                meta["tags"] = applied_tags
        return meta

    base_http = f"http://{settings.gateway.host}:{settings.gateway.port}"
    for slug, payload in manifests.items():
        if slug == "gateway":
            gw_route = f"{base_http}/mcp"
        elif slug.startswith("profile-"):
            prof_name = slug.removeprefix("profile-")
            gw_route = f"{base_http}/profiles/{prof_name}/mcp"
        else:
            gw_route = f"{base_http}/servers/{slug}/mcp"
        has_remotes = bool(payload.get("remotes"))
        register_kwargs: dict[str, Any] = {
            "server_json": payload,
            "status": "active",
            "create_access_endpoints_from_remotes": has_remotes,
        }
        if access_headers is not None and has_remotes:
            register_kwargs["mcp_server_access_headers"] = access_headers
        try:
            ver = register_fn(**register_kwargs)
            ver_str = str(getattr(ver, "version", payload["version"]))
            entry_ok: dict[str, Any] = {
                "status": "registered",
                "name": payload["name"],
                "version": ver_str,
            }
            entry_ok.update(
                _apply_alias_and_tags(slug, payload["name"], ver_str, has_remotes, gw_route)
            )
            results[slug] = entry_ok
        except Exception as exc:
            err_msg = str(exc)
            if "already exists" in err_msg.lower():
                refreshed = False
                refresh_error: str | None = None
                if refresh_fn is not None and has_remotes:
                    refresh_kwargs: dict[str, Any] = {
                        "name": payload["name"],
                        "version": payload["version"],
                    }
                    if access_headers is not None:
                        refresh_kwargs["mcp_server_access_headers"] = access_headers
                    try:
                        refresh_fn(**refresh_kwargs)
                        refreshed = True
                    except Exception as refresh_exc:
                        refreshed = False
                        refresh_error = str(refresh_exc)
                entry: dict[str, Any] = {
                    "status": "already_exists_refreshed" if refreshed else "already_exists",
                    "name": payload["name"],
                    "version": payload["version"],
                }
                entry.update(
                    _apply_alias_and_tags(
                        slug, payload["name"], payload["version"], has_remotes, gw_route
                    )
                )
                if refresh_error is not None:
                    entry["refresh_error"] = refresh_error
                results[slug] = entry
            else:
                results[slug] = {
                    "status": "error",
                    "name": payload["name"],
                    "error": err_msg,
                }

    upstream_results: dict[str, Any] = {}
    if settings.gateway.upstream_servers:
        upstream_results = sync_upstream_registry(settings, genai_module=genai_module)

    out_payload: dict[str, Any] = {
        "dry_run": False,
        "tracking_uri": settings.mlflow.tracking_uri,
        "manifest_files": [str(p) for p in written],
        "results": results,
    }
    if upstream_results:
        out_payload["upstream_results"] = upstream_results
    return out_payload


def sync_upstream_registry(
    settings: MCPStackSettings,
    *,
    genai_module: Any = None,
    tracking_client: Any = None,
) -> dict[str, Any]:
    """Repair or register federated external MCP servers with tags, gateway_route, & @production."""
    if not settings.gateway.upstream_servers:
        return {}

    if genai_module is None:
        import mlflow
        import mlflow.genai

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        genai_module = mlflow.genai
    if tracking_client is None:
        import mlflow

        tracking_client = mlflow.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    register_fn = getattr(genai_module, "register_mcp_server", None)
    alias_fn = getattr(genai_module, "set_mcp_server_alias", None)
    tag_fn = getattr(genai_module, "set_mcp_server_tag", None)
    search_vers_fn = getattr(genai_module, "search_mcp_server_versions", None)

    base_http = f"http://{settings.gateway.host}:{settings.gateway.port}"
    existing_map: dict[str, Any] = {}
    try:
        for srv in tracking_client.search_mcp_servers(max_results=100):
            existing_map[str(srv.name)] = srv
    except Exception:
        pass

    results: dict[str, Any] = {}
    for raw_name, cfg in settings.gateway.upstream_servers.items():
        slug = raw_name.strip().replace("_", "-").lower()
        reg_name = cfg.registry_name or f"io.github.slcc2c/{slug}"
        route = f"/servers/{slug}/mcp"
        full_gw_url = f"{base_http}{route}"
        entry: dict[str, Any] = {"name": reg_name, "gateway_route": full_gw_url}

        existing = existing_map.get(reg_name)
        target_ver = __version__
        if existing is not None:
            entry["status"] = "updated_existing"
            aliases = dict(getattr(existing, "aliases", None) or {})
            if "production" in aliases:
                target_ver = str(aliases["production"])
            elif aliases:
                target_ver = str(next(iter(aliases.values())))
            elif callable(search_vers_fn):
                try:
                    vers = search_vers_fn(reg_name)
                    if vers:
                        target_ver = str(getattr(vers[0], "version", __version__))
                except Exception:
                    pass
        elif callable(register_fn):
            remote_url = cfg.url if (cfg.transport == "http" and cfg.url) else full_gw_url
            payload = {
                "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
                "name": reg_name,
                "title": slug.replace("-", " ").title(),
                "description": cfg.description or f"Federated MCP server '{slug}'",
                "version": __version__,
                "remotes": [{"type": "streamable-http", "url": remote_url}],
            }
            try:
                ver_obj = register_fn(
                    server_json=payload,
                    status="active",
                    create_access_endpoints_from_remotes=False,
                )
                target_ver = str(getattr(ver_obj, "version", __version__))
                entry["status"] = "registered"
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)[:200]
                results[slug] = entry
                continue
        else:
            entry["status"] = "skipped"
            results[slug] = entry
            continue

        entry["version"] = target_ver
        if callable(alias_fn):
            try:
                alias_fn(name=reg_name, alias="production", version=target_ver)
                entry["alias"] = "production"
            except Exception as exc:
                entry["alias_error"] = str(exc)[:160]

        if callable(tag_fn):
            desired = {
                "scope": "external",
                "governance": cfg.governance or "external-proxy",
                "transport": "streamable-http" if cfg.transport == "http" else "stdio-proxy",
                "gateway_route": full_gw_url,
            }
            applied: dict[str, str] = {}
            for k, v in desired.items():
                try:
                    tag_fn(name=reg_name, key=k, value=v)
                    applied[k] = v
                except Exception:
                    pass
            entry["tags"] = applied
        results[slug] = entry

    return results
