"""Zero-dependency repository secret scanner for local checks and GitHub Actions CI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_classic_pat", re.compile(r"ghp_[A-Za-z0-9_]{20,}")),
    ("github_oauth", re.compile(r"gho_[A-Za-z0-9_]{20,}")),
    ("github_fine_grained_pat", re.compile(r"github_pat_[A-Za-z0-9_]{16,}")),
    ("openai_like_key", re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)

SKIP_FILES = frozenset(
    {
        "scripts/secret_scan.py",
        "tests/unit/test_secret_scan.py",
    }
)


def _is_placeholder(matched: str) -> bool:
    """Ignore obvious documentation/example placeholders such as ghp_xxxx or REPLACE_WITH_*."""
    lower = matched.lower()
    if any(
        marker in lower
        for marker in (
            "replace_with",
            "your_github",
            "your_openai",
            "your_key",
            "placeholder",
            "example",
        )
    ):
        return True
    tail = matched
    for prefix in ("github_pat_", "sk-ant-", "ghp_", "gho_", "sk-"):
        if tail.startswith(prefix):
            tail = tail[len(prefix) :]
            break
    return len(set(tail)) <= 2


def scan_text(text: str, rel_path: str) -> list[tuple[str, int, str]]:
    """Return (path, line_number, rule_name) hits without exposing matched secret text."""
    if rel_path in SKIP_FILES:
        return []
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule_name, pattern in RULES:
            for match in pattern.finditer(line):
                if rule_name != "private_key" and _is_placeholder(match.group(0)):
                    continue
                hits.append((rel_path, lineno, rule_name))
                break
    return hits


def scan_repo(root: Path | None = None) -> list[tuple[str, int, str]]:
    """Scan all git-tracked non-binary files in the repository."""
    repo_root = (root or Path.cwd()).resolve()
    raw_list = subprocess.check_output(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
    )
    rel_paths = [p.decode("utf-8", errors="replace") for p in raw_list.split(b"\x00") if p]

    all_hits: list[tuple[str, int, str]] = []
    for rel in rel_paths:
        if rel in SKIP_FILES:
            continue
        fp = repo_root / rel
        if not fp.is_file():
            continue
        sample = fp.read_bytes()
        if b"\x00" in sample[:4096]:
            continue
        all_hits.extend(scan_text(sample.decode("utf-8", errors="replace"), rel))
    return all_hits


def main() -> int:
    hits = scan_repo()
    if hits:
        for path, lineno, rule in hits:
            print(f"{path}:{lineno}:{rule}", file=sys.stderr)
        print(f"Secret scan failed: {len(hits)} finding(s).", file=sys.stderr)
        return 1

    raw_list = subprocess.check_output(["git", "ls-files", "-z"])
    count = len([p for p in raw_list.split(b"\x00") if p])
    print(f"Secret scan clean ({count} tracked files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
