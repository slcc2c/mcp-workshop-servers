"""Exercise the installed CLI with a mock agy and a disposable Git repository."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
RUNNER = (
    _HERE / "mini_agy_runner.py"
    if (_HERE / "mini_agy_runner.py").is_file()
    else _HERE.parents[1] / "scripts" / "mini_agy_runner.py"
)

try:
    import pytest

    pytestmark = pytest.mark.unit
except ImportError:
    pass
MOCK = r"""
import json
import os
import sys
import time

args = sys.argv[1:]
if args == ["--version"]:
    print("1.5.17 mock")
elif args == ["remote-control", "status"]:
    print("Daemon state = running\nInstance name: mac-mini")
else:
    assert args[0] == "--output-format=stream-json", args
    assert args[-1].startswith("--print="), args
    prompt = args[-1].removeprefix("--print=")
    resume = any(arg.startswith("--resume=") for arg in args)
    if resume:
        assert "--resume=abc-123" in args
    print(json.dumps({
        "event": "init",
        "conversation_id": "abc-123",
        "init": {
            "cwd": os.getcwd(),
            "tools": [],
            "permission_mode": "request-review",
            "args": args,
        },
    }), flush=True)
    if prompt == "hold":
        print(json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": "abc-123",
                "step_index": 1,
                "state": "ACTIVE",
                "step_type": "agent_response",
                "text_delta": "holding...",
            },
        }), flush=True)
        time.sleep(60)
    print("non-JSON diagnostic", flush=True)
    print(json.dumps({
        "event": "step_update",
        "step_update": {
            "conversation_id": "abc-123",
            "step_index": 1,
            "state": "ACTIVE",
            "step_type": "agent_response",
            "text_delta": "work",
        },
    }), flush=True)
    print(json.dumps({
        "event": "step_update",
        "step_update": {
            "conversation_id": "abc-123",
            "step_index": 1,
            "state": "DONE",
            "step_type": "agent_response",
            "text_delta": "ing\n",
        },
    }), flush=True)
    print(json.dumps({
        "event": "result",
        "result": {
            "conversation_id": "abc-123",
            "status": "SUCCESS" if prompt != "fail" else "FAILED",
            "response": prompt + "\n",
            "num_turns": 1,
        },
    }), flush=True)
    if prompt == "fail":
        sys.exit(7)
