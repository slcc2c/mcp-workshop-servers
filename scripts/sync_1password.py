#!/usr/bin/env python3
"""Idempotent two-way sync between local .env MCP tokens and a 1Password Login item.

Works directly from Fish, zsh, or bash using Python's standard library only.
Never passes secret values on CLI arguments and never prints token values.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

DEFAULT_ENV_FILE = Path("/Users/spencer/repos/mcp-server/.env")
DEFAULT_TITLE = "MCP Workshop Gateway"
DEFAULT_URL = "https://mcp.slcc2c.com"
PRIMARY_TOKEN_KEY = "MCP_CODEX_AUTH_TOKEN"
EXTRA_TOKEN_KEYS = (
    "MCP_CLAUDE_AUTH_TOKEN",
    "MCP_CURSOR_AUTH_TOKEN",
    "MCP_OPENAI_AUTH_TOKEN",
    "MCP_DEFAULT_AUTH_TOKEN",
)
ALL_TOKEN_KEYS = (PRIMARY_TOKEN_KEY, *EXTRA_TOKEN_KEYS)
VAULT_PRIORITY = ("Server-Configurations", "Private", "Personal")
CLIENT_TOKENS_SECTION_ID = "client_tokens"
CLIENT_TOKENS_SECTION_LABEL = "Client Tokens"
ITEM_NOTES = (
    "MCP Workshop Gateway (Mac Studio :8090 -> https://mcp.slcc2c.com/ui). "
    "Password field holds MCP_CODEX_AUTH_TOKEN for autofill; run `mcp-stack ui open` "
    "on Mac Studio for a 30-day HttpOnly cookie session."
)

RunFn = Callable[..., subprocess.CompletedProcess[str]]


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from an env file, ignoring blanks and comments."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            result[key] = val
    return result


def render_updated_env(existing_text: str, updates: dict[str, str]) -> str:
    """Update matching KEY=VALUE entries in-place while preserving comments and other keys."""
    remaining = dict(updates)
    out_lines: list[str] = []

    for line in existing_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(line)
            continue
        prefix = ""
        body = line
        if line.lstrip().startswith("export "):
            idx = line.index("export ") + len("export ")
            prefix = line[:idx]
            body = line[idx:]
        key = body.split("=", 1)[0].strip()
        if key in remaining:
            out_lines.append(f"{prefix}{key}={remaining.pop(key)}")
        else:
            out_lines.append(line)

    if remaining:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        for key, val in remaining.items():
            out_lines.append(f"{key}={val}")

    return "\n".join(out_lines) + "\n" if out_lines else ""


def build_create_item_payload(tokens: dict[str, str], title: str, url: str) -> dict[str, Any]:
    """Build a 1Password LOGIN item JSON payload conforming to `op item template get login`."""
    fields: list[dict[str, Any]] = [
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
            "value": tokens[PRIMARY_TOKEN_KEY],
        },
        {
            "id": "notesPlain",
            "type": "STRING",
            "purpose": "NOTES",
            "label": "notesPlain",
            "value": ITEM_NOTES,
        },
    ]
    for key in EXTRA_TOKEN_KEYS:
        if val := tokens.get(key, ""):
            fields.append(
                {
                    "type": "CONCEALED",
                    "label": key,
                    "value": val,
                    "section": {
                        "id": CLIENT_TOKENS_SECTION_ID,
                        "label": CLIENT_TOKENS_SECTION_LABEL,
                    },
                }
            )
    return {
        "title": title,
        "category": "LOGIN",
        "urls": [{"primary": True, "href": url}],
        "sections": [{"id": CLIENT_TOKENS_SECTION_ID, "label": CLIENT_TOKENS_SECTION_LABEL}],
        "fields": fields,
    }


def extract_item_tokens(item: dict[str, Any]) -> tuple[dict[str, str], str]:
    """Return `(token_map, primary_url)` from a 1Password item JSON document."""
    tokens: dict[str, str] = {}
    extra_set = set(EXTRA_TOKEN_KEYS)
    for field in item.get("fields") or []:
        label = str(field.get("label") or "")
        purpose = str(field.get("purpose") or "")
        val = str(field.get("value") or "")
        if not val:
            continue
        if purpose == "PASSWORD" or label == "password":
            tokens[PRIMARY_TOKEN_KEY] = val
        elif label in extra_set:
            tokens[label] = val

    primary_url = ""
    for u in item.get("urls") or []:
        href = str(u.get("href") or "")
        if not href:
            continue
        if u.get("primary") or not primary_url:
            primary_url = href
    return tokens, primary_url


def merge_item_payload(
    existing_item: dict[str, Any], tokens: dict[str, str], url: str
) -> dict[str, Any]:
    """Merge local tokens and URL into a deep copy of an existing 1Password item JSON."""
    merged = copy.deepcopy(existing_item)
    fields: list[dict[str, Any]] = list(merged.get("fields") or [])
    sections: list[dict[str, Any]] = list(merged.get("sections") or [])

    section_ref = {"id": CLIENT_TOKENS_SECTION_ID, "label": CLIENT_TOKENS_SECTION_LABEL}
    for sec in sections:
        if (
            sec.get("id") == CLIENT_TOKENS_SECTION_ID
            or sec.get("label") == CLIENT_TOKENS_SECTION_LABEL
        ):
            section_ref = {
                "id": sec.get("id", CLIENT_TOKENS_SECTION_ID),
                "label": sec.get("label", CLIENT_TOKENS_SECTION_LABEL),
            }
            break
    else:
        sections.append(dict(section_ref))

    # Update password & username
    saw_pw = False
    saw_user = False
    saw_extra: set[str] = set()
    for field in fields:
        purpose = str(field.get("purpose") or "")
        label = str(field.get("label") or "")
        if purpose == "PASSWORD" or label == "password":
            if PRIMARY_TOKEN_KEY in tokens:
                field["value"] = tokens[PRIMARY_TOKEN_KEY]
            saw_pw = True
        elif purpose == "USERNAME" or label == "username":
            if not field.get("value"):
                field["value"] = "codex"
            saw_user = True
        elif label in EXTRA_TOKEN_KEYS:
            saw_extra.add(label)
            if label in tokens:
                field["value"] = tokens[label]

    if not saw_user:
        fields.append(
            {
                "id": "username",
                "type": "STRING",
                "purpose": "USERNAME",
                "label": "username",
                "value": "codex",
            }
        )
    if not saw_pw and PRIMARY_TOKEN_KEY in tokens:
        fields.append(
            {
                "id": "password",
                "type": "CONCEALED",
                "purpose": "PASSWORD",
                "label": "password",
                "value": tokens[PRIMARY_TOKEN_KEY],
            }
        )
    for key in EXTRA_TOKEN_KEYS:
        if key not in saw_extra and tokens.get(key):
            fields.append(
                {
                    "type": "CONCEALED",
                    "label": key,
                    "value": tokens[key],
                    "section": dict(section_ref),
                }
            )

    urls: list[dict[str, Any]] = list(merged.get("urls") or [])
    norm_target = url.rstrip("/")
    if not any(str(u.get("href") or "").rstrip("/") == norm_target for u in urls):
        urls.append({"primary": len(urls) == 0, "href": url})

    merged["sections"] = sections
    merged["fields"] = fields
    merged["urls"] = urls
    return merged


def diff_token_maps(source: dict[str, str], target: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return `(missing_in_target, differing_values)` as lists of key names only."""
    missing: list[str] = []
    differing: list[str] = []
    for key, src_val in source.items():
        if not src_val:
            continue
        if key not in target or not target[key]:
            missing.append(key)
        elif target[key] != src_val:
            differing.append(key)
    return missing, differing


