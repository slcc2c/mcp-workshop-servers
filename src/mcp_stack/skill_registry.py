"""MLflow 3.18 Skill Registry service layer with graceful <3.18 fallback."""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.skills import (
    _collect_canonical_skills,
    hash_skill_dir,
    load_skills_manifest,
    resolve_manifest_path,
    sync_skills,
)

_SEMVER_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_GITHUB_TREE_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/tree/([^/]+)(?:/(.*?))?/?$"
)
_GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$"
)
DEFAULT_WEB_LOCK_RELATIVE = Path("templates/agents/web-skills-lock.yaml")
DEFAULT_MATERIALIZE_ROOT = Path("~/.local/share/mcp-stack/registry-skills")

_SOURCE_ORG_DEFAULTS: dict[str, str] = {
    "atelier-personal": "personal",
    "mlflow-sme": "mlflow-sme",
    "prose-hygiene": "vendor",
}

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
    max_results: int = 250,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """List registered MLflow 3.18 skills across pages with graceful fallback."""
    if mlflow_module is None:
        cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
        if not cap["supported"]:
            return {
                **cap,
                "skills": [],
                "organizations": [],
                "mutationsEnabled": settings.mlflow.allow_mutations,
            }
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
    raw_skills = _search_all_skills(mlflow_mod, max_results=max(1, max_results))

    q_l = query.strip().lower()
    st_l = status.strip().lower()
    org_l = organization.strip().lower()
    orgs_seen: set[str] = set()
    skills_out: list[dict[str, Any]] = []

    for sk in raw_skills:
        sk_name = str(getattr(sk, "name", "") or "")
        sk_org = str(getattr(sk, "organization", "") or "")
        sk_desc = str(getattr(sk, "description", "") or "")
        if sk_org:
            orgs_seen.add(sk_org)
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
        latest_ver = str(versions_out[0].get("version")) if versions_out else None
        skills_out.append(
            {
                "name": sk_name,
                "organization": sk_org,
                "description": sk_desc,
                "latestVersion": latest_ver,
                "aliases": dict(getattr(sk, "aliases", None) or {}),
                "tags": dict(getattr(sk, "tags", None) or {}),
                "versions": versions_out,
            }
        )

    return {
        **cap,
        "mutationsEnabled": settings.mlflow.allow_mutations,
        "organizations": sorted(orgs_seen),
        "skills": skills_out,
    }


def _search_all_skills(mlflow_mod: Any, *, max_results: int = 250) -> list[Any]:
    """Iterate MLflow search_skills pages up to max_results."""
    collected: list[Any] = []
    page_token: str | None = None
    while len(collected) < max_results:
        page_limit = min(100, max_results - len(collected))
        kwargs: dict[str, Any] = {"max_results": page_limit}
        if page_token:
            kwargs["page_token"] = page_token
        page = mlflow_mod.genai.search_skills(**kwargs)
        items = list(page)
        collected.extend(items)
        next_token = getattr(page, "token", None)
        if not next_token or not items:
            break
        page_token = str(next_token)
    return collected


_SKILL_ORG_LOOKUP_RANK: dict[str, int] = {
    "personal": 0,
    "mlflow-sme": 1,
    "web": 2,
    "vendor": 3,
}


def _resolve_skill_identity_and_org(
    mlflow_mod: Any,
    client: Any,
    name: str,
    organization: str,
) -> tuple[str, str]:
    clean_name = name.strip()
    clean_org = organization.strip()
    if clean_name.startswith("@") and "/" in clean_name:
        org_part, _, name_part = clean_name[1:].partition("/")
        if org_part and name_part:
            clean_org = clean_org or org_part.strip()
            clean_name = name_part.strip()

    if clean_org:
        return clean_name, clean_org

    # Resolve across organizations using canonical precedence when no org was specified
    candidates: list[str] = []
    for sk in _search_all_skills(mlflow_mod, max_results=500):
        if str(getattr(sk, "name", "") or "") == clean_name:
            candidates.append(str(getattr(sk, "organization", "") or ""))
    if not candidates:
        return clean_name, ""

    def _org_rank(org: str) -> tuple[int, str]:
        if org in _SKILL_ORG_LOOKUP_RANK:
            return (_SKILL_ORG_LOOKUP_RANK[org], org)
        if org.startswith("repo-"):
            return (4, org)
        if org == "":
            return (5, org)
        return (6, org)

    return clean_name, min(candidates, key=_org_rank)


