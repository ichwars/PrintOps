"""Require a published release and successful exact-commit builds before latest promotion."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = "ichwars/PrintOps"
REQUIRED = {
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/release-container.yml",
    ".github/workflows/windows-installer.yml",
}


def require_successful_runs(runs: list[dict], sha: str, tag: str) -> None:
    selected = {}
    for run in runs:
        path = run.get("path")
        if path not in REQUIRED or run.get("head_sha") != sha:
            continue
        if run.get("event") != "push" or run.get("head_branch") not in ("main", tag):
            continue
        if path not in selected or (run["id"], run.get("run_attempt", 1)) > (
            selected[path]["id"],
            selected[path].get("run_attempt", 1),
        ):
            selected[path] = run
    missing = REQUIRED - selected.keys()
    failed = [
        path for path, run in selected.items() if run.get("status") != "completed" or run.get("conclusion") != "success"
    ]
    if missing or failed:
        raise ValueError(
            "Release checks/builds missing, pending or failed: " + ", ".join(sorted(missing | set(failed)))
        )


def api(path: str):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{path}", "--paginate", "--slurp"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?", args.tag):
        raise ValueError("Only stable release tags may be promoted")
    release = api(f"releases/tags/{args.tag}")[0]
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Release is not a published stable release")
    if api("releases/latest")[0].get("tag_name") != args.tag:
        raise ValueError("Refusing to overwrite latest with an older release")
    ref = api(f"git/ref/tags/{args.tag}")[0]["object"]
    if ref["type"] == "tag":
        ref = api(f"git/tags/{ref['sha']}")[0]["object"]
    if ref["type"] != "commit":
        raise ValueError("Release tag does not resolve to a commit")
    sha = ref["sha"]
    pages = api(f"actions/runs?head_sha={sha}&event=push&per_page=100")
    require_successful_runs([run for page in pages for run in page["workflow_runs"]], sha, args.tag)
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"sha={sha}\n")
    print(f"Release {args.tag} at {sha}: exact-commit CI, scans, container and Windows builds successful")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
