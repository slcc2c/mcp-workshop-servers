#!/usr/bin/env python3.12
"""Manage detached Antigravity print sessions in local Git worktrees."""

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

HOME = Path.home()
STATE = HOME / ".local/share/mini-agy"
LOGS = HOME / "Library/Logs/mini-agy"
REPOS = HOME / "repos"
AGY = os.environ.get("MINI_AGY_BIN", str(HOME / ".local/bin/agy"))


def build_agy_command(prompt_text, options):
    return [AGY, "--output-format=stream-json", *options, f"--print={prompt_text}"]


RUNTIME_ADAPTERS = {
    "agy": build_agy_command,
}


def now():
    return datetime.now(UTC).isoformat()


def run(*argv, cwd=None, check=True):
    result = subprocess.run(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", shell=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip()
                           or f"{argv[0]} exited {result.returncode}")
    return result


def git(repo, *args):
    return run("git", "-C", str(repo), *args).stdout.rstrip("\n")


def save(job, meta):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=job,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(meta, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, job / "meta.json")
        finally:
            temporary.unlink(missing_ok=True)


def read(job):
    return json.loads((job / "meta.json").read_text())


@contextmanager
def locked(job):
    with (job / "lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def get_job(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("invalid job ID")
    job = STATE / "jobs" / job_id
    if not (job / "meta.json").is_file():
        raise ValueError(f"unknown job: {job_id}")
    return job


def alive(pid):
    # A detached supervisor must still lead its own process group.
    try:
        os.kill(pid, 0)
        return os.getpgid(pid) == pid
    except ProcessLookupError:
        return False


def read_events(path, tail=0, offset=0):
    recent = deque(maxlen=tail)
    conversation = summary = None
    active_step = None
    active_chunks = []
    if not path.exists():
        return conversation, summary, []
    with path.open("rb") as stream:
        stream.seek(offset)
        for line in stream:
            if not line.endswith(b"\n"):
                break
            try:
                event = json.loads(line, parse_constant=invalid_constant)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(event, dict):
                continue
            recent.append(event)
            for container in (event, event.get("step_update"), event.get("result")):
                if not isinstance(container, dict):
                    continue
                for key in ("conversation_id", "conversationId", "session_id", "sessionId"):
                    if isinstance(container.get(key), str) and container[key]:
                        conversation = container[key]
                        break
            event_kind = event.get("event")
            if event_kind == "init":
                active_step = None
                active_chunks = []
            elif event_kind == "step_update":
                step = event.get("step_update")
                if isinstance(step, dict) and step.get("step_type") == "agent_response":
                    step_index = step.get("step_index")
                    if step_index != active_step:
                        active_step = step_index
                        active_chunks = []
                    delta = step.get("text_delta")
                    if isinstance(delta, str) and delta:
                        active_chunks.append(delta)
                        text = "".join(active_chunks).rstrip("\n")
                        if text:
                            summary = text
            elif event_kind == "result":
                payload = event.get("result")
                if isinstance(payload, dict):
                    response = payload.get("response")
                    if isinstance(response, str):
                        text = response.rstrip("\n")
                        if text:
                            summary = text
                active_step = None
                active_chunks = []
            else:
                message = event.get("message")
                if not isinstance(message, dict):
                    message = event
                kind = event.get("type")
                if kind in ("assistant", "result") or message.get("role") == "assistant":
                    content = event.get("result") or message.get("content") or message.get("text")
                    if isinstance(content, list):
                        content = "\n".join(
                            part["text"] for part in content
                            if isinstance(part, dict) and isinstance(part.get("text"), str)
                        )
                    if isinstance(content, str) and content:
                        summary = content.rstrip("\n")
    return conversation, summary, list(recent)


def invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def capture(meta, tail=0):
    conversation, summary, events = read_events(Path(meta["events_path"]), tail)
    meta["conversation_id"] = conversation or meta.get("conversation_id")
    meta["summary"] = summary or meta.get("summary")
    return events


def reconcile(job, meta):
    if meta["status"] == "running" and not alive(meta["pid"]):
        capture(meta)
        meta.update(status="failed", finished_at=now(), exit_code=None,
                    error="supervisor exited without recording a result")
        save(job, meta)


def prompt(args):
    if args.prompt is not None:
        return args.prompt
    if args.prompt_file == "-":
        return sys.stdin.read()
    return Path(args.prompt_file).read_text(encoding="utf-8")


def launch(job, meta, prompt_path, options):
    events = Path(meta["events_path"])
    events.touch()
    with events.open("rb+") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell():
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                stream.write(b"\n")
        offset = stream.tell()
    meta.update(status="running", started_at=now(), finished_at=None,
                exit_code=None, pid=None)
    meta.pop("error", None)
    with Path(meta["log_path"]).open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_worker",
             str(job), str(prompt_path), str(offset), *options],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
            start_new_session=True, shell=False,
        )
        meta["pid"] = process.pid
        try:
            save(job, meta)
        except OSError:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    return meta


