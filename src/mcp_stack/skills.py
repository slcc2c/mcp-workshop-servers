"""5-layer skill registry, collision auditor, symlink projector, and recoverable quarantine."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

_IGNORED_HASH_FILENAMES = frozenset({".DS_Store", ".skillfish.json"})
_IGNORED_HASH_PARTS = frozenset({"__pycache__", ".git"})
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillSourceSpec(BaseModel):
    """Canonical source directory containing owned SKILL.md folders."""

    path: str
    kind: Literal["canonical-repo", "domain-repo", "vendor-plugin"] = "canonical-repo"
    owner: str = "personal"
    include_all: bool = False
    skills: list[str] = Field(default_factory=list)
    atelier_managed: list[str] = Field(default_factory=list)


class SkillTargetSpec(BaseModel):
    """Target harness directory where symlinks are projected."""

    dir: str
    sources: list[str] = Field(default_factory=list)
    ignore_names: list[str] = Field(default_factory=list)
    preserve_unlisted: bool = False


class LegacyRootSpec(BaseModel):
    """Legacy skill directory slated for recoverable quarantine cleanup."""

    path: str
    reason: str = ""
    ignore_names: list[str] = Field(default_factory=list)


class AliasGroupSpec(BaseModel):
    """Semantic group of skill names that collide even when renamed."""

    id: str
    names: list[str]
    canonical_owner: str = ""
    recommendation: str = ""


class SkillsManifest(BaseModel):
    """Declarative manifest governing canonical skills, harness targets, and collision rules."""

    version: int = 1
    quarantine_root: str = "~/.local/share/mcp-stack/skill-quarantine"
    sources: dict[str, SkillSourceSpec] = Field(default_factory=dict)
    targets: dict[str, SkillTargetSpec] = Field(default_factory=dict)
    legacy_cleanup_roots: list[LegacyRootSpec] = Field(default_factory=list)
    plugin_owned_skills: list[str] = Field(default_factory=list)
    alias_groups: list[AliasGroupSpec] = Field(default_factory=list)


def _expand_user_path(raw: str, home: Path) -> Path:
    text = raw.strip()
    if text == "~":
        return home
    if text.startswith("~/"):
        return home / text[2:]
    return Path(text).expanduser()


def resolve_manifest_path(
    explicit: Path | None = None,
    *,
    configured: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve the active skills manifest path, falling back to repo config if needed."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    if configured is not None:
        candidates.append(configured.expanduser())
    base = repo_root or Path.cwd()
    candidates.extend(
        [
            base / "config" / "skills-manifest.yaml",
            base / "config" / "skills-manifest.example.yaml",
        ]
    )
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def load_skills_manifest(path: Path) -> SkillsManifest:
    """Load and validate a skills-manifest.yaml file."""
    resolved = path.expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Skills manifest not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Skills manifest must be a YAML mapping: {resolved}")
    return SkillsManifest.model_validate(data)


def parse_skill_frontmatter(skill_md: Path) -> dict[str, str]:
    """Extract name and description from SKILL.md frontmatter."""
    if not skill_md.exists():
        return {"name": skill_md.parent.name, "description": ""}
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {"name": skill_md.parent.name, "description": ""}
    try:
        meta = yaml.safe_load(match.group(1))
    except Exception:
        meta = None
    if not isinstance(meta, dict):
        return {"name": skill_md.parent.name, "description": ""}
    return {
        "name": str(meta.get("name") or skill_md.parent.name).strip(),
        "description": str(meta.get("description") or "").strip(),
    }


def hash_skill_dir(skill_dir: Path) -> str:
    """Compute a deterministic SHA-256 short digest of a skill directory."""
    h = hashlib.sha256()
    resolved = skill_dir.resolve()
    if not resolved.exists() or not resolved.is_dir():
        return ""
    for item in sorted(resolved.rglob("*")):
        if not item.is_file():
            continue
        if item.name in _IGNORED_HASH_FILENAMES:
            continue
        if any(part in _IGNORED_HASH_PARTS for part in item.relative_to(resolved).parts):
            continue
        h.update(str(item.relative_to(resolved)).encode("utf-8"))
        h.update(b"\x00")
        h.update(item.read_bytes())
    return h.hexdigest()[:12]


def _collect_canonical_skills(
    manifest: SkillsManifest,
    home: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build canonical skill map keyed by skill directory name."""
    canonical: dict[str, dict[str, Any]] = {}
    missing_sources: list[str] = []

    for src_id, spec in manifest.sources.items():
        src_dir = _expand_user_path(spec.path, home)
        if not src_dir.exists():
            missing_sources.append(f"{src_id}: {src_dir}")
            continue
        if spec.include_all:
            names = sorted(
                d.name
                for d in src_dir.iterdir()
                if not d.name.startswith(".") and d.is_dir() and (d / "SKILL.md").exists()
            )
        else:
            names = list(dict.fromkeys([*spec.skills, *spec.atelier_managed]))

        atelier_set = set(spec.atelier_managed)
        for name in names:
            skill_path = src_dir / name
            if not (skill_path / "SKILL.md").exists():
                missing_sources.append(f"{src_id}/{name}: missing SKILL.md at {skill_path}")
                continue
            meta = parse_skill_frontmatter(skill_path / "SKILL.md")
            canonical[name] = {
                "name": name,
                "frontmatterName": meta["name"],
                "description": meta["description"],
                "sourceId": src_id,
                "sourceKind": spec.kind,
                "owner": spec.owner,
                "canonicalPath": str(skill_path),
                "resolvedPath": str(skill_path.resolve()),
                "hash": hash_skill_dir(skill_path),
                "atelierManaged": name in atelier_set,
            }
    return canonical, missing_sources


