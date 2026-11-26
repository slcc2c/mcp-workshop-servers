"""Unit tests for 5-layer skill audit, symlink projection, promotion, and quarantine rollback."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_stack.skills import (
    audit_skills,
    load_skills_manifest,
    promote_skill,
    rollback_quarantine,
    sync_skills,
)


def _write_skill(root: Path, name: str, body: str = "Use this skill.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Desc for {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return d


def _setup_fixture_home(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    atelier_skills = home / "repos/atelier/templates/agents/skills"
    _write_skill(atelier_skills, "alpha-skill", "canonical alpha")
    _write_skill(atelier_skills, "agent-coordination", "managed coord")

    mlflow_skills = home / "repos/mlflow_sme/skills"
    _write_skill(mlflow_skills, "mlflow-tracking", "mlflow tracking")

    # Target dirs
    claude_dir = home / ".claude/skills"
    claude_dir.mkdir(parents=True, exist_ok=True)
    # Identical drifted static copy
    _write_skill(claude_dir, "alpha-skill", "canonical alpha")
    # Atelier-managed static copy (must be preserved!)
    _write_skill(claude_dir, "agent-coordination", "managed coord")
    # Synced bucket that must never be touched by sync
    _write_skill(home / ".claude/skills/synced/bucket-1", "grilling", "synced grilling")

    codex_dir = home / ".codex/skills"
    codex_dir.mkdir(parents=True, exist_ok=True)
    # Unmanaged plugin-owned duplicate
    _write_skill(codex_dir, "grilling", "user copy grilling")
    # Codex .system skill (must be ignored)
    _write_skill(codex_dir / ".system", "skill-creator", "system skill")

    # Legacy root
    _write_skill(home / ".agents/skills", "tdd", "legacy tdd")
    _write_skill(home / ".agents/skills", "learned", "keep learned?")
    (home / ".agents/skills/learned/SKILL.md").unlink()

    # Repo-local dual copy & grill-me collision
    _write_skill(home / "repos/sample_repo/.agents/skills", "grill-me", "repo grill-me")
    _write_skill(home / "repos/sample_repo/.claude/skills", "grill-me", "repo grill-me")

    manifest_path = home / "repos/atelier/templates/agents/skills-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        """
version: 1
quarantine_root: ~/.local/share/mcp-stack/skill-quarantine
sources:
  atelier-personal:
    path: ~/repos/atelier/templates/agents/skills
    kind: canonical-repo
    owner: personal
    atelier_managed: [agent-coordination]
    skills: [alpha-skill]
  mlflow-sme:
    path: ~/repos/mlflow_sme/skills
    kind: domain-repo
    owner: mlflow_sme
    include_all: true
targets:
  claude-code:
    dir: ~/.claude/skills
    sources: [atelier-personal, mlflow-sme]
    ignore_names: [synced]
  codex:
    dir: ~/.codex/skills
    sources: [atelier-personal, mlflow-sme]
    ignore_names: [.system]
legacy_cleanup_roots:
  - path: ~/.agents/skills
    reason: "Bucket 3 backlog"
    ignore_names: [learned]
plugin_owned_skills: [grilling, grill-me]
alias_groups:
  - id: grilling
    names: [grilling, grill-me]
    canonical_owner: plugin/builtin
    recommendation: "Keep one grilling layer."
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return home, manifest_path


def test_audit_skills_detects_five_layers_and_collisions(tmp_path: Path) -> None:
    home, mpath = _setup_fixture_home(tmp_path)
    manifest = load_skills_manifest(mpath)

    report = audit_skills(manifest, home_dir=home, repos_root=home / "repos")
    assert report["available"] is True
    assert report["summary"]["canonicalSkills"] == 3
    assert report["targets"]["claude-code"]["counts"]["drifted_copy"] == 1
    assert report["targets"]["claude-code"]["counts"]["atelier_managed"] == 1
    assert report["targets"]["claude-code"]["counts"]["missing"] == 1
    assert "grilling" in report["targets"]["codex"]["extraUnmanaged"]
    assert any(c["group"] == "grilling" for c in report["collisions"])
    assert any(item["skill"] == "tdd" for item in report["legacyItems"])
    assert len(report["repoDualCopies"]) == 1