def worker(job, prompt_path, offset, options):
    with locked(job):
        meta = read(job)
        if meta["status"] != "running" or meta["pid"] != os.getpid():
            return
        runtime_name = meta.get("runtime", "agy")
    try:
        adapter = RUNTIME_ADAPTERS.get(runtime_name)
        if adapter is None:
            raise ValueError(f"unsupported runtime: {runtime_name}")
        with Path(meta["events_path"]).open("ab") as events:
            result = subprocess.run(
                adapter(prompt_path.read_text(encoding="utf-8"), options),
                cwd=meta["worktree"], stdin=subprocess.DEVNULL, stdout=events,
                shell=False,
            )
        code = result.returncode
        error = None
    except (OSError, ValueError) as exc:
        code, error = None, str(exc)
        print(error, file=sys.stderr)
    with locked(job):
        meta = read(job)
        if meta["status"] != "running" or meta["pid"] != os.getpid():
            return
        conversation, summary, _ = read_events(Path(meta["events_path"]), offset=offset)
        meta.update(status="completed" if code == 0 else "failed", exit_code=code,
                    finished_at=now(), conversation_id=conversation or meta.get("conversation_id"),
                    summary=summary or meta.get("summary"))
        if error:
            meta["error"] = error
        save(job, meta)


def ensure_dirs():
    for path in (STATE / "jobs", LOGS):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)


def doctor(args):
    ensure_dirs()
    checks = {}
    for key, cmd in {
        "agy_version": (AGY, "--version"),
        "remote_control": (AGY, "remote-control", "status"),
        "git_version": ("git", "--version"),
        "python_version": ("python3.12", "--version"),
    }.items():
        try:
            result = run(*cmd, check=False)
            checks[key] = {"exit_code": result.returncode,
                           "output": "\n".join(filter(None, (result.stdout.strip(),
                                                            result.stderr.strip())))}
        except OSError as exc:
            checks[key] = {"exit_code": None, "output": str(exc)}
    checks["repos_readable"] = REPOS.is_dir() and os.access(REPOS, os.R_OK | os.X_OK)
    for key, path in (("state_writable", STATE), ("logs_writable", LOGS)):
        try:
            with tempfile.TemporaryFile(dir=path):
                checks[key] = True
        except OSError:
            checks[key] = False
    ok = all(value["exit_code"] == 0 if isinstance(value, dict) else value
             for value in checks.values())
    return {"ok": ok, "checks": checks, **({} if ok else {"error": "doctor checks failed"})}


def option_flags(args, defaults=None):
    settings = dict(defaults or {})
    for name in ("mode", "model", "effort", "sandbox", "timeout"):
        value = getattr(args, name, None)
        if value is not None:
            settings[name] = value
    flags = [f"--{key}={settings[key]}" for key in ("mode", "model", "effort")
             if key in settings]
    if settings.get("sandbox"):
        flags.append("--sandbox")
    if settings.get("timeout") is not None:
        flags.append(f"--print-timeout={settings['timeout']}")
    return settings, flags


