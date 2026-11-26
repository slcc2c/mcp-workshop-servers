"""MLflow 3.18 Skill Registry service layer with graceful <3.18 fallback."""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.skills import (
    _collect_canonical_skills,
    load_skills_manifest,
    resolve_manifest_path,
)

_SEMVER_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")

_CAPABILITY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def parse_semver(version_str: str | None) -> tuple[int, int, int] | None:
    if not version_str:
        return None
    m = _SEMVER_RE.search(version_str.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def probe_skill_registry_capability(
    tracking_uri: str,
    *,
    ttl_s: float = 60.0,
    timeout_s: float = 2.0,
) -> dict[str, Any]:
    """Check whether the configured MLflow tracking server supports Skill Registry (>=3.18.0)."""
    base = tracking_uri.rstrip("/")
    now = time.monotonic()
    cached = _CAPABILITY_CACHE.get(base)
    if cached is not None and now < cached[0]:
        return dict(cached[1])

    server_ver: str | None = None
    reason: str | None = None
    supported = False
    try:
        resp = httpx.get(f"{base}/version", timeout=timeout_s)
        if resp.status_code == 200:
            server_ver = resp.text.strip()
            parsed = parse_semver(server_ver)
            if parsed is not None and parsed >= (3, 18, 0):
                supported = True
            else:
                reason = (
                    f"MLflow server at {base} is running {server_ver or 'unknown'}; "
                    "Skill Registry requires MLflow >= 3.18.0."
                )
        else:
            reason = f"MLflow /version returned HTTP {resp.status_code}"
    except Exception as exc:
        reason = f"MLflow tracking server unreachable at {base}: {exc}"

    payload: dict[str, Any] = {
        "supported": supported,
        "serverVersion": server_ver,
        "requiredVersion": "3.18.0",
        "trackingUri": base,
        "reason": reason,
    }
    _CAPABILITY_CACHE[base] = (now + ttl_s, payload)
    return dict(payload)


def clear_capability_cache() -> None:
    _CAPABILITY_CACHE.clear()


def _serialize_skill_version(ver: Any) -> dict[str, Any]:
    return {
        "name": getattr(ver, "name", None),
        "version": getattr(ver, "version", None),
        "organization": getattr(ver, "organization", "") or "",
        "status": str(getattr(ver, "status", "") or ""),
        "aliases": list(getattr(ver, "aliases", None) or []),
        "digest": getattr(ver, "digest", None),
        "source": str(getattr(ver, "source", "") or "") or None,
        "creationTimestamp": getattr(ver, "creation_timestamp", None),
        "lastUpdatedTimestamp": getattr(ver, "last_updated_timestamp", None),
        "tags": dict(getattr(ver, "tags", None) or {}),
    }


def _read_skill_md_preview(ver: Any) -> str | None:
    try:
        from mlflow.genai.skills import pull_skill_version

        with tempfile.TemporaryDirectory(prefix="mlflow-skill-") as tmp_dir:
            dest = Path(tmp_dir)
            pulled = Path(pull_skill_version(ver, dest))
            for cand in (pulled / "SKILL.md", dest / "SKILL.md"):
                if cand.is_file():
                    return cand.read_text(encoding="utf-8", errors="replace")[:50_000]
            for cand in dest.rglob("SKILL.md"):
                return cand.read_text(encoding="utf-8", errors="replace")[:50_000]
    except Exception:
        return None
    return None


def list_mlflow_skills(
    settings: MCPStackSettings,
    *,
    query: str = "",
    status: str = "",
    organization: str = "",
    max_results: int = 50,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """List registered MLflow 3.18 skills with graceful capability fallback."""
    if mlflow_module is None:
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        if not cap["supported"]:
            return {**cap, "skills": [], "mutationsEnabled": settings.mlflow.allow_mutations}
        import mlflow

        mlflow_mod = mlflow
    else:
        mlflow_mod = mlflow_module
        cap = {
            "supported": True,
            "serverVersion": "3.18.0",
            "requiredVersion": "3.18.0",
            "trackingUri": settings.mlflow.tracking_uri,
            "reason": None,
        }

    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    raw_skills = mlflow_mod.genai.search_skills(max_results=max(1, min(max_results, 100)))

    q_l = query.strip().lower()
    st_l = status.strip().lower()
    org_l = organization.strip().lower()
    skills_out: list[dict[str, Any]] = []

    for sk in raw_skills:
        sk_name = str(getattr(sk, "name", "") or "")
        sk_org = str(getattr(sk, "organization", "") or "")
        sk_desc = str(getattr(sk, "description", "") or "")
        if org_l and sk_org.lower() != org_l:
            continue
        versions_out: list[dict[str, Any]] = []
        try:
            vers = client.search_skill_versions(
                name=sk_name,
                organization=sk_org,
                max_results=25,
            )
            versions_out = [_serialize_skill_version(v) for v in vers]
            versions_out.sort(key=lambda item: int(item.get("version") or 0), reverse=True)
        except Exception:
            pass
        if st_l and not any(str(v.get("status") or "").lower() == st_l for v in versions_out):
            continue
        if q_l:
            hay = f"{sk_name} {sk_org} {sk_desc}".lower()
            if q_l not in hay:
                continue
        skills_out.append(
            {
                "name": sk_name,
                "organization": sk_org,
                "description": sk_desc,
                "aliases": dict(getattr(sk, "aliases", None) or {}),
                "tags": dict(getattr(sk, "tags", None) or {}),
                "versions": versions_out,
            }
        )

    return {
        **cap,
        "mutationsEnabled": settings.mlflow.allow_mutations,
        "skills": skills_out,
    }


def get_mlflow_skill_detail(
    settings: MCPStackSettings,
    name: str,
    *,
    organization: str = "",
    version_or_alias: str | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Fetch metadata, versions, aliases, and SKILL.md preview for one registered skill."""
    if mlflow_module is None:
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        if not cap["supported"]:
            raise RuntimeError(cap["reason"] or "MLflow Skill Registry requires >= 3.18.0")
        import mlflow

        mlflow_mod = mlflow
    else:
        mlflow_mod = mlflow_module

    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
    skill = client.get_skill(name=name, organization=organization)
    vers = client.search_skill_versions(name=name, organization=organization, max_results=25)
    versions_out = [_serialize_skill_version(v) for v in vers]
    versions_out.sort(key=lambda item: int(item.get("version") or 0), reverse=True)

    target_ver_obj: Any = None
    if version_or_alias and version_or_alias.isdigit():
        target_ver_obj = client.get_skill_version(
            name=name, version=int(version_or_alias), organization=organization
        )
    elif version_or_alias:
        target_ver_obj = client.get_skill_version_by_alias(
            name=name, alias=version_or_alias.lstrip("@"), organization=organization
        )
    elif vers:
        target_ver_obj = sorted(vers, key=lambda v: int(getattr(v, "version", 0)), reverse=True)[0]

    skill_md = _read_skill_md_preview(target_ver_obj) if target_ver_obj is not None else None
    return {
        "name": getattr(skill, "name", name),
        "organization": getattr(skill, "organization", organization),
        "description": getattr(skill, "description", None),
        "aliases": dict(getattr(skill, "aliases", None) or {}),
        "tags": dict(getattr(skill, "tags", None) or {}),
        "versions": versions_out,
        "selectedVersion": _serialize_skill_version(target_ver_obj) if target_ver_obj else None,
        "skillMd": skill_md,
    }


def _resolve_local_skill_source(
    settings: MCPStackSettings,
    *,
    source: str | None,
    local_skill_id: str | None,
) -> tuple[str, str | None]:
    if local_skill_id:
        mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
        manifest = load_skills_manifest(mpath)
        canonical, _ = _collect_canonical_skills(manifest, Path.home())
        entry = canonical.get(local_skill_id)
        if entry is None:
            raise ValueError(f"Unknown local skill '{local_skill_id}' in manifest {mpath}")
        canonical_dir = Path(str(entry.get("canonicalPath") or ""))
        if not canonical_dir.is_dir():
            raise ValueError(f"Canonical skill directory missing: {canonical_dir}")
        return str(canonical_dir), str(entry.get("name") or local_skill_id)

    raw = (source or "").strip()
    if not raw:
        raise ValueError("Provide either 'source' or 'local_skill_id'")
    if raw.startswith(("https://", "git://", "oci://", "http://")):
        return raw, None
    cand = Path(raw).expanduser().resolve()
    allowed_roots = [
        Path.cwd().resolve(),
        Path.home().resolve(),
        *settings.filesystem.allowed_paths,
    ]
    if not any(cand == root or cand.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ValueError(f"Local skill path '{cand}' is outside allowed roots")
    if not cand.exists():
        raise ValueError(f"Local skill source path not found: {cand}")
    return str(cand), None


def register_mlflow_skill(
    settings: MCPStackSettings,
    *,
    source: str | None = None,
    local_skill_id: str | None = None,
    name: str | None = None,
    organization: str = "",
    status: str = "draft",
    alias: str | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Register a skill version in the MLflow 3.18 Skill Registry."""
    if not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to register or modify skills")
    if status not in {"draft", "active", "deprecated"}:
        raise ValueError("status must be one of: draft, active, deprecated")

    resolved_src, inferred_name = _resolve_local_skill_source(
        settings, source=source, local_skill_id=local_skill_id
    )
    target_name = (name or inferred_name or "").strip() or None
    if target_name and not _SKILL_NAME_RE.match(target_name):
        raise ValueError("Skill name must match ^[a-z0-9][a-z0-9_-]{0,80}$")

    if mlflow_module is None:
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        if not cap["supported"]:
            raise RuntimeError(cap["reason"] or "MLflow Skill Registry requires >= 3.18.0")
        import mlflow

        mlflow_mod = mlflow
    else:
        mlflow_mod = mlflow_module

    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    ver = mlflow_mod.genai.register_skill(
        source=resolved_src,
        name=target_name,
        organization=organization.strip(),
        status=status,
    )
    ver_num = int(getattr(ver, "version", 1))
    reg_name = str(getattr(ver, "name", target_name or ""))
    if alias and alias.strip():
        client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)
        client.set_skill_alias(
            name=reg_name,
            alias=alias.strip(),
            version=ver_num,
            organization=organization.strip(),
        )
    return {
        "created": True,
        "skill": _serialize_skill_version(ver),
        "alias": alias.strip() if alias else None,
    }


def update_mlflow_skill_version(
    settings: MCPStackSettings,
    *,
    name: str,
    version: int | str,
    organization: str = "",
    status: str | None = None,
    alias: str | None = None,
    delete_alias: str | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Update lifecycle status or alias on a skill version in MLflow 3.18."""
    if not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to update skill versions")

    try:
        ver_num = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"version must be a positive integer, got {version!r}") from exc

    if mlflow_module is None:
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        if not cap["supported"]:
            raise RuntimeError(cap["reason"] or "MLflow Skill Registry requires >= 3.18.0")
        import mlflow

        mlflow_mod = mlflow
    else:
        mlflow_mod = mlflow_module

    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    updated_ver = None
    if status is not None:
        if status not in {"draft", "active", "deprecated"}:
            raise ValueError("status must be one of: draft, active, deprecated")
        updated_ver = client.update_skill_version(
            name=name,
            version=ver_num,
            organization=organization.strip(),
            status=status,
        )
    if alias and alias.strip():
        client.set_skill_alias(
            name=name,
            alias=alias.strip(),
            version=ver_num,
            organization=organization.strip(),
        )
    if delete_alias and delete_alias.strip():
        client.delete_skill_alias(
            name=name,
            alias=delete_alias.strip().lstrip("@"),
            organization=organization.strip(),
        )
    if updated_ver is None:
        updated_ver = client.get_skill_version(
            name=name, version=ver_num, organization=organization.strip()
        )
    return {"updated": True, "version": _serialize_skill_version(updated_ver)}
