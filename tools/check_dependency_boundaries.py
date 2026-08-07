"""Validate the separation between runtime and development dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEV_ONLY_PACKAGES = frozenset(
    {
        "bandit",
        "pip-audit",
        "pip-tools",
        "pre-commit",
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "pytest-split",
        "pytest-timeout",
        "pytest-xdist",
        "ruff",
    }
)

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^]]+\])?")
_INCLUDE = re.compile(r"^\s*(?:-r|--requirement(?:\s+|=))\s*([^\s#]+)")


def canonicalize_name(name: str) -> str:
    """Return the normalized package key used by Python package indexes."""

    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(path: Path) -> set[str]:
    """Read package names from a requirements input or pip-compile lock."""

    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        match = _REQUIREMENT_NAME.match(line)
        if match:
            names.add(canonicalize_name(match.group(1)))
    return names


def included_requirement_files(path: Path) -> set[str]:
    """Read normalized file names referenced through pip requirement includes."""

    includes: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _INCLUDE.match(line)
        if match:
            includes.add(Path(match.group(1)).as_posix())
    return includes


def check_dependency_boundaries(root: Path) -> list[str]:
    """Return actionable dependency-boundary violations for a repository root."""

    runtime_input = root / "requirements.txt"
    dev_input = root / "requirements-dev.txt"
    runtime_lock = root / "requirements.lock.txt"
    dev_lock = root / "requirements-dev.lock.txt"

    missing_files = [path.name for path in (runtime_input, dev_input, runtime_lock, dev_lock) if not path.is_file()]
    if missing_files:
        return [f"Missing dependency file: {name}" for name in missing_files]

    runtime_direct = requirement_names(runtime_input)
    dev_direct = requirement_names(dev_input)
    runtime_locked = requirement_names(runtime_lock)
    dev_locked = requirement_names(dev_lock)

    errors: list[str] = []
    if "requirements.txt" not in included_requirement_files(dev_input):
        errors.append("requirements-dev.txt must include requirements.txt with -r or --requirement")

    runtime_tools = sorted(runtime_direct & DEV_ONLY_PACKAGES)
    if runtime_tools:
        errors.append("requirements.txt contains development-only packages: " + ", ".join(runtime_tools))

    locked_tools = sorted(runtime_locked & DEV_ONLY_PACKAGES)
    if locked_tools:
        errors.append("requirements.lock.txt contains development-only packages: " + ", ".join(locked_tools))

    missing_runtime = sorted(runtime_direct - runtime_locked)
    if missing_runtime:
        errors.append("requirements.lock.txt is missing direct runtime packages: " + ", ".join(missing_runtime))

    missing_dev = sorted((runtime_direct | dev_direct) - dev_locked)
    if missing_dev:
        errors.append("requirements-dev.lock.txt is missing direct packages: " + ", ".join(missing_dev))

    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    errors = check_dependency_boundaries(root)
    if errors:
        print("Dependency boundary check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Dependency boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