def start(args):
    text = prompt(args)
    if "\x00" in text:
        raise ValueError("prompt contains a NUL byte")
    repo_arg = Path(args.repo).expanduser()
    if not repo_arg.is_absolute():
        if len(repo_arg.parts) != 1 or repo_arg.name == "..":
            raise ValueError("use a repository name or an absolute path")
        repo_arg = REPOS / repo_arg
    repo = Path(git(repo_arg, "rev-parse", "--show-toplevel")).resolve()
    if args.no_worktree and (args.branch or args.base_ref != "HEAD"):
        raise ValueError("--branch and --base-ref require a managed worktree")
    ensure_dirs()
    job_id = uuid.uuid4().hex
    job = STATE / "jobs" / job_id
    job.mkdir(mode=0o700)
    with locked(job):
        prompt_path = job / "prompt.txt"
        prompt_path.write_text(text, encoding="utf-8")
        branch = args.branch or f"agy/{job_id}"
        worktree = repo if args.no_worktree else STATE / "worktrees" / repo.name / job_id
        if args.no_worktree:
            branch = git(repo, "branch", "--show-current") or None
        settings, flags = option_flags(args)
        runtime_name = getattr(args, "runtime", None) or "agy"
        if runtime_name not in RUNTIME_ADAPTERS:
            raise ValueError(f"unsupported runtime: {runtime_name}")
        meta = {
            "job_id": job_id, "created_at": now(), "repo": str(repo),
            "worktree": str(worktree), "branch": branch, "managed": not args.no_worktree,
            "runtime": runtime_name,
            "events_path": str(job / "events.ndjson"),
            "log_path": str(LOGS / f"{job_id}.stderr.log"), "settings": settings,
            "conversation_id": None, "summary": None, "resume_count": 0,
            "worktree_removed": False, "branch_deleted": False,
        }
        try:
            if meta["managed"]:
                base = git(repo, "rev-parse", "--verify", "--end-of-options",
                           f"{args.base_ref}^{{commit}}")
                worktree.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                git(repo, "worktree", "add", "-b", branch, "--", str(worktree), base)
        except (OSError, RuntimeError) as exc:
            meta.update(status="failed", pid=None, exit_code=None, finished_at=now(),
                        error=str(exc), managed=False)
            save(job, meta)
            raise
        try:
            return launch(job, meta, prompt_path, flags)
        except (OSError, ValueError) as exc:
            meta.update(status="failed", pid=None, exit_code=None, finished_at=now(),
                        error=str(exc))
            save(job, meta)
            raise


def status(args, job, meta):
    events = capture(meta, args.tail)
    worktree = Path(meta["worktree"])
    dirty = git(worktree, "status", "--short") if worktree.is_dir() else None
    return dict(meta, events=events, git_status=dirty)


def resume(args, job, meta):
    if meta["status"] == "running":
        raise ValueError("job is running")
    if meta["worktree_removed"] or not Path(meta["worktree"]).is_dir():
        raise ValueError("job worktree is unavailable")
    capture(meta)
    conversation = meta["conversation_id"]
    if not conversation:
        raise ValueError("job has no conversation ID")
    text = prompt(args)
    if "\x00" in text:
        raise ValueError("prompt contains a NUL byte")
    number = meta["resume_count"] + 1
    path = job / f"resume-{number}.txt"
    path.write_text(text, encoding="utf-8")
    settings, flags = option_flags(args, meta["settings"])
    meta.update(resume_count=number, settings=settings)
    return launch(job, meta, path, [f"--resume={conversation}", *flags])


def cancel(args, job, meta):
    if meta["status"] == "cancelled":
        return meta
    if meta["status"] != "running":
        raise ValueError("job is not running")
    pid = meta["pid"]
    try:
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            os.killpg(pid, 0)
            time.sleep(0.05)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    capture(meta)
    meta.update(status="cancelled", finished_at=now(), exit_code=None)
    save(job, meta)
    return meta


