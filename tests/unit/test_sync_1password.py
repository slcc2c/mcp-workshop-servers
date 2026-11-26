"""Unit tests for scripts/sync_1password.py."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sync_1password.py"
_SPEC = importlib.util.spec_from_file_location("sync_1password", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
sync_1p = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync_1p)

SECRET_CODEX = "tok_secret_codex_12345"
SECRET_CLAUDE = "tok_secret_claude_67890"
SECRET_CURSOR = "tok_secret_cursor_abcde"


def _write_env(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_parse_and_render_env_preserves_comments_and_other_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    original = (
        "# Gateway config\n"
        "OTHER_VAR=keep_me\n"
        f'MCP_CODEX_AUTH_TOKEN="{SECRET_CODEX}"\n'
        "export UNRELATED_URL=http://127.0.0.1:5002\n"
    )
    _write_env(env_path, original)

    parsed = sync_1p.parse_env_file(env_path)
    assert parsed["MCP_CODEX_AUTH_TOKEN"] == SECRET_CODEX
    assert parsed["UNRELATED_URL"] == "http://127.0.0.1:5002"

    updated = sync_1p.render_updated_env(
        original,
        {"MCP_CODEX_AUTH_TOKEN": "new_codex", "MCP_CLAUDE_AUTH_TOKEN": SECRET_CLAUDE},
    )
    assert "# Gateway config" in updated
    assert "OTHER_VAR=keep_me" in updated
    assert "export UNRELATED_URL=http://127.0.0.1:5002" in updated
    assert "MCP_CODEX_AUTH_TOKEN=new_codex" in updated
    assert f"MCP_CLAUDE_AUTH_TOKEN={SECRET_CLAUDE}" in updated


def test_push_creates_item_via_stdin_without_leaking_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / ".env"
    _write_env(
        env_path,
        f"MCP_CODEX_AUTH_TOKEN={SECRET_CODEX}\nMCP_CLAUDE_AUTH_TOKEN={SECRET_CLAUDE}\n",
    )

    calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd, *, input=None, **_kwargs):
        calls.append((list(cmd), input))
        if cmd[:3] == ["op", "vault", "list"]:
            vaults = [
                {"id": "v1", "name": "Private"},
                {"id": "v2", "name": "Server-Configurations"},
            ]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(vaults), "")
        if cmd[:3] == ["op", "item", "list"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps([]), "")
        if cmd[:3] == ["op", "item", "create"]:
            created = {"id": "item123", "title": "MCP Workshop Gateway"}
            return subprocess.CompletedProcess(cmd, 0, json.dumps(created), "")
        raise AssertionError(f"unexpected cmd: {cmd}")

    rc = sync_1p.main(["--env-file", str(env_path)], run_fn=fake_run)
    assert rc == 0

    captured = capsys.readouterr()
    assert SECRET_CODEX not in captured.out + captured.err
    assert SECRET_CLAUDE not in captured.out + captured.err
    assert "Server-Configurations" in captured.out

    create_cmd, create_stdin = calls[-1]
    assert create_cmd[-1] == "-"
    assert all(SECRET_CODEX not in arg and SECRET_CLAUDE not in arg for arg in create_cmd)
    payload = json.loads(create_stdin or "{}")
    assert payload["urls"][0]["href"] == "https://mcp.slcc2c.com"
    fields = {f["label"]: f for f in payload["fields"]}
    assert fields["password"]["value"] == SECRET_CODEX
    assert fields["MCP_CLAUDE_AUTH_TOKEN"]["value"] == SECRET_CLAUDE
    assert fields["MCP_CLAUDE_AUTH_TOKEN"]["type"] == "CONCEALED"


def test_push_dry_run_makes_no_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / ".env"
    _write_env(env_path, f"MCP_CODEX_AUTH_TOKEN={SECRET_CODEX}\n")
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["op", "vault", "list"]:
            vaults = [{"id": "v1", "name": "Server-Configurations"}]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(vaults), "")
        if cmd[:3] == ["op", "item", "list"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps([]), "")
        raise AssertionError(f"unexpected mutating cmd in dry-run: {cmd}")

    rc = sync_1p.main(["--env-file", str(env_path), "--dry-run"], run_fn=fake_run)
    assert rc == 0
    assert len(calls) == 2
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert SECRET_CODEX not in out


def test_push_existing_in_sync_and_drift_guard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / ".env"
    _write_env(
        env_path,
        f"MCP_CODEX_AUTH_TOKEN={SECRET_CODEX}\nMCP_CLAUDE_AUTH_TOKEN={SECRET_CLAUDE}\n",
    )

    existing_item = {
        "id": "item-abc",
        "title": "MCP Workshop Gateway",
        "urls": [{"primary": True, "href": "https://mcp.slcc2c.com"}],
        "sections": [{"id": "sec1", "label": "Client Tokens"}],
        "fields": [
            {
                "id": "username",
                "type": "STRING",
                "purpose": "USERNAME",
                "label": "username",
                "value": "codex",
            },
            {
                "id": "password",
                "type": "CONCEALED",
                "purpose": "PASSWORD",
                "label": "password",
                "value": SECRET_CODEX,
            },
            {
                "id": "f1",
                "type": "CONCEALED",
                "label": "MCP_CLAUDE_AUTH_TOKEN",
                "value": SECRET_CLAUDE,
                "section": {"id": "sec1"},
            },
        ],
    }

    def fake_run_sync(cmd, **_kwargs):
        if cmd[:3] == ["op", "item", "list"]:
            listed = [{"id": "item-abc", "title": "MCP Workshop Gateway"}]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(listed), "")
        if cmd[:3] == ["op", "item", "get"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(existing_item), "")
        raise AssertionError(f"unexpected cmd: {cmd}")

    rc = sync_1p.main(
        ["--vault", "Server-Configurations", "--env-file", str(env_path)],
        run_fn=fake_run_sync,
    )
    assert rc == 0
    assert "Already in sync" in capsys.readouterr().out

    # Now drift local codex token -> refuse without --update, succeed with --update
    _write_env(
        env_path,
        f"MCP_CODEX_AUTH_TOKEN={SECRET_CURSOR}\nMCP_CLAUDE_AUTH_TOKEN={SECRET_CLAUDE}\n",
    )
    rc_refuse = sync_1p.main(
        ["--vault", "Server-Configurations", "--env-file", str(env_path)],
        run_fn=fake_run_sync,
    )
    assert rc_refuse == 2
    err = capsys.readouterr().err
    assert "MCP_CODEX_AUTH_TOKEN" in err
    assert SECRET_CURSOR not in err and SECRET_CODEX not in err

    edit_calls: list[tuple[list[str], str | None]] = []

    def fake_run_edit(cmd, *, input=None, **_kwargs):
        if cmd[:3] == ["op", "item", "edit"]:
            edit_calls.append((list(cmd), input))
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"id": "item-abc"}), "")
        return fake_run_sync(cmd)

    rc_upd = sync_1p.main(
        ["--vault", "Server-Configurations", "--env-file", str(env_path), "--update"],
        run_fn=fake_run_edit,
    )
    assert rc_upd == 0
    assert len(edit_calls) == 1
    edit_cmd, edit_stdin = edit_calls[0]
    assert "-" not in edit_cmd  # op item edit rejects trailing '-'
    merged = json.loads(edit_stdin or "{}")
    pw = next(f["value"] for f in merged["fields"] if f.get("purpose") == "PASSWORD")
    assert pw == SECRET_CURSOR


def test_pull_writes_secure_env_and_guards_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / ".env"
    item = {
        "id": "item-pull",
        "title": "MCP Workshop Gateway",
        "urls": [{"primary": True, "href": "https://mcp.slcc2c.com"}],
        "fields": [
            {"id": "password", "purpose": "PASSWORD", "label": "password", "value": SECRET_CODEX},
            {"label": "MCP_CLAUDE_AUTH_TOKEN", "value": SECRET_CLAUDE},
        ],
    }

    def fake_run(cmd, **_kwargs):
        if cmd[:3] == ["op", "item", "list"]:
            listed = [{"id": "item-pull", "title": "MCP Workshop Gateway"}]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(listed), "")
        if cmd[:3] == ["op", "item", "get"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(item), "")
        raise AssertionError(f"unexpected cmd: {cmd}")

    rc = sync_1p.main(
        ["--pull", "--vault", "Server-Configurations", "--env-file", str(env_path)],
        run_fn=fake_run,
    )
    assert rc == 0
    mode = stat.S_IMODE(os.stat(env_path).st_mode)
    assert mode == 0o600
    parsed = sync_1p.parse_env_file(env_path)
    assert parsed["MCP_CODEX_AUTH_TOKEN"] == SECRET_CODEX
    assert parsed["MCP_CLAUDE_AUTH_TOKEN"] == SECRET_CLAUDE
    out = capsys.readouterr().out
    assert SECRET_CODEX not in out and SECRET_CLAUDE not in out

    # Modify .env locally -> pull without --update refuses (rc 2); with --update overwrites
    _write_env(env_path, "OTHER=preserve\nMCP_CODEX_AUTH_TOKEN=local_override\n")
    rc_refuse = sync_1p.main(
        ["--pull", "--vault", "Server-Configurations", "--env-file", str(env_path)],
        run_fn=fake_run,
    )
    assert rc_refuse == 2

    rc_upd = sync_1p.main(
        ["--pull", "--vault", "Server-Configurations", "--env-file", str(env_path), "--update"],
        run_fn=fake_run,
    )
    assert rc_upd == 0
    final_parsed = sync_1p.parse_env_file(env_path)
    assert final_parsed["OTHER"] == "preserve"
    assert final_parsed["MCP_CODEX_AUTH_TOKEN"] == SECRET_CODEX
    assert final_parsed["MCP_CLAUDE_AUTH_TOKEN"] == SECRET_CLAUDE