def _scan_plugin_layers(home: Path) -> list[dict[str, Any]]:
    """Layer 3: read-only scan of enabled Claude/Codex/Antigravity plugins and synced buckets."""
    found: list[dict[str, Any]] = []

    claude_enabled_map: dict[str, bool] = {}
    claude_settings_path = home / ".claude/settings.json"
    try:
        if claude_settings_path.exists():
            c_cfg = json.loads(claude_settings_path.read_text(encoding="utf-8"))
            if isinstance(c_cfg, dict) and isinstance(c_cfg.get("enabledPlugins"), dict):
                claude_enabled_map = {
                    str(k): bool(v) for k, v in c_cfg["enabledPlugins"].items()
                }
    except Exception:
        pass

    # Claude installed_plugins.json (skip plugins explicitly disabled in ~/.claude/settings.json)
    ip_path = home / ".claude/plugins/installed_plugins.json"
    try:
        if ip_path.exists():
            raw = json.loads(ip_path.read_text(encoding="utf-8"))
            plugins = raw.get("plugins", raw) if isinstance(raw, dict) else {}
            if isinstance(plugins, dict):
                for plugin_id, entries in sorted(plugins.items()):
                    if claude_enabled_map.get(plugin_id) is False:
                        continue
                    items = entries if isinstance(entries, list) else [entries]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        inst = item.get("installPath")
                        if not isinstance(inst, str) or not Path(inst).exists():
                            continue
                        for smd in sorted(Path(inst).rglob("SKILL.md")):
                            found.append(
                                {
                                    "skill": smd.parent.name,
                                    "layer": "claude-plugin",
                                    "origin": plugin_id,
                                    "path": str(smd.parent),
                                }
                            )
    except Exception:
        pass

    # Claude synced bucket (~/.claude/skills/synced)
    synced_dir = home / ".claude/skills/synced"
    try:
        if synced_dir.exists():
            for smd in sorted(synced_dir.rglob("SKILL.md")):
                found.append(
                    {
                        "skill": smd.parent.name,
                        "layer": "claude-synced",
                        "origin": smd.parent.parent.name,
                        "path": str(smd.parent),
                    }
                )
    except OSError:
        pass

    disabled_codex_plugins: set[str] = set()
    codex_cfg_path = home / ".codex/config.toml"
    try:
        if codex_cfg_path.exists():
            cx_cfg = tomllib.loads(codex_cfg_path.read_text(encoding="utf-8"))
            for k, v in (cx_cfg.get("plugins") or {}).items():
                if isinstance(v, dict) and v.get("enabled") is False:
                    disabled_codex_plugins.add(str(k))
    except Exception:
        pass

    # Codex plugin cache (~/.codex/plugins/cache/<marketplace>/<plugin>/...)
    codex_cache = home / ".codex/plugins/cache"
    try:
        if codex_cache.exists():
            seen_cx: set[tuple[str, str]] = set()
            for smd in sorted(codex_cache.rglob("SKILL.md")):
                rel = smd.relative_to(codex_cache)
                if len(rel.parts) >= 2:
                    plugin_key = f"{rel.parts[1]}@{rel.parts[0]}"
                    if plugin_key in disabled_codex_plugins:
                        continue
                    origin = "/".join(rel.parts[:2])
                else:
                    origin = rel.parts[0]
                key = (smd.parent.name, origin)
                if key in seen_cx:
                    continue
                seen_cx.add(key)
                found.append(
                    {
                        "skill": smd.parent.name,
                        "layer": "codex-plugin",
                        "origin": origin,
                        "path": str(smd.parent),
                    }
                )
    except OSError:
        pass

    # Antigravity / Gemini plugins (~/.gemini/config/plugins)
    gemini_plugins = home / ".gemini/config/plugins"
    try:
        if gemini_plugins.exists():
            for plugin_dir in sorted(gemini_plugins.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                sk_dir = plugin_dir / "skills"
                if not sk_dir.exists():
                    continue
                for entry in sorted(sk_dir.iterdir()):
                    if (entry / "SKILL.md").exists():
                        found.append(
                            {
                                "skill": entry.name,
                                "layer": "antigravity-plugin",
                                "origin": plugin_dir.name,
                                "path": str(entry),
                                "isSymlink": entry.is_symlink(),
                            }
                        )
    except OSError:
        pass
    return found


def _scan_repo_local_skills(repos_root: Path) -> list[dict[str, Any]]:
    """Layer 4: read-only scan of repo-local {.agents,.claude,.codex}/skills across repos."""
    found: list[dict[str, Any]] = []
    try:
        if not repos_root.exists() or not repos_root.is_dir():
            return found
        repo_list = sorted(repos_root.iterdir())
    except OSError:
        return found
    seen_repos: set[Path] = set()
    for repo in repo_list:
        try:
            if not repo.is_dir():
                continue
            resolved_repo = repo.resolve()
        except OSError:
            continue
        if resolved_repo in seen_repos:
            continue
        seen_repos.add(resolved_repo)
        for rel_sub in (".agents/skills", ".claude/skills", ".codex/skills"):
            sk_dir = resolved_repo / rel_sub
            try:
                if not sk_dir.exists() or not sk_dir.is_dir():
                    continue
                entries = sorted(sk_dir.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if (entry / "SKILL.md").exists():
                        found.append(
                            {
                                "skill": entry.name,
                                "repo": repo.name,
                                "subpath": rel_sub,
                                "path": str(entry),
                                "isSymlink": entry.is_symlink(),
                                "hash": hash_skill_dir(entry),
                            }
                        )
                except OSError:
                    continue
    return found


def audit_skills(
    manifest: SkillsManifest,
    *,
    home_dir: Path | None = None,
    repos_root: Path | None = None,
) -> dict[str, Any]:
    """Run a 5-layer audit of canonical sources, harness targets, plugins, repos, and aliases."""
    home = (home_dir or Path.home()).resolve()
    r_root = (
        repos_root.expanduser() if repos_root is not None else (home / "repos")
    )
    canonical, source_warnings = _collect_canonical_skills(manifest, home)

    # Layer 2: target harness projections
    target_reports: dict[str, dict[str, Any]] = {}
    per_skill_targets: dict[str, dict[str, str]] = {name: {} for name in canonical}
    target_issues: list[dict[str, Any]] = []

    for target_id, tspec in manifest.targets.items():
        tdir = _expand_user_path(tspec.dir, home)
        ignored = set(tspec.ignore_names) | {".DS_Store"}
        expected_names: list[str] = []
        for sid in tspec.sources:
            src_spec = manifest.sources.get(sid)
            if src_spec is None:
                continue
            for cname, cmeta in canonical.items():
                if cmeta["sourceId"] == sid and cname not in expected_names:
                    expected_names.append(cname)

        entries_status: dict[str, dict[str, Any]] = {}
        counts = {
            "synced": 0,
            "atelier_managed": 0,
            "missing": 0,
            "drifted_copy": 0,
            "wrong_target": 0,
            "extra_unmanaged": 0,
        }

        for cname in expected_names:
            cmeta = canonical[cname]
            cand = tdir / cname
            is_atelier = bool(cmeta.get("atelierManaged"))
            if not cand.exists() and not cand.is_symlink():
                status = "missing"
                detail = f"Not present in {tdir}"
            elif is_atelier:
                status = "atelier_managed"
                detail = "Preserved under atelier-installer ownership"
            elif cand.is_symlink():
                try:
                    resolved = str(cand.resolve())
                except OSError:
                    resolved = ""
                if resolved == cmeta["resolvedPath"]:
                    status = "synced"
                    detail = f"Symlink -> {cmeta['canonicalPath']}"
                else:
                    status = "wrong_target"
                    detail = f"Symlink points to {resolved or 'broken target'}"
            else:
                local_hash = hash_skill_dir(cand)
                same = local_hash == cmeta["hash"]
                status = "drifted_copy"
                detail = (
                    "Static copy (identical content; replace with symlink)"
                    if same
                    else "Static copy (DIVERGED from canonical source)"
                )
            counts[status] += 1
            entries_status[cname] = {"status": status, "detail": detail}
            per_skill_targets[cname][target_id] = status
            if status in {"missing", "drifted_copy", "wrong_target"}:
                target_issues.append(
                    {
                        "target": target_id,
                        "skill": cname,
                        "status": status,
                        "path": str(cand),
                        "detail": detail,
                    }
                )

        extra_names: list[str] = []
        if tdir.exists() and not tspec.preserve_unlisted:
            expected_set = set(expected_names)
            for item in sorted(tdir.iterdir()):
                if item.name in ignored or item.name.startswith("."):
                    continue
                if item.name not in expected_set and (
                    item.is_symlink() or (item / "SKILL.md").exists()
                ):
                    extra_names.append(item.name)
                    counts["extra_unmanaged"] += 1
                    target_issues.append(
                        {
                            "target": target_id,
                            "skill": item.name,
                            "status": "extra_unmanaged",
                            "path": str(item),
                            "detail": "Not listed in manifest for this target",
                        }
                    )

        target_reports[target_id] = {
            "dir": str(tdir),
            "exists": tdir.exists(),
            "expectedCount": len(expected_names),
            "counts": counts,
            "extraUnmanaged": extra_names,
            "skills": entries_status,
        }

    # Layer 3 & 4: plugin caches and repo-local skills
    plugin_entries = _scan_plugin_layers(home)
    repo_entries = _scan_repo_local_skills(r_root)

    # Layer 5: Legacy cleanup roots
    legacy_items: list[dict[str, Any]] = []
    for lspec in manifest.legacy_cleanup_roots:
        ldir = _expand_user_path(lspec.path, home)
        if not ldir.exists():
            continue
        l_ignore = set(lspec.ignore_names)
        for item in sorted(ldir.iterdir()):
            if item.name in l_ignore or item.name.startswith("."):
                continue
            if item.is_symlink() or (item / "SKILL.md").exists():
                legacy_items.append(
                    {
                        "root": str(ldir),
                        "skill": item.name,
                        "path": str(item),
                        "reason": lspec.reason,
                    }
                )

    # Collision & alias group detection across all layers
    plugin_owned_set = set(manifest.plugin_owned_skills)
    collisions: list[dict[str, Any]] = []

    # Check plugin-owned skills appearing in user target dirs or canonical sources
    for pskill in sorted(plugin_owned_set):
        occurrences: list[dict[str, str]] = []
        for tid, trep in target_reports.items():
            if pskill in trep["extraUnmanaged"] or pskill in trep["skills"]:
                occurrences.append({"layer": f"target:{tid}", "path": f"{trep['dir']}/{pskill}"})
        for pe in plugin_entries:
            if pe["skill"] == pskill:
                occurrences.append(
                    {
                        "layer": pe["layer"],
                        "path": pe["path"],
                        "origin": pe["origin"],
                    }
                )
        for re_item in repo_entries:
            if re_item["skill"] == pskill:
                occurrences.append(
                    {
                        "layer": f"repo:{re_item['repo']}/{re_item['subpath']}",
                        "path": re_item["path"],
                    }
                )
        if len(occurrences) > 1 or any(o["layer"].startswith("target:") for o in occurrences):
            collisions.append(
                {
                    "group": pskill,
                    "kind": "plugin-owned-shadow",
                    "occurrences": occurrences,
                    "recommendation": (
                        f"Plugin/built-in owns '{pskill}'. "
                        "Quarantine user-dir copies and keep one layer."
                    ),
                }
            )

    # Evaluate explicit alias groups
    for ag in manifest.alias_groups:
        name_set = set(ag.names)
        occurrences = []
        for cname, cmeta in canonical.items():
            if cname in name_set:
                occurrences.append(
                    {
                        "layer": f"canonical:{cmeta['sourceId']}",
                        "path": cmeta["canonicalPath"],
                    }
                )
        for tid, trep in target_reports.items():
            for ex in trep["extraUnmanaged"]:
                if ex in name_set:
                    occurrences.append({"layer": f"target:{tid}", "path": f"{trep['dir']}/{ex}"})
        for pe in plugin_entries:
            if pe["skill"] in name_set:
                occurrences.append(
                    {
                        "layer": pe["layer"],
                        "path": pe["path"],
                        "origin": pe["origin"],
                    }
                )
        for re_item in repo_entries:
            if re_item["skill"] in name_set:
                occurrences.append(
                    {
                        "layer": f"repo:{re_item['repo']}/{re_item['subpath']}",
                        "path": re_item["path"],
                    }
                )
        distinct_layers = {
            f"{o['layer']}:{o.get('origin', '')}" for o in occurrences
        }
        if len(distinct_layers) > 1:
            collisions.append(
                {
                    "group": ag.id,
                    "kind": "alias-collision",
                    "names": ag.names,
                    "canonicalOwner": ag.canonical_owner,
                    "occurrences": occurrences,
                    "recommendation": ag.recommendation
                    or f"Consolidate {ag.names} under {ag.canonical_owner or 'one owner'}.",
                }
            )

    # Repo-local dual-dir duplicates (.agents/skills + .claude/skills in same repo)
    by_repo_skill: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for re_item in repo_entries:
        by_repo_skill.setdefault((re_item["repo"], re_item["skill"]), []).append(re_item)
    repo_dual_copies = [
        {
            "repo": repo,
            "skill": sk,
            "paths": [x["path"] for x in items],
            "allSymlinks": all(x["isSymlink"] for x in items),
        }
        for (repo, sk), items in sorted(by_repo_skill.items())
        if len(items) > 1 and not any(x["isSymlink"] for x in items)
    ]

    skills_matrix = [
        {
            **cmeta,
            "targets": per_skill_targets.get(cname, {}),
        }
        for cname, cmeta in sorted(canonical.items())
    ]

    total_synced = sum(
        t["counts"]["synced"] + t["counts"]["atelier_managed"]
        for t in target_reports.values()
    )
    total_drift = sum(
        t["counts"]["missing"]
        + t["counts"]["drifted_copy"]
        + t["counts"]["wrong_target"]
        + t["counts"]["extra_unmanaged"]
        for t in target_reports.values()
    )

    return {
        "available": True,
        "summary": {
            "canonicalSkills": len(canonical),
            "targets": len(target_reports),
            "syncedLinks": total_synced,
            "driftIssues": total_drift,
            "collisions": len(collisions),
            "legacyItems": len(legacy_items),
            "repoDualCopies": len(repo_dual_copies),
            "pluginSkills": len(plugin_entries),
        },
        "sourceWarnings": source_warnings,
        "skills": skills_matrix,
        "targets": target_reports,
        "targetIssues": target_issues,
        "collisions": collisions,
        "legacyItems": legacy_items,
        "repoDualCopies": repo_dual_copies,
        "pluginSkills": plugin_entries,
    }


def _quarantine_item(
    src: Path,
    quarantine_batch: Path,
    rel_bucket: str,
    reason: str,
    records: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    dest = quarantine_batch / rel_bucket / src.name
    action: dict[str, Any] = {
        "action": "quarantine",
        "original": str(src),
        "quarantined": str(dest),
        "reason": reason,
        "wasSymlink": src.is_symlink(),
    }
    if src.is_symlink():
        try:
            action["symlinkTarget"] = str(src.readlink())
        except OSError:
            action["symlinkTarget"] = ""
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest = dest.with_name(f"{dest.name}-{datetime.now(UTC).strftime('%H%M%S%f')}")
            action["quarantined"] = str(dest)
        if src.is_symlink():
            dest.write_text(action.get("symlinkTarget", ""), encoding="utf-8")
            src.unlink()
        else:
            shutil.move(str(src), str(dest))
        records.append(action)
    return action


def sync_skills(
    manifest: SkillsManifest,
    *,
    dry_run: bool = True,
    quarantine_legacy: bool = False,
    targets: list[str] | None = None,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Project canonical skill symlinks into harness targets with recoverable quarantine."""
    home = (home_dir or Path.home()).resolve()
    canonical, source_warnings = _collect_canonical_skills(manifest, home)
    q_root = _expand_user_path(manifest.quarantine_root, home)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = q_root / stamp

    selected_targets = set(targets) if targets else set(manifest.targets.keys())
    unknown = selected_targets - set(manifest.targets.keys())
    if unknown:
        raise ValueError(f"Unknown skill sync target(s): {sorted(unknown)}")

    actions: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for target_id in manifest.targets:
        if target_id not in selected_targets:
            continue
        tspec = manifest.targets[target_id]
        tdir = _expand_user_path(tspec.dir, home)
        ignored = set(tspec.ignore_names) | {".DS_Store"}
        if not dry_run:
            tdir.mkdir(parents=True, exist_ok=True)

        expected: dict[str, dict[str, Any]] = {}
        for sid in tspec.sources:
            for cname, cmeta in canonical.items():
                if cmeta["sourceId"] == sid and cname not in expected:
                    expected[cname] = cmeta

        # 1. Remove/quarantine extra_unmanaged entries
        if tdir.exists() and not tspec.preserve_unlisted:
            for item in sorted(tdir.iterdir()):
                if item.name in ignored or item.name.startswith("."):
                    continue
                if item.name not in expected and (
                    item.is_symlink() or (item / "SKILL.md").exists()
                ):
                    actions.append(
                        _quarantine_item(
                            item,
                            batch_dir,
                            f"targets/{target_id}",
                            "extra_unmanaged",
                            records,
                            dry_run=dry_run,
                        )
                    )

        # 2. Ensure each expected skill is synced
        for cname, cmeta in sorted(expected.items()):
            dest = tdir / cname
            src_resolved = Path(cmeta["resolvedPath"])
            if cmeta.get("atelierManaged") and (dest.exists() or dest.is_symlink()):
                continue
            if dest.is_symlink():
                try:
                    if dest.resolve() == src_resolved:
                        continue
                except OSError:
                    pass
                actions.append(
                    _quarantine_item(
                        dest,
                        batch_dir,
                        f"targets/{target_id}",
                        "wrong_target",
                        records,
                        dry_run=dry_run,
                    )
                )
            elif dest.exists():
                actions.append(
                    _quarantine_item(
                        dest,
                        batch_dir,
                        f"targets/{target_id}",
                        "drifted_copy",
                        records,
                        dry_run=dry_run,
                    )
                )

            link_action = {
                "action": "symlink",
                "target": target_id,
                "skill": cname,
                "link": str(dest),
                "source": str(src_resolved),
            }
            if not dry_run:
                dest.symlink_to(src_resolved)
            actions.append(link_action)

    # 3. Clean legacy roots if requested
    if quarantine_legacy:
        for idx, lspec in enumerate(manifest.legacy_cleanup_roots):
            ldir = _expand_user_path(lspec.path, home)
            if not ldir.exists():
                continue
            l_ignore = set(lspec.ignore_names)
            bucket = f"legacy/{idx}_{ldir.parent.name}_{ldir.name}"
            for item in sorted(ldir.iterdir()):
                if item.name in l_ignore or item.name.startswith("."):
                    continue
                if item.is_symlink() or (item / "SKILL.md").exists():
                    actions.append(
                        _quarantine_item(
                            item,
                            batch_dir,
                            bucket,
                            lspec.reason or "legacy_cleanup",
                            records,
                            dry_run=dry_run,
                        )
                    )

    manifest_file: Path | None = None
    if not dry_run and records:
        batch_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = batch_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "createdAt": stamp,
                    "records": records,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        "dryRun": dry_run,
        "quarantineLegacy": quarantine_legacy,
        "quarantineBatch": str(batch_dir) if (not dry_run and records) else None,
        "manifestFile": str(manifest_file) if manifest_file else None,
        "sourceWarnings": source_warnings,
        "actionCount": len(actions),
        "quarantinedCount": sum(1 for a in actions if a["action"] == "quarantine"),
        "symlinkedCount": sum(1 for a in actions if a["action"] == "symlink"),
        "actions": actions,
    }


def promote_skill(
    manifest_path: Path,
    source_or_name: str,
    *,
    skill_name: str | None = None,
    source_id: str = "atelier-personal",
    dry_run: bool = True,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Promote a skill directory (or quarantined skill name) into canonical atelier storage."""
    home = (home_dir or Path.home()).resolve()
    manifest = load_skills_manifest(manifest_path)
    src_spec = manifest.sources.get(source_id)
    if src_spec is None:
        raise ValueError(f"Unknown canonical source id: {source_id}")

    candidate = Path(source_or_name).expanduser()
    if not candidate.exists():
        # Search legacy roots and latest quarantine batches by name
        search_dirs: list[Path] = [
            _expand_user_path(legacy_spec.path, home) / source_or_name
            for legacy_spec in manifest.legacy_cleanup_roots
        ]
        q_root = _expand_user_path(manifest.quarantine_root, home)
        if q_root.exists():
            for batch in sorted(q_root.iterdir(), reverse=True):
                if batch.is_dir():
                    for found in batch.rglob(source_or_name):
                        if found.is_dir() and (found / "SKILL.md").exists():
                            search_dirs.append(found)
        resolved_src = next((p for p in search_dirs if (p / "SKILL.md").exists()), None)
        if resolved_src is None:
            raise FileNotFoundError(
                f"Skill '{source_or_name}' not found at path, legacy roots, or quarantine."
            )
        candidate = resolved_src

    if not (candidate / "SKILL.md").exists():
        raise ValueError(f"Source directory does not contain SKILL.md: {candidate}")

    target_name = (skill_name or candidate.name).strip()
    dest_dir = _expand_user_path(src_spec.path, home) / target_name

    if not dry_run:
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(
            candidate,
            dest_dir,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", ".skillfish.json"),
        )
        raw_yaml = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        src_block = raw_yaml.setdefault("sources", {}).setdefault(source_id, {})
        skills_list = list(src_block.get("skills") or [])
        if target_name not in skills_list and target_name not in (
            src_block.get("atelier_managed") or []
        ):
            skills_list.append(target_name)
            src_block["skills"] = skills_list
            manifest_path.write_text(yaml.safe_dump(raw_yaml, sort_keys=False), encoding="utf-8")

    sync_res = (
        sync_skills(load_skills_manifest(manifest_path), dry_run=dry_run, home_dir=home)
        if not dry_run
        else {
            "dryRun": True,
            "note": "Re-run with --apply to copy, register, and project symlinks.",
        }
    )
    return {
        "dryRun": dry_run,
        "skill": target_name,
        "source": str(candidate),
        "canonicalDest": str(dest_dir),
        "sync": sync_res,
    }


def rollback_quarantine(batch_dir: Path, *, dry_run: bool = True) -> dict[str, Any]:
    """Restore quarantined skills/symlinks from a batch's manifest.json."""
    resolved_batch = batch_dir.expanduser().resolve()
    manifest_file = resolved_batch / "manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Quarantine manifest.json not found: {manifest_file}")
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for rec in records:
        orig = Path(rec["original"])
        quarantined = Path(rec["quarantined"])
        if not quarantined.exists() and not quarantined.is_symlink():
            skipped.append({"original": str(orig), "reason": "quarantined copy missing"})
            continue
        if orig.exists() and not orig.is_symlink():
            skipped.append(
                {
                    "original": str(orig),
                    "reason": "destination already exists (non-symlink)",
                }
            )
            continue
        if not dry_run:
            orig.parent.mkdir(parents=True, exist_ok=True)
            if orig.is_symlink():
                orig.unlink()
            if rec.get("wasSymlink"):
                target_str = (
                    rec.get("symlinkTarget")
                    or quarantined.read_text(encoding="utf-8").strip()
                )
                orig.symlink_to(target_str)
            else:
                shutil.move(str(quarantined), str(orig))
        restored.append({"original": str(orig), "from": str(quarantined)})

    return {
        "dryRun": dry_run,
        "batchDir": str(resolved_batch),
        "restoredCount": len(restored),
        "skippedCount": len(skipped),
        "restored": restored,
        "skipped": skipped,
    }


def dedupe_repo_dual_skills(
    repos_root: Path,
    *,
    repo_names: list[str] | None = None,
    quarantine_root: Path | None = None,
    dry_run: bool = True,
    home_dir: Path | None = None,
) -> dict[str, Any]:
    """Quarantine identical .claude/skills/<name> copies and link to ../../.agents/skills/<name>."""
    home = (home_dir or Path.home()).resolve()
    r_root = repos_root.expanduser()
    q_base = (
        quarantine_root.expanduser()
        if quarantine_root is not None
        else home / ".local/share/mcp-stack/skill-quarantine"
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = q_base / f"{stamp}-repo-symlinks"

    wanted = set(repo_names) if repo_names else None
    actions: list[dict[str, Any]] = []
    skipped_diverged: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    if r_root.exists() and r_root.is_dir():
        seen_repos: set[Path] = set()
        for repo in sorted(r_root.iterdir()):
            if not repo.is_dir():
                continue
            if wanted is not None and repo.name not in wanted:
                continue
            resolved = repo.resolve()
            if resolved in seen_repos:
                continue
            seen_repos.add(resolved)
            agents_dir = resolved / ".agents/skills"
            claude_dir = resolved / ".claude/skills"
            if not agents_dir.is_dir() or not claude_dir.is_dir():
                continue
            for agent_entry in sorted(agents_dir.iterdir()):
                if agent_entry.name.startswith(".") or not (agent_entry / "SKILL.md").exists():
                    continue
                claude_entry = claude_dir / agent_entry.name
                if claude_entry.is_symlink() or not (claude_entry / "SKILL.md").exists():
                    continue
                if hash_skill_dir(agent_entry) != hash_skill_dir(claude_entry):
                    skipped_diverged.append(
                        {
                            "repo": repo.name,
                            "skill": agent_entry.name,
                            "agentsPath": str(agent_entry),
                            "claudePath": str(claude_entry),
                        }
                    )
                    continue
                rel_target = os.path.relpath(agent_entry, claude_entry.parent)
                if not dry_run:
                    _quarantine_item(
                        claude_entry,
                        batch_dir,
                        f"repos/{repo.name}",
                        "repo_dual_copy_dedupe",
                        records,
                        dry_run=False,
                    )
                    claude_entry.symlink_to(rel_target)
                actions.append(
                    {
                        "repo": repo.name,
                        "skill": agent_entry.name,
                        "claudePath": str(claude_entry),
                        "relativeTarget": rel_target,
                    }
                )

    manifest_file: Path | None = None
    if not dry_run and records:
        batch_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = batch_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps({"createdAt": stamp, "records": records}, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "dryRun": dry_run,
        "quarantineBatch": str(batch_dir) if (not dry_run and records) else None,
        "manifestFile": str(manifest_file) if manifest_file else None,
        "dedupedCount": len(actions),
        "skippedDivergedCount": len(skipped_diverged),
        "actions": actions,
        "skippedDiverged": skipped_diverged,
    }