def list_jobs(args):
    jobs = []
    for path in (STATE / "jobs").glob("*/meta.json"):
        job = path.parent
        with locked(job):
            meta = read(job)
            reconcile(job, meta)
        if not args.active or meta["status"] == "running":
            jobs.append(meta)
    jobs.sort(key=lambda item: item["created_at"], reverse=True)
    return {"jobs": jobs[:args.limit]}


def cleanup(args, job, meta):
    if meta["status"] == "running":
        raise ValueError("job is running")
    if not meta["managed"]:
        raise ValueError("job has no managed worktree")
    repo = Path(meta["repo"])
    worktree = Path(meta["worktree"])
    if not meta["worktree_removed"]:
        if worktree.exists() and not args.force and git(
            worktree, "status", "--short", "--untracked-files=all", "--ignored=matching"
        ):
            raise ValueError("worktree is dirty; use --force to discard changes")
        registered = git(repo, "worktree", "list", "--porcelain", "-z").split("\x00")
        registered_paths = {Path(entry.removeprefix("worktree ")).resolve()
                            for entry in registered if entry.startswith("worktree ")}
        if worktree.resolve() in registered_paths:
            git(repo, "worktree", "remove", *(["--force"] if args.force else []),
                "--", str(worktree))
        elif worktree.exists():
            raise ValueError("job worktree path exists without a Git registration")
        meta["worktree_removed"] = True
        save(job, meta)
    if args.delete_branch and not meta["branch_deleted"]:
        if git(repo, "branch", "--list", "--", meta["branch"]):
            git(repo, "branch", "-D" if args.force else "-d", "--", meta["branch"])
        meta["branch_deleted"] = True
        save(job, meta)
    return meta


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

    def print_help(self, file=None):
        super().print_help(file or sys.stderr)


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def parser():
    root = Parser(prog="mini-agy-runner", allow_abbrev=False)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    start_parser = commands.add_parser("start", allow_abbrev=False)
    start_parser.add_argument("--repo", required=True)
    start_parser.add_argument("--runtime", choices=tuple(RUNTIME_ADAPTERS), default="agy")
    start_parser.add_argument("--branch")
    start_parser.add_argument("--base-ref", default="HEAD")
    start_parser.add_argument("--sandbox", action="store_true", default=None)
    start_parser.add_argument("--timeout")
    start_parser.add_argument("--no-worktree", action="store_true")
    resume_parser = commands.add_parser("resume", allow_abbrev=False)
    resume_parser.add_argument("job_id")
    for command in (start_parser, resume_parser):
        group = command.add_mutually_exclusive_group(required=True)
        group.add_argument("--prompt")
        group.add_argument("--prompt-file")
        command.add_argument("--mode", choices=("auto", "accept-edits", "plan"))
        command.add_argument("--model")
        command.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"))
    status_parser = commands.add_parser("status")
    status_parser.add_argument("job_id")
    status_parser.add_argument("--tail", type=nonnegative, default=20)
    commands.add_parser("cancel").add_argument("job_id")
    listing = commands.add_parser("list")
    listing.add_argument("--active", action="store_true")
    listing.add_argument("--limit", type=nonnegative)
    cleaning = commands.add_parser("cleanup")
    cleaning.add_argument("job_id")
    cleaning.add_argument("--delete-branch", action="store_true")
    cleaning.add_argument("--force", action="store_true")
    return root


def main(argv):
    args = parser().parse_args(argv)
    commands = {"start": start, "doctor": doctor, "list": list_jobs}
    if args.command in commands:
        return commands[args.command](args)
    commands = {"status": status, "resume": resume, "cancel": cancel, "cleanup": cleanup}
    job = get_job(args.job_id)
    with locked(job):
        meta = read(job)
        reconcile(job, meta)
        return commands[args.command](args, job, meta)


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "_worker":
        worker(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), sys.argv[5:])
    else:
        try:
            result = main(sys.argv[1:])
        except (OSError, RuntimeError, ValueError) as exc:
            result = {"error": str(exc)}
        except SystemExit as exc:
            if exc.code:
                raise
            result = {"help": True}
        print(json.dumps(result, allow_nan=False))
        sys.exit(1 if "error" in result and "job_id" not in result else 0)