"""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.repo = self.home / "repos/fixture"
        self.repo.mkdir(parents=True)
        self.git("init", "-q")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--allow-empty", "-qm", "fixture")
        mock = self.home / "mock agy"
        mock.write_text(f"#!{sys.executable}\n{MOCK}")
        mock.chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.home), MINI_AGY_BIN=str(mock))
        (self.home / ".local/bin").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/bin/python3.12").symlink_to(sys.executable)
        self.env["PATH"] = str(self.home / ".local/bin") + os.pathsep + self.env["PATH"]

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def cli(self, *args, code=0, text=None):
        result = subprocess.run(
            [sys.executable, str(RUNNER), *args], env=self.env,
            input=text or "", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, code, (result.stdout, result.stderr))
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        data = json.loads(result.stdout)
        if code:
            self.assertIn("error", data)
        return data

    def poll(self, job, condition):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = self.cli("status", job)
            if condition(status):
                return status
            time.sleep(0.05)
        self.fail(f"timed out waiting for {job}: {status}")

    def test_doctor_and_json_errors(self):
        result = self.cli("doctor")
        self.assertTrue(result["ok"])
        self.assertEqual(result["checks"]["agy_version"]["output"], "1.5.17 mock")
        self.assertEqual(result["checks"]["remote_control"]["output"],
                         "Daemon state = running\nInstance name: mac-mini")
        self.assertEqual(self.cli("list"), {"jobs": []})
        self.cli("status", "../bad", code=1)
        self.cli("status", "a" * 32, code=1)
        self.cli("list", "--limit", "-1", code=1)

    def test_start_status_resume_and_clean_branch(self):
        prompt = "--literal $(pwd)\nsecond line"
        self.cli("start", "--repo", "fixture", "--runtime", "unknown", "--prompt", "x", code=1)
        start = self.cli("start", "--repo", "fixture", "--runtime", "agy",
                         "--branch", "job-fixture",
                         "--base-ref", "HEAD", "--mode", "plan", "--model", "fixture",
                         "--effort", "medium", "--sandbox", "--timeout", "5s",
                         "--prompt-file", "-", text=prompt)
        self.assertEqual(start["runtime"], "agy")
        job = start["job_id"]
        self.assertEqual(start["status"], "running")
        done = self.poll(job, lambda item: item["status"] != "running")
        self.assertEqual(done["exit_code"], 0)
        self.assertEqual(done["conversation_id"], "abc-123")
        self.assertEqual(done["summary"], prompt)
        self.assertEqual(done["git_status"], "")
        args = done["events"][0]["init"]["args"]
        self.assertEqual(args[1:-1], ["--mode=plan", "--model=fixture",
                                      "--effort=medium", "--sandbox", "--print-timeout=5s"])
        self.assertEqual(Path(done["events"][0]["init"]["cwd"]).resolve(),
                         Path(start["worktree"]).resolve())
        self.assertEqual(self.cli("status", job, "--tail", "1")["events"][0]["event"],
                         "result")
        self.assertEqual(self.cli("status", job, "--tail", "0")["events"], [])
        path = self.home / "resume prompt.txt"
        path.write_text("resumed")
        self.cli("resume", job, "--mode", "accept-edits", "--prompt-file", str(path))
        done = self.poll(job, lambda item: item["status"] != "running")
        self.assertEqual(done["summary"], "resumed")
        self.assertEqual(done["exit_code"], 0)
        resume_init = [ev for ev in done["events"] if ev.get("event") == "init"][-1]
        args = resume_init["init"]["args"]
        self.assertIn("--resume=abc-123", args)
        self.assertIn("--mode=accept-edits", args)
        self.assertIn("--sandbox", args)
        self.assertEqual(self.cli("list", "--limit", "1")["jobs"][0]["job_id"], job)
        self.assertEqual(self.cli("list", "--active"), {"jobs": []})
        cleaned = self.cli("cleanup", job, "--delete-branch")
        self.assertTrue(cleaned["worktree_removed"])
        self.assertTrue(cleaned["branch_deleted"])
        self.assertFalse(Path(start["worktree"]).exists())
        self.assertEqual(self.git("branch", "--list", "job-fixture"), "")
        self.cli("cleanup", job, "--delete-branch")
        self.cli("resume", job, "--prompt", "again", code=1)

    def test_cancel_and_dirty_cleanup(self):
        start = self.cli("start", "--repo", str(self.repo), "--prompt", "hold")
        job = start["job_id"]
        self.addCleanup(lambda: self.best_effort_cancel(job))
        running = self.poll(job, lambda item: item["summary"] == "holding...")
        self.assertEqual(running["conversation_id"], "abc-123")
        self.assertEqual(self.cli("list", "--active")["jobs"][0]["job_id"], job)
        self.cli("resume", job, "--prompt", "retry", code=1)
        self.cli("cleanup", job, "--force", code=1)
        self.assertEqual(self.cli("cancel", job)["status"], "cancelled")
        self.assertEqual(self.cli("status", job)["status"], "cancelled")
        self.cli("cancel", job)
        dirty = Path(start["worktree"]) / "untracked"
        dirty.write_text("keep")
        self.assertIn("dirty", self.cli("cleanup", job, code=1)["error"])
        self.assertEqual(dirty.read_text(), "keep")
        self.assertTrue(self.cli("cleanup", job, "--delete-branch", "--force")["branch_deleted"])

    def best_effort_cancel(self, job):
        subprocess.run(
            [sys.executable, str(RUNNER), "cancel", job], env=self.env,
            capture_output=True, timeout=10,
        )

    def test_failed_no_worktree_job_preserves_checkout(self):
        start = self.cli("start", "--repo", "fixture", "--no-worktree", "--prompt", "fail")
        job = start["job_id"]
        done = self.poll(job, lambda item: item["status"] != "running")
        self.assertEqual(done["status"], "failed")
        self.assertEqual(done["exit_code"], 7)
        self.cli("cleanup", job, "--force", "--delete-branch", code=1)
        self.assertTrue(self.repo.is_dir())
        self.assertEqual(self.git("status", "--short"), "")


if __name__ == "__main__":
    unittest.main()