def test_sync_skills_quarantines_and_rollback_restores(tmp_path: Path) -> None:
    home, mpath = _setup_fixture_home(tmp_path)
    manifest = load_skills_manifest(mpath)

    dry = sync_skills(manifest, dry_run=True, quarantine_legacy=True, home_dir=home)
    assert dry["dryRun"] is True
    assert dry["quarantinedCount"] >= 3
    assert not (home / ".claude/skills/alpha-skill").is_symlink()

    applied = sync_skills(manifest, dry_run=False, quarantine_legacy=True, home_dir=home)
    assert applied["dryRun"] is False
    batch = Path(applied["quarantineBatch"])
    assert (batch / "manifest.json").exists()

    # Symlinks created & atelier_managed preserved as non-symlink
    assert (home / ".claude/skills/alpha-skill").is_symlink()
    assert (home / ".claude/skills/mlflow-tracking").is_symlink()
    assert not (home / ".claude/skills/agent-coordination").is_symlink()
    # Ignored entries preserved
    assert (home / ".claude/skills/synced/bucket-1/grilling/SKILL.md").exists()
    assert (home / ".codex/skills/.system/skill-creator/SKILL.md").exists()
    # Unmanaged grilling & legacy tdd moved to quarantine
    assert not (home / ".codex/skills/grilling").exists()
    assert not (home / ".agents/skills/tdd").exists()

    post_audit = audit_skills(manifest, home_dir=home, repos_root=home / "repos")
    assert post_audit["summary"]["driftIssues"] == 0
    assert post_audit["summary"]["legacyItems"] == 0

    # Clean targets before testing rollback of quarantined grilling & tdd
    rb = rollback_quarantine(batch, dry_run=False)
    manifest_recs = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))["records"]
    assert rb["restoredCount"] + rb["skippedCount"] == len(manifest_recs)
    assert (home / ".codex/skills/grilling/SKILL.md").exists()
    assert (home / ".agents/skills/tdd/SKILL.md").exists()


def test_promote_skill_copies_into_canonical_and_updates_manifest(tmp_path: Path) -> None:
    home, mpath = _setup_fixture_home(tmp_path)
    res = promote_skill(mpath, "tdd", dry_run=False, home_dir=home)
    assert res["skill"] == "tdd"
    assert (home / "repos/atelier/templates/agents/skills/tdd/SKILL.md").exists()
    assert (home / ".claude/skills/tdd").is_symlink()
    assert (home / ".codex/skills/tdd").is_symlink()
    updated = load_skills_manifest(mpath)
    assert "tdd" in updated.sources["atelier-personal"].skills


def test_disabled_plugins_filtered_and_repo_dual_skills_deduped(tmp_path: Path) -> None:
    from mcp_stack.skills import dedupe_repo_dual_skills

    home, mpath = _setup_fixture_home(tmp_path)

    # Disabled Claude & Codex plugins must NOT generate collisions
    claude_plug_dir = home / ".claude/plugins/cache/mattpocock/1.0/skills/grill-me"
    _write_skill(claude_plug_dir.parent, "grill-me", "disabled plugin grill-me")
    (home / ".claude/plugins/installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "mattpocock-skills@claude-plugins-official": [
                        {"installPath": str(claude_plug_dir.parents[1])}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (home / ".claude/settings.json").write_text(
        json.dumps({"enabledPlugins": {"mattpocock-skills@claude-plugins-official": False}}),
        encoding="utf-8",
    )

    codex_plug_dir = home / ".codex/plugins/cache/claude-cowork/mlflow/skills/mlflow-agent"
    _write_skill(codex_plug_dir.parent, "mlflow-agent", "disabled codex mlflow")
    (home / ".codex/config.toml").write_text(
        '[plugins."mlflow@claude-cowork"]\nenabled = false\n',
        encoding="utf-8",
    )

    manifest = load_skills_manifest(mpath)
    report = audit_skills(manifest, home_dir=home, repos_root=home / "repos")
    plugin_origins = {p["origin"] for p in report["pluginSkills"]}
    assert "mattpocock-skills@claude-plugins-official" not in plugin_origins
    assert "claude-cowork/mlflow" not in plugin_origins

    # Diverged repo dual copy is skipped; identical repo dual copy becomes relative symlink
    _write_skill(home / "repos/sample_repo/.agents/skills", "diverged-skill", "one")
    _write_skill(home / "repos/sample_repo/.claude/skills", "diverged-skill", "two")

    dedupe = dedupe_repo_dual_skills(
        home / "repos",
        repo_names=["sample_repo"],
        quarantine_root=home / ".local/share/mcp-stack/skill-quarantine",
        dry_run=False,
        home_dir=home,
    )
    assert dedupe["dedupedCount"] == 1
    assert dedupe["skippedDivergedCount"] == 1
    link = home / "repos/sample_repo/.claude/skills/grill-me"
    assert link.is_symlink()
    assert str(link.readlink()) == "../../.agents/skills/grill-me"
    assert Path(dedupe["manifestFile"]).exists()
