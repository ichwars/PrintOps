#!/usr/bin/env python3
"""Run the authorized weekly security maintenance in an isolated Git worktree."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "ichwars/PrintOps"


def command(*args: str, cwd: Path, timeout: int = 120) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, umask=0o022)
    if result.returncode:
        # Avoid copying authentication errors or remote response bodies to logs.
        raise ValueError(f"{Path(args[0]).name} failed (exit {result.returncode})")
    return result.stdout.strip()


def preflight(repo: Path, codex: str) -> None:
    for executable in ("git", "gh", codex):
        if not shutil.which(executable):
            raise ValueError(f"Required executable missing: {executable}")
    if command("git", "rev-parse", "--show-toplevel", cwd=repo) != str(repo):
        raise ValueError("--repo must name the repository root")
    remote = command("git", "remote", "get-url", "origin", cwd=repo)
    if remote not in (
        "https://github.com/ichwars/PrintOps.git",
        "https://github.com/ichwars/PrintOps",
        "git@github.com:ichwars/PrintOps.git",
    ):
        raise ValueError("origin is not the authorized PrintOps repository")
    permission = command("gh", "api", f"repos/{REPOSITORY}", "--jq", ".permissions.push", cwd=repo)
    if permission != "true":
        raise ValueError("GitHub authentication lacks repository write access")
    command(codex, "login", "status", cwd=repo)
    if "--approve-for-me" not in command(codex, "exec", "--help", cwd=repo):
        raise ValueError("Codex CLI with automatic approval review is required")


def run(repo: Path, state: Path, codex: str, prompt: str) -> int:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Security maintenance is already running") from None
        preflight(repo, codex)
        command("git", "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main", cwd=repo)
        base = command("git", "rev-parse", "origin/main", cwd=repo)
        run_dir = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=state))
        checkout = run_dir / "checkout"
        branch = "codex/security-maintenance-" + run_dir.name.lower()
        command("git", "worktree", "add", "-b", branch, str(checkout), base, cwd=repo)
        (run_dir / "run.json").write_text(
            json.dumps({"base": base, "branch": branch, "checkout": str(checkout)}) + "\n", encoding="utf-8"
        )
        # The task text is local, reviewed policy. Issue/alert bodies are fetched as data by the agent.
        with (run_dir / "events.jsonl").open("w") as events, (run_dir / "stderr.log").open("w") as errors:
            result = subprocess.run(
                [
                    codex,
                    "exec",
                    "--approve-for-me",
                    "--json",
                    "-C",
                    str(checkout),
                    "--output-last-message",
                    str(run_dir / "summary.md"),
                    "-",
                ],
                input=prompt,
                text=True,
                stdout=events,
                stderr=errors,
                cwd=checkout,
                timeout=14_000,
            )
        (run_dir / "exit-code").write_text(str(result.returncode) + "\n", encoding="utf-8")
        print(f"Security maintenance exit {result.returncode}; private result: {run_dir / 'summary.md'}")
        # Keep worktrees and incomplete changes for diagnosis; never discard an unfinished fix.
        return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--check-config", action="store_true", help="Read-only authentication and capability check")
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    try:
        repo = args.repo.expanduser().resolve()
        if args.check_config:
            preflight(repo, args.codex)
            print("GitHub/Codex configuration checked; no agent run or repository changes")
            return 0
        state = args.state_dir.expanduser().resolve() if args.state_dir else repo / ".cache/security-maintenance"
        prompt = (Path(__file__).with_name("security-maintenance-prompt.md")).read_text(encoding="utf-8")
        return run(repo, state, args.codex, prompt)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Security maintenance failed: {error}", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(main())
