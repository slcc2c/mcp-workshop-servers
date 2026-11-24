"""Unit tests for the repository CI secret scanner."""

from __future__ import annotations

from scripts.secret_scan import scan_repo, scan_text


def test_secret_scan_flags_synthetic_leaks_and_skips_short_fixtures() -> None:
    pat = "ghp_" + ("A1b2C3d4" * 5)
    fg = "github_pat_" + ("Z9y8X7w6" * 3)
    pk = "-----BEGIN PRIVATE KEY-----"

    hits = scan_text(f"token={pat}\npat={fg}\n{pk}\n", "sample.env")
    assert ("sample.env", 1, "github_classic_pat") in hits
    assert ("sample.env", 2, "github_fine_grained_pat") in hits
    assert ("sample.env", 3, "private_key") in hits

    short_fixture = "ghp_" + "super_secret"
    assert scan_text(f"auth={short_fixture}", "tests/unit/test_fixture.py") == []

    placeholder_doc = (
        "GITHUB_TOKEN=ghp_your_github_token_here\n"
        'OPENAI="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n'
        'EX="ghp_REPLACE_WITH_YOUR_GITHUB_TOKEN"\n'
    )
    assert scan_text(placeholder_doc, "docs/example.env") == []


def test_secret_scan_clean_on_tracked_repository() -> None:
    assert scan_repo() == []
