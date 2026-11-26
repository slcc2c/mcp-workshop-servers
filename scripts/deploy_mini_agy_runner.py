#!/usr/bin/env python3
"""Idempotently deploy scripts/mini_agy_runner.py and its tests to spencers-mac-mini."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SRC = REPO_ROOT / "scripts" / "mini_agy_runner.py"
TEST_SRC = REPO_ROOT / "tests" / "unit" / "test_mini_agy_runner.py"
REMOTE_DIR_REL = ".local/share/mini-agy/src"
REMOTE_BIN_REL = ".local/bin/mini-agy-runner"


def deploy_mini_agy_runner(
    *,
    host: str = "spencers-mac-mini",
    dry_run: bool = False,
    verify: bool = False,
    ssh_bin: str = "ssh",
    scp_bin: str = "scp",
) -> dict[str, object]:
    """Copy mini_agy_runner.py + unit tests to the Mac mini and optionally verify."""
    if not RUNNER_SRC.is_file():
        raise FileNotFoundError(f"Missing runner source: {RUNNER_SRC}")
    if not TEST_SRC.is_file():
        raise FileNotFoundError(f"Missing runner tests: {TEST_SRC}")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prep_cmd = (
        f"mkdir -p ~/{REMOTE_DIR_REL} ~/.local/bin && "
        f"if [ -f ~/{REMOTE_DIR_REL}/mini_agy_runner.py ]; then "
        f"cp ~/{REMOTE_DIR_REL}/mini_agy_runner.py "
        f"~/{REMOTE_DIR_REL}/mini_agy_runner.py.bak-{stamp}; fi"
    )
    finalize_cmd = (
        f"chmod +x ~/{REMOTE_DIR_REL}/mini_agy_runner.py && "
        f"ln -sfn \"$HOME/{REMOTE_DIR_REL}/mini_agy_runner.py\" \"$HOME/{REMOTE_BIN_REL}\""
    )

    plan = {
        "host": host,
        "dry_run": dry_run,
        "verify": verify,
        "runner_src": str(RUNNER_SRC),
        "test_src": str(TEST_SRC),
        "remote_dir": f"~/{REMOTE_DIR_REL}",
        "remote_symlink": f"~/{REMOTE_BIN_REL}",
        "backup_suffix": f".bak-{stamp}",
    }
    if dry_run:
        return {"ok": True, **plan}

    def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, capture_output=True, text=True, check=True)

    _run([ssh_bin, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, prep_cmd])
    _run([scp_bin, "-q", str(RUNNER_SRC), f"{host}:{REMOTE_DIR_REL}/mini_agy_runner.py"])
    _run([scp_bin, "-q", str(TEST_SRC), f"{host}:{REMOTE_DIR_REL}/test_mini_agy_runner.py"])
    _run([ssh_bin, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, finalize_cmd])

    result: dict[str, object] = {"ok": True, **plan}
    if verify:
        test_res = _run(
            [
                ssh_bin,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                host,
                f'python3.12 -B -m unittest discover -s "$HOME/{REMOTE_DIR_REL}" -v',
            ]
        )
        doc_res = _run(
            [
                ssh_bin,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                host,
                "mini-agy-runner doctor",
            ]
        )
        result["unit_tests_output"] = test_res.stderr.strip() or test_res.stdout.strip()
        result["doctor"] = json.loads(doc_res.stdout)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy mini_agy_runner.py to spencers-mac-mini")
    parser.add_argument("--host", default="spencers-mac-mini")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = deploy_mini_agy_runner(host=args.host, dry_run=args.dry_run, verify=args.verify)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        err_payload: dict[str, object] = {"ok": False, "error": str(exc)}
        if isinstance(exc, subprocess.CalledProcessError):
            err_payload["stdout"] = exc.stdout.strip()
            err_payload["stderr"] = exc.stderr.strip()
        print(json.dumps(err_payload, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
