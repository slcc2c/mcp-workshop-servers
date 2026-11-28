"""Unit tests for MLflow 3.18 Skill Registry publish, web import, absorb, and restore."""

from __future__ import annotations

import shutil
import types
from pathlib import Path
from typing import Any

import pytest

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.skill_registry import (
    _coerce_remote_git_source,
    absorb_skills_dir,
    get_mlflow_skill_detail,
    import_web_skill,
    list_mlflow_skills,
    materialize_mlflow_skill,
    normalize_mlflow_name,
    publish_local_skills_to_mlflow,
    restore_registry_from_lockfile,
)


def _write_skill(root: Path, name: str, body: str = "Skill body.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Desc for {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return d


class _FakePagedList(list):
    def __init__(self, items: list[Any], token: str | None = None) -> None:
        super().__init__(items)
        self.token = token


def _make_fake_mlflow(store: dict[tuple[str, str], dict[str, Any]]):
    """Build an in-memory fake mlflow module supporting pagination, tags, aliases, and pull."""

    class FakeClient:
        def __init__(self, tracking_uri: str = "") -> None:
            self.tracking_uri = tracking_uri

        def search_skill_versions(self, *, name: str, organization: str = "", **_kw: Any):
            rec = store.get((organization, name))
            return list(rec["versions"]) if rec else []

        def get_skill(self, *, name: str, organization: str = ""):
            if (organization, name) not in store:
                raise KeyError((organization, name))
            return types.SimpleNamespace(
                name=name,
                organization=organization,
                description=f"Desc for {organization}/{name}",
                aliases=dict(store[(organization, name)]["aliases"]),
                tags={},
            )

        def get_skill_version(self, *, name: str, version: int, organization: str = ""):
            rec = store[(organization, name)]
            for v in rec["versions"]:
                if v.version == version:
                    return v
            raise KeyError(version)

        def get_skill_version_by_alias(self, *, name: str, alias: str, organization: str = ""):
            rec = store[(organization, name)]
            ver_num = rec["aliases"][alias]
            return self.get_skill_version(name=name, version=ver_num, organization=organization)

        def get_latest_skill_version(self, *, name: str, organization: str = ""):
            return store[(organization, name)]["versions"][-1]

        def set_skill_alias(self, *, name: str, alias: str, version: int, organization: str = ""):
            store[(organization, name)]["aliases"][alias] = version

        def set_skill_version_tag(
            self,
            *,
            name: str,
            version: int,
            key: str,
            value: str,
            organization: str = "",
        ):
            v = self.get_skill_version(name=name, version=version, organization=organization)
            v.tags[key] = value

    def search_skills(*, max_results: int = 100, page_token: str | None = None):
        all_items = [
            types.SimpleNamespace(
                name=name,
                organization=org,
                description=f"Desc for {name}",
                aliases=dict(rec["aliases"]),
                tags={},
            )
            for (org, name), rec in sorted(store.items())
        ]
        start = int(page_token) if page_token else 0
        chunk = all_items[start : start + max_results]
        next_tok = str(start + len(chunk)) if (start + len(chunk)) < len(all_items) else None
        return _FakePagedList(chunk, token=next_tok)

    def get_skill(*, name: str, organization: str = ""):
        if (organization, name) not in store:
            raise KeyError((organization, name))
        return types.SimpleNamespace(
            name=name,
            organization=organization,
            description=f"Desc for {organization}/{name}",
            aliases=dict(store[(organization, name)]["aliases"]),
            tags={},
        )

    def register_skill(
        *,
        source: str,
        name: str | None = None,
        organization: str = "",
        status: str = "active",
    ):
        src_path = Path(source)
        sk_name = normalize_mlflow_name(name or src_path.name)
        rec = store.setdefault(
            (organization, sk_name),
            {"aliases": {}, "versions": []},
        )
        ver_num = len(rec["versions"]) + 1
        ver = types.SimpleNamespace(
            name=sk_name,
            organization=organization,
            version=ver_num,
            status=status,
            aliases=[],
            digest=f"digest-{sk_name}-{ver_num}",
            source=source,
            tags={},
            _src_dir=src_path,
        )
        rec["versions"].append(ver)
        return ver

    def import_skills(
        *,
        source: str,
        organization: str = "",
        skill_names: list[str] | None = None,
        status: str = "active",
    ):
        names = skill_names or ["web-imported-skill"]
        created = []
        for sname in names:
            ver = types.SimpleNamespace(
                name=sname,
                organization=organization,
                version=1,
                status=status,
                aliases=[],
                digest=f"digest-{sname}-1",
                source=source,
                tags={},
                _src_dir=None,
            )
            store[(organization, sname)] = {"aliases": {}, "versions": [ver]}
            created.append(ver)
        return created

    return types.SimpleNamespace(
        set_tracking_uri=lambda _u: None,
        MlflowClient=FakeClient,
        genai=types.SimpleNamespace(
            search_skills=search_skills,
            register_skill=register_skill,
            import_skills=import_skills,
        ),
    )


def _setup_registry_env(tmp_path: Path) -> tuple[MCPStackSettings, Path, Path]:
    home = tmp_path / "home"
    atelier_skills = home / "repos/atelier/templates/agents/skills"
    _write_skill(atelier_skills, "alpha-skill", "alpha body")
    _write_skill(home / "repos/mlflow_sme/skills", "mlflow-tracking", "mlflow body")
    _write_skill(home / "repos/demo_repo/.agents/skills", "repo-helper", "repo body")

    mpath = home / "repos/atelier/templates/agents/skills-manifest.yaml"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(
        """
version: 1
quarantine_root: ~/.local/share/mcp-stack/skill-quarantine
sources:
  atelier-personal:
    path: ~/repos/atelier/templates/agents/skills
    kind: canonical-repo
    owner: personal
    skills: [alpha-skill]
  mlflow-sme:
    path: ~/repos/mlflow_sme/skills
    kind: domain-repo
    owner: mlflow_sme
    include_all: true
  mlflow-web:
    path: ~/.local/share/mcp-stack/registry-skills/web
    kind: mlflow-registry
    owner: web
    include_all: true
targets:
  claude-code:
    dir: ~/.claude/skills
    sources: [atelier-personal, mlflow-sme, mlflow-web]
plugin_owned_skills: [pdf]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    settings = MCPStackSettings.model_validate(
        {
            "mlflow": {"tracking_uri": "http://localhost:5002", "allow_mutations": True},
            "skills": {"manifest_path": str(mpath), "repos_root": str(home / "repos")},
        }
    )
    return settings, home, mpath


def test_list_mlflow_skills_paginates_past_100() -> None:
    store: dict[tuple[str, str], dict[str, Any]] = {}
    for i in range(135):
        name = f"skill-{i:03d}"
        store[("personal", name)] = {
            "aliases": {"production": 1},
            "versions": [
                types.SimpleNamespace(
                    name=name,
                    organization="personal",
                    version=1,
                    status="active",
                    aliases=["production"],
                    digest="abc",
                    source="x",
                    tags={},
                )
            ],
        }
    fake_mlflow = _make_fake_mlflow(store)
    settings = MCPStackSettings()
    res = list_mlflow_skills(settings, max_results=250, mlflow_module=fake_mlflow)
    assert len(res["skills"]) == 135
    assert res["organizations"] == ["personal"]


def test_publish_local_skills_idempotent_and_git_clean_vs_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, home, _ = _setup_registry_env(tmp_path)
    store: dict[tuple[str, str], dict[str, Any]] = {}
    fake_mlflow = _make_fake_mlflow(store)

    # alpha-skill clean -> @production, others dirty -> @draft
    monkeypatch.setattr(
        "mcp_stack.skill_registry._git_skill_state",
        lambda p: (p.name == "alpha-skill", "abc1234", p.parent.name),
    )

    first = publish_local_skills_to_mlflow(
        settings, include_repos=True, dry_run=False, home_dir=home, mlflow_module=fake_mlflow
    )
    assert first["publishedCount"] == 3
    assert first["errorCount"] == 0
    by_name = {item["name"]: item for item in first["published"]}
    assert by_name["alpha-skill"]["alias"] == "production"
    assert by_name["alpha-skill"]["organization"] == "personal"
    assert by_name["mlflow-tracking"]["alias"] == "draft"
    assert by_name["repo-helper"]["organization"] == "repo-demo-repo"

    # Second run must publish zero new versions
    second = publish_local_skills_to_mlflow(
        settings, include_repos=True, dry_run=False, home_dir=home, mlflow_module=fake_mlflow
    )
    assert second["publishedCount"] == 0
    assert second["unchangedCount"] == 3


def test_import_web_materialize_precedence_and_absorb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, home, mpath = _setup_registry_env(tmp_path)
    store: dict[tuple[str, str], dict[str, Any]] = {}
    fake_mlflow = _make_fake_mlflow(store)

    src_bundle = tmp_path / "web_src"
    good = _write_skill(src_bundle, "cool-web-skill", "cool body")
    _write_skill(src_bundle, "alpha-skill", "collides with personal")
    _write_skill(src_bundle, "pdf", "plugin owned")

    def fake_pull(ver: Any, dest: Path) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        src_dir = getattr(ver, "_src_dir", None) or good
        shutil.copytree(src_dir, dest, dirs_exist_ok=True)
        return dest

    monkeypatch.setattr("mlflow.genai.skills.pull_skill_version", fake_pull)

    # Precedence blocks personal skill collision unless --allow-shadow
    with pytest.raises(ValueError, match="personal canonical skill"):
        import_web_skill(
            settings,
            source=str(src_bundle / "alpha-skill"),
            home_dir=home,
            mlflow_module=fake_mlflow,
        )

    mat_root = home / ".local/share/mcp-stack/registry-skills"
    lock_file = mpath.parent / "web-skills-lock.yaml"

    # Absorb skips alpha-skill + pdf, imports cool-web-skill into MLflow + lockfile + harnesses
    ab = absorb_skills_dir(
        settings,
        src_bundle,
        dry_run=False,
        lock_path=lock_file,
        materialize_root=mat_root,
        home_dir=home,
        mlflow_module=fake_mlflow,
    )
    assert ab["absorbedCount"] == 1
    assert ab["skippedCount"] == 2
    assert (mat_root / "web/cool-web-skill/SKILL.md").is_file()
    assert (home / ".claude/skills/cool-web-skill").is_symlink()
    assert lock_file.is_file()

    # Re-materialize & restore into fresh MLflow store succeeds from lockfile + cache
    fresh_store: dict[tuple[str, str], dict[str, Any]] = {}
    fresh_mlflow = _make_fake_mlflow(fresh_store)
    restored = restore_registry_from_lockfile(
        settings,
        dry_run=False,
        lock_path=lock_file,
        materialize_root=mat_root,
        home_dir=home,
        mlflow_module=fresh_mlflow,
    )
    assert restored["webRestoredCount"] == 1
    assert ("web", "cool-web-skill") in fresh_store

    # Direct materialize_mlflow_skill atomic swap check
    mat = materialize_mlflow_skill(
        settings,
        "cool-web-skill",
        organization="web",
        materialize_root=mat_root,
        mlflow_module=fake_mlflow,
    )
    assert Path(mat["path"]).is_dir()


def test_get_mlflow_skill_detail_resolves_org_precedence_and_at_syntax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store: dict[tuple[str, str], dict[str, Any]] = {}
    for org, body in (
        ("repo-printer", "repo copy"),
        ("web", "web copy"),
        ("personal", "personal copy"),
    ):
        d = tmp_path / org / "shared-skill"
        _write_skill(tmp_path / org, "shared-skill", body)
        store[(org, "shared-skill")] = {
            "aliases": {"production": 1},
            "versions": [
                types.SimpleNamespace(
                    name="shared-skill",
                    organization=org,
                    version=1,
                    status="active",
                    aliases=["production"],
                    digest=f"d-{org}",
                    source=str(d),
                    tags={},
                    _src_dir=d,
                )
            ],
        }

    web_only = _write_skill(tmp_path / "only_web", "web-only", "web only md")
    store[("web", "web-only")] = {
        "aliases": {"production": 1},
        "versions": [
            types.SimpleNamespace(
                name="web-only",
                organization="web",
                version=1,
                status="active",
                aliases=["production"],
                digest="d-web",
                source=str(web_only),
                tags={},
                _src_dir=web_only,
            )
        ],
    }

    fake_mlflow = _make_fake_mlflow(store)
    monkeypatch.setattr(
        "mlflow.genai.skills.pull_skill_version",
        lambda ver, dest: (shutil.copytree(ver._src_dir, dest, dirs_exist_ok=True), dest)[1],
    )
    settings = MCPStackSettings()

    # Empty org picks personal > web > repo-*
    resolved = get_mlflow_skill_detail(settings, "shared-skill", mlflow_module=fake_mlflow)
    assert resolved["organization"] == "personal"
    assert resolved["resolvedOrganization"] == "personal"
    assert "personal copy" in (resolved["skillMd"] or "")

    # Empty org finds web-only skill cleanly instead of failing on org=''
    web_res = get_mlflow_skill_detail(settings, "web-only", mlflow_module=fake_mlflow)
    assert web_res["organization"] == "web"
    assert "web only md" in (web_res["skillMd"] or "")

    # @org/name shorthand explicitly targets web over personal
    at_res = get_mlflow_skill_detail(settings, "@web/shared-skill", mlflow_module=fake_mlflow)
    assert at_res["organization"] == "web"
    assert "web copy" in (at_res["skillMd"] or "")


def test_coerce_remote_git_source_handles_bare_and_tree_github_urls() -> None:
    from mlflow.entities.skill_source import GitSource

    bare = _coerce_remote_git_source("https://github.com/anthropics/skills")
    assert isinstance(bare, GitSource)
    assert bare.url == "https://github.com/anthropics/skills.git"
    assert bare.ref is None
    assert bare.subpath is None

    tree = _coerce_remote_git_source("https://github.com/org/repo/tree/main/skills/foo/")
    assert isinstance(tree, GitSource)
    assert tree.url == "https://github.com/org/repo.git"
    assert tree.ref == "main"
    assert tree.subpath == "skills/foo"

    assert (
        _coerce_remote_git_source("https://github.com/org/repo/archive/main.zip")
        == "https://github.com/org/repo/archive/main.zip"
    )
    assert _coerce_remote_git_source("/tmp/local-skill") == "/tmp/local-skill"