def _run_op(args: Sequence[str], *, run_fn: RunFn, stdin_text: str | None = None) -> Any:
    res = run_fn(["op", *args], input=stdin_text, text=True, capture_output=True)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or f"op exited {res.returncode}").strip()
        raise RuntimeError(err)
    return json.loads(res.stdout)


def resolve_vault(explicit_vault: str | None, *, run_fn: RunFn) -> str:
    """Resolve the target vault name via explicit override or vault priority list."""
    if explicit_vault:
        return explicit_vault
    vaults = _run_op(["vault", "list", "--format", "json"], run_fn=run_fn)
    names = [str(v.get("name") or "") for v in vaults if v.get("name")]
    if not names:
        raise RuntimeError("No 1Password vaults returned by `op vault list`")
    for preferred in VAULT_PRIORITY:
        if preferred in names:
            return preferred
    return names[0]


def find_item_in_vault(vault: str, title: str, *, run_fn: RunFn) -> dict[str, Any] | None:
    """Find an existing item in `vault` matching `title` case-insensitively."""
    items = _run_op(["item", "list", "--vault", vault, "--format", "json"], run_fn=run_fn)
    target = title.strip().lower()
    for it in items:
        if str(it.get("title") or "").strip().lower() == target:
            return it
    return None


def write_env_atomic(env_path: Path, content: str) -> None:
    """Atomically write env file content with 0o600 permissions."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".env.tmp.", dir=str(env_path.parent))
    try:
        os.chmod(tmp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, env_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def push_tokens(args: argparse.Namespace, *, run_fn: RunFn = subprocess.run) -> int:
    """Push MCP gateway tokens from `.env` into 1Password."""
    env_all = parse_env_file(args.env_file)
    tokens = {k: env_all[k] for k in ALL_TOKEN_KEYS if env_all.get(k)}
    if not tokens.get(PRIMARY_TOKEN_KEY):
        print(f"Missing required {PRIMARY_TOKEN_KEY} in {args.env_file}", file=sys.stderr)
        return 1

    vault = resolve_vault(args.vault, run_fn=run_fn)
    existing_summary = find_item_in_vault(vault, args.title, run_fn=run_fn)

    if existing_summary is None:
        payload = build_create_item_payload(tokens, args.title, args.url)
        field_labels = [
            PRIMARY_TOKEN_KEY if f.get("label") == "password" else f["label"]
            for f in payload["fields"]
            if f.get("type") == "CONCEALED"
        ]
        if args.dry_run:
            print(
                f"[dry-run] Would create '{args.title}' (url={args.url}) in vault "
                f"'{vault}' with fields: {field_labels}"
            )
            return 0
        created = _run_op(
            ["item", "create", "--vault", vault, "--format", "json", "-"],
            run_fn=run_fn,
            stdin_text=json.dumps(payload),
        )
        print(
            f"Created 1Password item {created.get('id')} '{created.get('title')}' "
            f"in vault '{vault}' with fields: {field_labels}"
        )
        return 0

    existing_full = _run_op(
        ["item", "get", str(existing_summary["id"]), "--vault", vault, "--format", "json"],
        run_fn=run_fn,
    )
    op_tokens, _op_url = extract_item_tokens(existing_full)
    missing, differing = diff_token_maps(tokens, op_tokens)
    target_url = args.url.rstrip("/")
    url_matches = any(
        str(u.get("href") or "").rstrip("/") == target_url
        for u in (existing_full.get("urls") or [])
    )

    if not missing and not differing and url_matches:
        print(
            f"Already in sync: '{args.title}' ({existing_summary['id']}) "
            f"in vault '{vault}' matches {len(tokens)} token(s)."
        )
        return 0

    if differing and not args.update:
        print(
            f"Refusing to overwrite differing token(s) in '{args.title}' "
            f"({existing_summary['id']}): {differing}. "
            "Re-run with --update to overwrite.",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        updated_keys = differing if args.update else []
        print(
            f"[dry-run] Would update '{args.title}' ({existing_summary['id']}) in vault "
            f"'{vault}': missing={missing}, updated={updated_keys}, "
            f"add_url={not url_matches}"
        )
        return 0

    merged = merge_item_payload(existing_full, tokens, args.url)
    # `op item edit` reads piped JSON stdin WITHOUT `-`
    edited = _run_op(
        ["item", "edit", str(existing_summary["id"]), "--vault", vault, "--format", "json"],
        run_fn=run_fn,
        stdin_text=json.dumps(merged),
    )
    item_id = edited.get("id", existing_summary["id"])
    print(
        f"Updated 1Password item {item_id} '{args.title}' in vault '{vault}': "
        f"added={missing}, overwritten={differing}"
    )
    return 0


def pull_tokens(args: argparse.Namespace, *, run_fn: RunFn = subprocess.run) -> int:
    """Pull MCP gateway tokens from 1Password into local `.env`."""
    vault = resolve_vault(args.vault, run_fn=run_fn)
    existing_summary = find_item_in_vault(vault, args.title, run_fn=run_fn)
    if existing_summary is None:
        print(f"Item '{args.title}' not found in vault '{vault}'", file=sys.stderr)
        return 1

    item = _run_op(
        ["item", "get", str(existing_summary["id"]), "--vault", vault, "--format", "json"],
        run_fn=run_fn,
    )
    op_tokens, _ = extract_item_tokens(item)
    if not op_tokens:
        print(
            f"No MCP tokens found on 1Password item '{args.title}' ({existing_summary['id']})",
            file=sys.stderr,
        )
        return 1

    local_all = parse_env_file(args.env_file)
    local_tokens = {k: local_all[k] for k in ALL_TOKEN_KEYS if k in local_all}
    missing, differing = diff_token_maps(op_tokens, local_tokens)

    if not missing and not differing:
        print(
            f"Already in sync: {args.env_file} matches 1Password item '{args.title}' "
            f"({len(op_tokens)} token(s))."
        )
        return 0

    if differing and not args.update:
        print(
            f"Refusing to overwrite differing token(s) in {args.env_file}: {differing}. "
            "Re-run with --update to overwrite.",
            file=sys.stderr,
        )
        return 2

    to_write = {
        k: v
        for k, v in op_tokens.items()
        if k in missing or (args.update and k in differing)
    }
    if args.dry_run:
        print(
            f"[dry-run] Would write keys {sorted(to_write)} "
            f"to {args.env_file} from vault '{vault}'"
        )
        return 0

    existing_text = args.env_file.read_text(encoding="utf-8") if args.env_file.exists() else ""
    new_text = render_updated_env(existing_text, to_write)
    write_env_atomic(args.env_file, new_text)
    print(
        f"Updated {args.env_file} from 1Password '{args.title}' "
        f"(vault '{vault}'): keys={sorted(to_write)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Two-way secret-safe sync for MCP Workshop Gateway tokens with 1Password."
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--push", action="store_true", help="Sync local .env -> 1Password (default)")
    mode.add_argument("--pull", action="store_true", help="Restore local .env <- 1Password")
    p.add_argument(
        "--vault",
        default=None,
        help="1Password vault name (defaults to Server-Configurations, then Private)",
    )
    p.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help=f"1Password item title (default: {DEFAULT_TITLE!r})",
    )
    p.add_argument("--url", default=DEFAULT_URL, help=f"Login URL (default: {DEFAULT_URL!r})")
    p.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Local .env file (default: {DEFAULT_ENV_FILE})",
    )
    p.add_argument(
        "--update",
        action="store_true",
        help="Overwrite differing token values when drifting",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying 1Password or .env",
    )
    return p


def main(argv: Sequence[str] | None = None, *, run_fn: RunFn = subprocess.run) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.pull:
            return pull_tokens(args, run_fn=run_fn)
        return push_tokens(args, run_fn=run_fn)
    except RuntimeError as exc:
        print(f"1Password sync error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