def get_mlflow_skill_detail(
    settings: MCPStackSettings,
    name: str,
    *,
    organization: str = "",
    version_or_alias: str | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Fetch metadata, versions, aliases, and SKILL.md preview for one registered skill."""
    mlflow_mod = _ensure_mlflow_mod(settings, mlflow_module)
    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    resolved_name, resolved_org = _resolve_skill_identity_and_org(
        mlflow_mod, client, name, organization
    )
    skill = client.get_skill(name=resolved_name, organization=resolved_org)
    vers = client.search_skill_versions(
        name=resolved_name, organization=resolved_org, max_results=25
    )
    versions_out = [_serialize_skill_version(v) for v in vers]
    versions_out.sort(key=lambda item: int(item.get("version") or 0), reverse=True)

    target_ver_obj: Any = None
    if version_or_alias and version_or_alias.isdigit():
        target_ver_obj = client.get_skill_version(
            name=resolved_name, version=int(version_or_alias), organization=resolved_org
        )
    elif version_or_alias:
        target_ver_obj = client.get_skill_version_by_alias(
            name=resolved_name,
            alias=version_or_alias.lstrip("@"),
            organization=resolved_org,
        )
    elif vers:
        target_ver_obj = sorted(
            vers, key=lambda v: int(getattr(v, "version", 0)), reverse=True
        )[0]

    skill_md = _read_skill_md_preview(target_ver_obj) if target_ver_obj is not None else None
    actual_org = getattr(skill, "organization", resolved_org)
    return {
        "name": getattr(skill, "name", resolved_name),
        "organization": actual_org,
        "resolvedOrganization": actual_org,
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


def normalize_mlflow_name(raw: str) -> str:
    """Normalize a skill directory name to MLflow 3.18's lowercase hyphenated format."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip("-")
    if not cleaned or not _SKILL_NAME_RE.fullmatch(cleaned):
        raise ValueError(f"Cannot normalize skill name to MLflow format: {raw!r}")
    return cleaned


def normalize_mlflow_org(raw: str) -> str:
    """Normalize an organization slug to MLflow 3.18's lowercase hyphenated format."""
    text = raw.strip()
    if not text:
        return ""
    return normalize_mlflow_name(text)


def _ensure_mlflow_mod(settings: MCPStackSettings, mlflow_module: Any | None) -> Any:
    if mlflow_module is not None:
        return mlflow_module
    cap = probe_skill_registry_capability(settings.mlflow.tracking_uri)
    if not cap["supported"]:
        raise RuntimeError(cap["reason"] or "MLflow Skill Registry requires >= 3.18.0")
    import mlflow

    return mlflow


def resolve_web_lock_path(settings: MCPStackSettings, lock_path: Path | None = None) -> Path:
    """Resolve the declarative web-skills-lock.yaml path beside skills-manifest.yaml."""
    if lock_path is not None:
        return lock_path.expanduser()
    try:
        mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
        return mpath.parent / "web-skills-lock.yaml"
    except Exception:
        return (
            settings.skills.repos_root.expanduser() / "atelier" / DEFAULT_WEB_LOCK_RELATIVE
        )


def load_web_skills_lock(lock_path: Path) -> dict[str, Any]:
    """Load web-skills-lock.yaml cleanly, returning a normalized dict structure."""
    if not lock_path.exists():
        return {
            "version": 1,
            "tracking_uri": "http://localhost:5002",
            "materialize_root": str(DEFAULT_MATERIALIZE_ROOT),
            "skills": [],
        }
    data = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Lockfile must be a YAML mapping: {lock_path}")
    data.setdefault("version", 1)
    data.setdefault("materialize_root", str(DEFAULT_MATERIALIZE_ROOT))
    if not isinstance(data.get("skills"), list):
        data["skills"] = []
    return data


def save_web_skills_lock(lock_path: Path, data: dict[str, Any]) -> None:
    """Persist web-skills-lock.yaml deterministically with atomic temp replacement."""
    skills_list = sorted(
        list(data.get("skills") or []),
        key=lambda item: (str(item.get("organization") or ""), str(item.get("name") or "")),
    )
    payload = {
        "version": int(data.get("version") or 1),
        "tracking_uri": str(data.get("tracking_uri") or "http://localhost:5002"),
        "materialize_root": str(data.get("materialize_root") or DEFAULT_MATERIALIZE_ROOT),
        "skills": skills_list,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = lock_path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    tmp.replace(lock_path)


def _upsert_lock_entry(
    data: dict[str, Any],
    *,
    name: str,
    organization: str,
    source: str,
    version: int,
    digest: str,
    alias: str = "production",
) -> None:
    entries: list[dict[str, Any]] = [
        item
        for item in (data.get("skills") or [])
        if not (
            isinstance(item, dict)
            and str(item.get("name") or "") == name
            and str(item.get("organization") or "") == organization
        )
    ]
    entries.append(
        {
            "name": name,
            "organization": organization,
            "source": source,
            "alias": alias,
            "version": int(version),
            "digest": digest,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    data["skills"] = entries


def _git_skill_state(skill_dir: Path) -> tuple[bool, str, str]:
    """Return (is_clean, short_commit, repo_name) for a skill directory."""
    try:
        top = subprocess.run(
            ["git", "-C", str(skill_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if top.returncode != 0 or not top.stdout.strip():
            return False, "", ""
        top_path = Path(top.stdout.strip()).resolve()
        head = subprocess.run(
            ["git", "-C", str(top_path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        commit = head.stdout.strip() if head.returncode == 0 else ""
        try:
            rel = str(skill_dir.resolve().relative_to(top_path))
        except ValueError:
            rel = str(skill_dir)
        st = subprocess.run(
            ["git", "-C", str(top_path), "status", "--porcelain", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        is_clean = st.returncode == 0 and not st.stdout.strip()
        return is_clean, commit, top_path.name
    except Exception:
        return False, "", ""


def _tag_skill_version_best_effort(
    client: Any,
    *,
    name: str,
    version: int,
    organization: str,
    tags: dict[str, str],
) -> None:
    if not hasattr(client, "set_skill_version_tag"):
        return
    for k, v in tags.items():
        if not v:
            continue
        with contextlib.suppress(Exception):
            client.set_skill_version_tag(
                name=name,
                version=version,
                key=k,
                value=str(v)[:500],
                organization=organization,
            )


def materialize_mlflow_skill(
    settings: MCPStackSettings,
    name: str,
    *,
    organization: str = "web",
    version_or_alias: str = "production",
    materialize_root: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Pull a skill version from MLflow 3.18 into staging and atomically swap into cache."""
    mlflow_mod = _ensure_mlflow_mod(settings, mlflow_module)
    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    org_clean = normalize_mlflow_org(organization) if organization else ""
    if version_or_alias.isdigit():
        ver = client.get_skill_version(
            name=name, version=int(version_or_alias), organization=org_clean
        )
    else:
        try:
            ver = client.get_skill_version_by_alias(
                name=name, alias=version_or_alias.lstrip("@"), organization=org_clean
            )
        except Exception:
            ver = client.get_latest_skill_version(name=name, organization=org_clean)

    root = (materialize_root or DEFAULT_MATERIALIZE_ROOT).expanduser()
    staging_root = root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    pull_dest = staging_root / f"pull-{name}-{uuid.uuid4().hex[:8]}"

    from mlflow.genai.skills import pull_skill_version

    pulled = Path(pull_skill_version(ver, pull_dest))
    if not (pulled / "SKILL.md").is_file():
        shutil.rmtree(pull_dest, ignore_errors=True)
        raise RuntimeError(f"Pulled skill '{name}' missing SKILL.md at {pulled}")

    target_dir = root / (org_clean or "default") / name
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_dir: Path | None = None
    try:
        if target_dir.is_symlink():
            target_dir.unlink()
        elif target_dir.exists():
            backup_dir = staging_root / f"bak-{name}-{uuid.uuid4().hex[:8]}"
            shutil.move(str(target_dir), str(backup_dir))
        shutil.move(str(pulled), str(target_dir))
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not target_dir.exists():
            shutil.move(str(backup_dir), str(target_dir))
        raise
    finally:
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        if pull_dest.exists():
            shutil.rmtree(pull_dest, ignore_errors=True)

    return {
        "name": str(getattr(ver, "name", name)),
        "organization": org_clean,
        "version": int(getattr(ver, "version", 1)),
        "digest": getattr(ver, "digest", None),
        "hash": hash_skill_dir(target_dir),
        "path": str(target_dir),
    }


def _personal_canonical_names(
    manifest_path: Path, home: Path
) -> tuple[set[str], set[str], set[str]]:
    manifest = load_skills_manifest(manifest_path)
    canonical, _ = _collect_canonical_skills(manifest, home)
    personal = {
        cname
        for cname, cmeta in canonical.items()
        if cmeta.get("sourceKind") in {"canonical-repo", "domain-repo"}
    }
    plugin_owned = set(manifest.plugin_owned_skills)
    for ag in manifest.alias_groups:
        plugin_owned.update(ag.names)
    return personal, plugin_owned, set(canonical.keys())


def publish_local_skills_to_mlflow(
    settings: MCPStackSettings,
    *,
    include_repos: bool = True,
    force_prod: bool = False,
    dry_run: bool = True,
    repos_root: Path | None = None,
    home_dir: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Publish manifest canonical skills and optional repo-local skills into MLflow 3.18."""
    if not dry_run and not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to publish skills into MLflow")

    home = (home_dir or Path.home()).resolve()
    r_root = (repos_root or settings.skills.repos_root).expanduser()
    mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
    manifest = load_skills_manifest(mpath)
    canonical, _ = _collect_canonical_skills(manifest, home)

    mlflow_mod = _ensure_mlflow_mod(settings, mlflow_module)
    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    # Index existing MLflow skills once for digest idempotency
    existing_map: dict[tuple[str, str], dict[str, Any]] = {}
    for sk in _search_all_skills(mlflow_mod, max_results=500):
        sk_name = str(getattr(sk, "name", "") or "")
        sk_org = str(getattr(sk, "organization", "") or "")
        aliases = dict(getattr(sk, "aliases", None) or {})
        latest_ver = None
        try:
            vers = list(
                client.search_skill_versions(name=sk_name, organization=sk_org, max_results=5)
            )
            vers.sort(key=lambda item: int(getattr(item, "version", 0)), reverse=True)
            latest_ver = vers[0] if vers else None
        except Exception:
            pass
        existing_map[(sk_org, sk_name)] = {"aliases": aliases, "latest": latest_ver}

    candidates: list[dict[str, Any]] = []
    seen_resolved: set[Path] = set()

    for cname, cmeta in sorted(canonical.items()):
        if cmeta.get("sourceKind") == "mlflow-registry":
            continue
        cpath = Path(str(cmeta["resolvedPath"]))
        seen_resolved.add(cpath)
        src_id = str(cmeta["sourceId"])
        org = _SOURCE_ORG_DEFAULTS.get(src_id, normalize_mlflow_org(str(cmeta["owner"])))
        candidates.append(
            {
                "name": cname,
                "organization": org,
                "dir": cpath,
                "scope": "shared",
                "sourceId": src_id,
            }
        )

    if include_repos and r_root.is_dir():
        seen_repos: set[Path] = set()
        for repo in sorted(r_root.iterdir()):
            if not repo.is_dir() or repo.is_symlink():
                continue
            resolved_repo = repo.resolve()
            if resolved_repo in seen_repos:
                continue
            seen_repos.add(resolved_repo)
            if repo.name == "mlflow_sme":
                continue
            org = normalize_mlflow_org(f"repo-{repo.name}")
            for sub in (".agents/skills", ".claude/skills", ".codex/skills", "skills"):
                sdir = resolved_repo / sub
                if not sdir.is_dir():
                    continue
                for entry in sorted(sdir.iterdir()):
                    if entry.name.startswith(".") or not entry.is_dir():
                        continue
                    if not (entry / "SKILL.md").is_file():
                        continue
                    ent_res = entry.resolve()
                    if ent_res in seen_resolved:
                        continue
                    seen_resolved.add(ent_res)
                    candidates.append(
                        {
                            "name": entry.name,
                            "organization": org,
                            "dir": ent_res,
                            "scope": "repo",
                            "sourceId": f"{repo.name}/{sub}",
                        }
                    )

    published: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for item in candidates:
        raw_name = str(item["name"])
        org = str(item["organization"])
        sdir = Path(item["dir"])
        try:
            mlflow_name = normalize_mlflow_name(raw_name)
        except ValueError as exc:
            errors.append({"name": raw_name, "organization": org, "error": str(exc)})
            continue

        digest = hash_skill_dir(sdir)
        is_clean, commit, repo_name = _git_skill_state(sdir)
        promote_prod = force_prod or is_clean or item["sourceId"] == "prose-hygiene"
        target_status = "active" if promote_prod else "draft"
        target_alias = "production" if promote_prod else "draft"

        existing = existing_map.get((org, mlflow_name))
        if existing and existing.get("latest") is not None:
            latest = existing["latest"]
            ltags = dict(getattr(latest, "tags", None) or {})
            lver = int(getattr(latest, "version", 0))
            aliases_map = dict(existing.get("aliases") or {})
            if (
                ltags.get("mcp_stack.content_digest") == digest
                and str(getattr(latest, "status", "")) == target_status
                and aliases_map.get(target_alias) == lver
            ):
                unchanged.append(
                    {
                        "name": mlflow_name,
                        "organization": org,
                        "version": lver,
                        "alias": target_alias,
                        "digest": digest,
                    }
                )
                continue

        entry_summary = {
            "name": mlflow_name,
            "organization": org,
            "scope": item["scope"],
            "source": str(sdir),
            "status": target_status,
            "alias": target_alias,
            "digest": digest,
            "gitCommit": commit or None,
            "dirty": not is_clean,
        }
        if dry_run:
            published.append({**entry_summary, "dryRun": True})
            continue

        try:
            ver = mlflow_mod.genai.register_skill(
                source=str(sdir),
                name=mlflow_name,
                organization=org,
                status=target_status,
            )
            ver_num = int(getattr(ver, "version", 1))
            client.set_skill_alias(
                name=mlflow_name,
                alias=target_alias,
                version=ver_num,
                organization=org,
            )
            _tag_skill_version_best_effort(
                client,
                name=mlflow_name,
                version=ver_num,
                organization=org,
                tags={
                    "mcp_stack.content_digest": digest,
                    "mcp_stack.scope": str(item["scope"]),
                    "mcp_stack.source_path": str(sdir),
                    "mcp_stack.git_commit": commit,
                    "mcp_stack.git_repo": repo_name,
                    "mcp_stack.dirty": "false" if is_clean else "true",
                },
            )
            published.append({**entry_summary, "version": ver_num})
        except Exception as exc:
            errors.append({"name": mlflow_name, "organization": org, "error": str(exc)})

    return {
        "dryRun": dry_run,
        "includeRepos": include_repos,
        "forceProd": force_prod,
        "publishedCount": len(published),
        "unchangedCount": len(unchanged),
        "errorCount": len(errors),
        "published": published,
        "unchanged": unchanged,
        "errors": errors,
    }


def _coerce_remote_git_source(resolved_src: str) -> Any:
    """Convert bare GitHub URLs into an MLflow GitSource so type inference succeeds."""
    raw = resolved_src.strip()
    match_tree = _GITHUB_TREE_RE.match(raw)
    if match_tree:
        owner, repo, ref, subpath = match_tree.groups()
        repo_url = f"https://github.com/{owner}/{repo}.git"
        clean_subpath = (subpath or "").strip("/") or None
        try:
            from mlflow.entities.skill_source import GitSource

            return GitSource(url=repo_url, ref=ref, subpath=clean_subpath)
        except ImportError:
            return repo_url

    match_repo = _GITHUB_REPO_RE.match(raw)
    if match_repo:
        owner, repo = match_repo.groups()
        repo_url = f"https://github.com/{owner}/{repo}.git"
        try:
            from mlflow.entities.skill_source import GitSource

            return GitSource(url=repo_url, ref=None, subpath=None)
        except ImportError:
            return repo_url

    return raw


def import_web_skill(
    settings: MCPStackSettings,
    *,
    source: str,
    organization: str = "web",
    skill_names: list[str] | None = None,
    name: str | None = None,
    allow_shadow: bool = False,
    materialize: bool = True,
    sync_harnesses: bool = True,
    lock_path: Path | None = None,
    materialize_root: Path | None = None,
    dry_run: bool = False,
    home_dir: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Import a web/third-party skill into MLflow 3.18, lockfile, cache, and harnesses."""
    if not dry_run and not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to import web skills")

    home = (home_dir or Path.home()).resolve()
    mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
    personal_names, _, _ = _personal_canonical_names(mpath, home)
    org_clean = normalize_mlflow_org(organization) if organization else "web"
    resolved_src = source.strip()
    if not resolved_src:
        raise ValueError("source is required")

    target_override = normalize_mlflow_name(name) if name else None
    if target_override and target_override in personal_names and not allow_shadow:
        raise ValueError(
            f"Refusing to shadow personal canonical skill '{target_override}'. "
            "Pass --name <alt> or --allow-shadow."
        )
    if skill_names and not allow_shadow:
        for req_name in skill_names:
            norm = normalize_mlflow_name(req_name)
            if norm in personal_names:
                raise ValueError(
                    f"Refusing to shadow personal canonical skill '{norm}'. "
                    "Pass --allow-shadow to override."
                )

    is_git_repo_url = resolved_src.startswith(("https://", "git://", "http://")) and (
        not resolved_src.lower().endswith(".zip")
    )
    if dry_run:
        return {
            "dryRun": True,
            "source": resolved_src,
            "organization": org_clean,
            "mode": "git_import" if (is_git_repo_url and not target_override) else "register",
            "skillNames": skill_names or ([target_override] if target_override else []),
        }

    mlflow_mod = _ensure_mlflow_mod(settings, mlflow_module)
    mlflow_mod.set_tracking_uri(settings.mlflow.tracking_uri)
    client = mlflow_mod.MlflowClient(tracking_uri=settings.mlflow.tracking_uri)

    versions: list[Any]
    remote_source = _coerce_remote_git_source(resolved_src) if is_git_repo_url else resolved_src
    if is_git_repo_url and not target_override and hasattr(mlflow_mod.genai, "import_skills"):
        versions = list(
            mlflow_mod.genai.import_skills(
                source=remote_source,
                organization=org_clean,
                skill_names=skill_names or None,
                status="active",
            )
        )
    else:
        src_arg: Any = remote_source if is_git_repo_url else resolved_src
        if not resolved_src.startswith(("https://", "git://", "http://", "oci://")):
            src_arg = str(Path(resolved_src).expanduser().resolve())
            inferred = target_override or normalize_mlflow_name(Path(src_arg).name)
            if inferred in personal_names and not allow_shadow:
                raise ValueError(
                    f"Refusing to shadow personal canonical skill '{inferred}'. "
                    "Pass --name <alt> or --allow-shadow."
                )
        ver = mlflow_mod.genai.register_skill(
            source=src_arg,
            name=target_override,
            organization=org_clean,
            status="active",
        )
        versions = [ver]

    lock_file = resolve_web_lock_path(settings, lock_path)
    lock_data = load_web_skills_lock(lock_file)
    imported_records: list[dict[str, Any]] = []

    for ver in versions:
        v_name = str(getattr(ver, "name", "") or "")
        v_num = int(getattr(ver, "version", 1))
        if v_name in personal_names and not allow_shadow:
            raise ValueError(
                f"Imported skill '{v_name}' conflicts with personal canonical skill."
            )
        client.set_skill_alias(
            name=v_name, alias="production", version=v_num, organization=org_clean
        )
        mat_res = (
            materialize_mlflow_skill(
                settings,
                v_name,
                organization=org_clean,
                version_or_alias=str(v_num),
                materialize_root=materialize_root,
                mlflow_module=mlflow_mod,
            )
            if materialize
            else {"hash": str(getattr(ver, "digest", "") or "")}
        )
        digest = str(mat_res.get("hash") or getattr(ver, "digest", "") or "")
        _tag_skill_version_best_effort(
            client,
            name=v_name,
            version=v_num,
            organization=org_clean,
            tags={
                "mcp_stack.origin_source": resolved_src,
                "mcp_stack.scope": "web",
                "mcp_stack.content_digest": digest,
            },
        )
        _upsert_lock_entry(
            lock_data,
            name=v_name,
            organization=org_clean,
            source=resolved_src,
            version=v_num,
            digest=digest,
            alias="production",
        )
        imported_records.append(
            {
                "name": v_name,
                "organization": org_clean,
                "version": v_num,
                "alias": "production",
                "digest": digest,
                "materializedPath": mat_res.get("path"),
            }
        )

    save_web_skills_lock(lock_file, lock_data)

    sync_res = None
    if sync_harnesses and materialize and mpath.exists():
        sync_res = sync_skills(load_skills_manifest(mpath), dry_run=False, home_dir=home)

    return {
        "importedCount": len(imported_records),
        "imported": imported_records,
        "lockFile": str(lock_file),
        "sync": sync_res,
    }


def absorb_skills_dir(
    settings: MCPStackSettings,
    source_dir: Path,
    *,
    organization: str = "web",
    dry_run: bool = True,
    skip_existing_personal: bool = True,
    skip_plugin_owned: bool = True,
    skip_repo_local: bool = True,
    sync_harnesses: bool = True,
    lock_path: Path | None = None,
    materialize_root: Path | None = None,
    home_dir: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Absorb valid skill folders from a directory (e.g. ~/.agents/skills) into MLflow web."""
    if not dry_run and not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to absorb skills into MLflow")

    home = (home_dir or Path.home()).resolve()
    src_root = source_dir.expanduser().resolve()
    if not src_root.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_root}")

    mpath = resolve_manifest_path(configured=settings.skills.manifest_path)
    personal_names, plugin_owned, _ = _personal_canonical_names(mpath, home)

    repo_skill_names: set[str] = set()
    r_root = settings.skills.repos_root.expanduser()
    if skip_repo_local and r_root.is_dir():
        for repo in r_root.iterdir():
            if not repo.is_dir() or repo.is_symlink():
                continue
            for sub in (".agents/skills", ".claude/skills", ".codex/skills", "skills"):
                sd = repo / sub
                if sd.is_dir():
                    for ent in sd.iterdir():
                        if (ent / "SKILL.md").is_file():
                            repo_skill_names.add(ent.name)

    absorbed: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for item in sorted(src_root.iterdir()):
        if item.name.startswith(".") or not item.is_dir():
            continue
        if not (item / "SKILL.md").is_file():
            skipped.append({"name": item.name, "reason": "missing SKILL.md"})
            continue
        if skip_existing_personal and item.name in personal_names:
            skipped.append({"name": item.name, "reason": "already managed by personal manifest"})
            continue
        if skip_plugin_owned and item.name in plugin_owned:
            skipped.append({"name": item.name, "reason": "plugin/alias-owned skill"})
            continue
        if skip_repo_local and item.name in repo_skill_names:
            skipped.append({"name": item.name, "reason": "managed inside repo-local skills"})
            continue

        if dry_run:
            absorbed.append(
                {
                    "name": item.name,
                    "organization": organization,
                    "source": str(item),
                    "dryRun": True,
                }
            )
            continue

        try:
            res = import_web_skill(
                settings,
                source=str(item),
                organization=organization,
                materialize=True,
                sync_harnesses=False,
                lock_path=lock_path,
                materialize_root=materialize_root,
                dry_run=False,
                home_dir=home,
                mlflow_module=mlflow_module,
            )
            absorbed.extend(res["imported"])
        except Exception as exc:
            errors.append({"name": item.name, "error": str(exc)})

    sync_res = None
    if not dry_run and sync_harnesses and absorbed and mpath.exists():
        sync_res = sync_skills(load_skills_manifest(mpath), dry_run=False, home_dir=home)

    return {
        "dryRun": dry_run,
        "sourceDir": str(src_root),
        "organization": organization,
        "absorbedCount": len(absorbed),
        "skippedCount": len(skipped),
        "errorCount": len(errors),
        "absorbed": absorbed,
        "skipped": skipped,
        "errors": errors,
        "sync": sync_res,
    }


def upgrade_web_skills(
    settings: MCPStackSettings,
    *,
    names: list[str] | None = None,
    dry_run: bool = True,
    lock_path: Path | None = None,
    materialize_root: Path | None = None,
    home_dir: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Re-fetch remote web skills in web-skills-lock.yaml and advance @production if changed."""
    if not dry_run and not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to upgrade web skills")

    lock_file = resolve_web_lock_path(settings, lock_path)
    lock_data = load_web_skills_lock(lock_file)
    wanted = set(names) if names else None
    upgraded: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for entry in lock_data.get("skills") or []:
        name = str(entry.get("name") or "")
        org = str(entry.get("organization") or "web")
        src = str(entry.get("source") or "")
        if wanted is not None and name not in wanted:
            continue
        if not src.startswith(("https://", "git://", "http://", "oci://")):
            src_path = Path(src).expanduser()
            if not src_path.exists():
                skipped.append({"name": name, "reason": "non-remote source without live path"})
                continue
        if dry_run:
            upgraded.append({"name": name, "organization": org, "source": src, "dryRun": True})
            continue
        try:
            res = import_web_skill(
                settings,
                source=src,
                organization=org,
                name=name if not src.startswith(("https://", "git://", "http://")) else None,
                skill_names=[name] if src.startswith(("https://", "git://", "http://")) else None,
                allow_shadow=True,
                materialize=True,
                sync_harnesses=False,
                lock_path=lock_file,
                materialize_root=materialize_root,
                dry_run=False,
                home_dir=home_dir,
                mlflow_module=mlflow_module,
            )
            upgraded.extend(res["imported"])
        except Exception as exc:
            errors.append({"name": name, "error": str(exc)})

    return {
        "dryRun": dry_run,
        "lockFile": str(lock_file),
        "upgradedCount": len(upgraded),
        "skippedCount": len(skipped),
        "errorCount": len(errors),
        "upgraded": upgraded,
        "skipped": skipped,
        "errors": errors,
    }


def restore_registry_from_lockfile(
    settings: MCPStackSettings,
    *,
    dry_run: bool = True,
    lock_path: Path | None = None,
    materialize_root: Path | None = None,
    home_dir: Path | None = None,
    mlflow_module: Any | None = None,
) -> dict[str, Any]:
    """Rebuild MLflow Skill Registry from skills-manifest.yaml and web-skills-lock.yaml."""
    if not dry_run and not settings.mlflow.allow_mutations:
        raise PermissionError("Set MLFLOW_ALLOW_MUTATIONS=true to restore MLflow Skill Registry")

    pub_res = publish_local_skills_to_mlflow(
        settings,
        include_repos=True,
        dry_run=dry_run,
        home_dir=home_dir,
        mlflow_module=mlflow_module,
    )
    lock_file = resolve_web_lock_path(settings, lock_path)
    lock_data = load_web_skills_lock(lock_file)
    mat_root = (
        materialize_root or Path(str(lock_data.get("materialize_root") or DEFAULT_MATERIALIZE_ROOT))
    ).expanduser()

    restored_web: list[dict[str, Any]] = []
    web_errors: list[dict[str, str]] = []
    for entry in lock_data.get("skills") or []:
        name = str(entry.get("name") or "")
        org = str(entry.get("organization") or "web")
        src = str(entry.get("source") or "")
        cached = mat_root / org / name
        chosen = str(cached) if (cached / "SKILL.md").is_file() else src
        if dry_run:
            restored_web.append(
                {"name": name, "organization": org, "source": chosen, "dryRun": True}
            )
            continue
        try:
            res = import_web_skill(
                settings,
                source=chosen,
                organization=org,
                name=name if Path(chosen).exists() else None,
                allow_shadow=True,
                materialize=not Path(chosen).exists(),
                sync_harnesses=False,
                lock_path=lock_file,
                materialize_root=mat_root,
                dry_run=False,
                home_dir=home_dir,
                mlflow_module=mlflow_module,
            )
            restored_web.extend(res["imported"])
        except Exception as exc:
            web_errors.append({"name": name, "error": str(exc)})

    return {
        "dryRun": dry_run,
        "localPublish": pub_res,
        "webRestoredCount": len(restored_web),
        "webErrorCount": len(web_errors),
        "webRestored": restored_web,
        "webErrors": web_errors,
    }
