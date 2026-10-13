"""Exercise frontend check orchestration without running heavyweight npm stages."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("typecheck_rc", "lint_rc", "test_rc"),
    [(0, 0, 0), (7, 0, 0), (0, 8, 0), (0, 0, 9), (7, 8, 0), (7, 0, 9), (0, 8, 9), (7, 8, 9)],
)
def test_frontend_runner_preserves_every_stage_failure(tmp_path, typecheck_rc, lint_rc, test_rc):
    """A later successful stage must never mask an earlier failed check."""
    repo = Path(__file__).resolve().parents[3]
    shutil.copyfile(repo / "test_frontend.sh", tmp_path / "test_frontend.sh")
    (tmp_path / "frontend").mkdir()
    executables = tmp_path / "executables"
    executables.mkdir()
    shim = """#!/bin/sh
case "$*" in
    'run typecheck'|'tsc') stage=typecheck; rc=$TYPECHECK_RC ;;
    'run lint') stage=lint; rc=$LINT_RC ;;
    'run test:run') stage=tests; rc=$TEST_RC ;;
    *) echo "Unexpected command: $*" >&2; exit 99 ;;
esac
echo "stage=$stage exit=$rc"
exit "$rc"
"""
    for name in ("npm", "npx"):
        executable = executables / name
        executable.write_text(shim)
        executable.chmod(0o755)
    result = subprocess.run(
        ["sh", "test_frontend.sh"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{executables}:{os.environ['PATH']}",
            "TYPECHECK_RC": str(typecheck_rc),
            "LINT_RC": str(lint_rc),
            "TEST_RC": str(test_rc),
        },
        text=True,
        capture_output=True,
        timeout=10,
    )
    if any((typecheck_rc, lint_rc, test_rc)):
        assert result.returncode != 0, result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
    # Run and report every stage even when an earlier one fails.
    for stage, rc in (("typecheck", typecheck_rc), ("lint", lint_rc), ("tests", test_rc)):
        assert f"stage={stage} exit={rc}" in result.stdout
