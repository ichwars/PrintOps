#!/usr/bin/env python3
"""Enforce repository-wide source file and Python function size budgets.

Grandfathered entries record current refactoring debt. Their exact line counts
prevent further growth until the files are split and the entries can be removed.
Generated output, vendored code, and locale data are validated elsewhere.
"""

from __future__ import annotations

import argparse
import ast
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

DEFAULT_PATHS = (".",)
DEFAULT_MAX_FUNCTION_LINES = 300

SOURCE_SUFFIX_LIMITS = {
    ".py": 2000,
    ".ts": 1500,
    ".tsx": 1500,
    ".js": 1000,
    ".mjs": 1000,
    ".css": 1500,
    ".scss": 1500,
    ".sh": 1000,
    ".ps1": 1000,
    ".bat": 1000,
    ".yml": 1000,
    ".yaml": 1000,
    ".toml": 1000,
    ".html": 1500,
    ".ini": 500,
    ".iss": 1000,
    ".service": 500,
    ".sql": 1000,
    ".go": 1500,
}

SOURCE_FILENAME_LIMITS = {
    "Dockerfile": 500,
}

TEST_PREFIX_LIMITS = {
    "backend/tests/": 3000,
    "frontend/src/__tests__/": 2000,
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "coverage",
    "dist",
    "gcode_viewer",
    "node_modules",
    "static",
}

EXCLUDED_PATH_PREFIXES = ("frontend/src/i18n/locales/",)

COMMENT_CHECK_PREFIXES = (
    "backend/app/",
    "frontend/src/",
    "scripts/",
    "tools/",
)

FILE_ALLOWLIST = {
    "backend/app/api/routes/archives.py": 4796,
    "backend/app/api/routes/inventory.py": 2700,
    "backend/app/api/routes/library.py": 4999,
    "backend/app/api/routes/mfa.py": 2262,
    "backend/app/api/routes/spoolman_inventory.py": 2056,
    "backend/app/core/database.py": 4139,
    "backend/app/main.py": 6987,
    "backend/app/services/bambu_mqtt.py": 5914,
    "backend/app/services/notification_service.py": 2147,
    "backend/app/services/print_scheduler.py": 3554,
    "backend/tests/integration/test_mfa_api.py": 5132,
    "backend/tests/integration/test_printers_api.py": 4094,
    "backend/tests/unit/services/test_bambu_mqtt.py": 6743,
    "backend/tests/unit/services/test_virtual_printer.py": 4056,
    "frontend/src/__tests__/pages/SettingsPage.test.tsx": 2252,
    "frontend/src/api/client.ts": 8156,
    "frontend/src/components/AddSmartPlugModal.tsx": 1745,
    "frontend/src/components/ConfigureAmsSlotModal.tsx": 1706,
    "frontend/src/components/ForecastPanel.tsx": 2055,
    "frontend/src/components/KProfilesView.tsx": 1720,
    "frontend/src/lib/orderMasterDataValidation.ts": 1733,
    "frontend/src/pages/ArchivesPage.tsx": 4368,
    "frontend/src/pages/BusinessDashboardPage.tsx": 2953,
    "frontend/src/pages/FileManagerPage.tsx": 2767,
    "frontend/src/pages/InventoryPage.tsx": 2920,
    "frontend/src/pages/PrintersPage.tsx": 9172,
    "frontend/src/pages/ProfilesPage.tsx": 2985,
    "frontend/src/pages/QueuePage.tsx": 2932,
    "frontend/src/pages/SettingsPage.tsx": 7618,
    "install/install.sh": 1031,
    "spoolbuddy/install/install.sh": 1654,
}

FUNCTION_ALLOWLIST = {
    "backend/app/api/routes/archives.py::get_archive_plates": 302,
    "backend/app/api/routes/library.py::_run_slicer_with_fallback": 353,
    "backend/app/api/routes/library.py::scan_external_folder": 325,
    "backend/app/api/routes/metrics.py::get_metrics": 370,
    "backend/app/api/routes/mfa.py::oidc_callback": 404,
    "backend/app/api/routes/printers_ams.py::configure_ams_slot": 377,
    "backend/app/api/routes/print_queue.py::add_to_queue": 365,
    "backend/app/api/routes/settings.py::restore_backup": 304,
    "backend/app/api/routes/spoolman.py::link_spool": 306,
    "backend/app/api/routes/support.py::_collect_support_info": 452,
    "backend/app/api/routes/updates.py::_perform_update": 303,
    "backend/app/core/database.py::run_migrations": 2850,
    "backend/app/core/database.py::seed_default_groups": 348,
    "backend/app/main.py::lifespan": 382,
    "backend/app/main.py::on_ams_change": 690,
    "backend/app/main.py::on_print_complete": 1230,
    "backend/app/main.py::on_print_start": 1073,
    "backend/app/services/bambu_mqtt.py::_handle_ams_data": 570,
    "backend/app/services/bambu_mqtt.py::_update_state": 1277,
    "backend/app/services/printer_manager.py::printer_state_to_dict": 335,
    "backend/app/services/print_scheduler.py::_start_print": 611,
    "backend/app/services/print_scheduler.py::check_queue": 420,
    "backend/app/services/usage_tracker.py::_track_from_3mf": 537,
}

DECORATIVE_SEPARATOR_RE = re.compile(r"^\s*(?:#|//)\s*[=-]{6,}\s*$")


def normalized(path: Path, root: Path = Path(".")) -> str:
    return path.absolute().relative_to(root.absolute()).as_posix()


def is_excluded(path: Path, root: Path) -> bool:
    rel = normalized(path, root)
    if any(part in EXCLUDED_DIR_NAMES for part in Path(rel).parts[:-1]):
        return True
    return rel.startswith(EXCLUDED_PATH_PREFIXES)


def iter_source_files(paths: Iterable[Path], root: Path = Path(".")) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
        for candidate in candidates:
            if (
                candidate.is_file()
                and (candidate.suffix.lower() in SOURCE_SUFFIX_LIMITS or candidate.name in SOURCE_FILENAME_LIMITS)
                and not is_excluded(candidate, root)
            ):
                files.add(candidate)
    return sorted(files, key=lambda path: normalized(path, root))


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def file_limit(
    rel: str,
    path: Path,
    suffix_limits: Mapping[str, int],
    test_prefix_limits: Mapping[str, int],
    filename_limits: Mapping[str, int],
) -> int:
    for prefix, limit in test_prefix_limits.items():
        if rel.startswith(prefix):
            return limit
    if path.name in filename_limits:
        return filename_limits[path.name]
    return suffix_limits[path.suffix.lower()]


def check_file_sizes(
    files: Iterable[Path],
    *,
    root: Path = Path("."),
    suffix_limits: Mapping[str, int] = SOURCE_SUFFIX_LIMITS,
    test_prefix_limits: Mapping[str, int] = TEST_PREFIX_LIMITS,
    filename_limits: Mapping[str, int] = SOURCE_FILENAME_LIMITS,
    allowlist: Mapping[str, int] = FILE_ALLOWLIST,
) -> list[str]:
    errors: list[str] = []
    for path in files:
        rel = normalized(path, root)
        lines = line_count(path)
        budget = allowlist.get(
            rel,
            file_limit(rel, path, suffix_limits, test_prefix_limits, filename_limits),
        )
        if rel in allowlist and lines < budget:
            errors.append(f"{rel}: grandfathered budget {budget} is stale; current size is {lines}")
        elif lines > budget and rel in allowlist:
            errors.append(f"{rel}: {lines} lines exceeds grandfathered budget {budget}")
        elif lines > budget:
            errors.append(f"{rel}: {lines} lines exceeds max {budget}")
        else:
            continue
    return errors


def check_decorative_comments(files: Iterable[Path], *, root: Path = Path(".")) -> list[str]:
    errors: list[str] = []
    for path in files:
        rel = normalized(path, root)
        if not rel.startswith(COMMENT_CHECK_PREFIXES):
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if DECORATIVE_SEPARATOR_RE.fullmatch(line):
                errors.append(f"{rel}:{line_number}: decorative separator comment is not allowed")
    return errors


def check_python_function_sizes(
    files: Iterable[Path],
    *,
    root: Path = Path("."),
    max_lines: int = DEFAULT_MAX_FUNCTION_LINES,
    allowlist: Mapping[str, int] = FUNCTION_ALLOWLIST,
) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix.lower() != ".py":
            continue
        rel = normalized(path, root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            errors.append(f"{rel}: cannot parse Python AST: {exc}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.end_lineno is None:
                continue
            lines = node.end_lineno - node.lineno + 1
            key = f"{rel}::{node.name}"
            budget = allowlist.get(key, max_lines)
            if key in allowlist and lines < budget:
                errors.append(f"{key}: grandfathered budget {budget} is stale; current size is {lines}")
            elif lines > budget and key in allowlist:
                errors.append(f"{key}: {lines} lines exceeds grandfathered budget {budget}")
            elif lines > budget:
                errors.append(f"{key}: {lines} lines exceeds max {max_lines}")
            else:
                continue
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    parser.add_argument("--max-function-lines", type=int, default=DEFAULT_MAX_FUNCTION_LINES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(".")
    files = iter_source_files((Path(path) for path in args.paths), root=root)
    errors = [
        *check_file_sizes(files, root=root),
        *check_python_function_sizes(files, root=root, max_lines=args.max_function_lines),
        *check_decorative_comments(files, root=root),
    ]
    if errors:
        print("Source size budget failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Source size budget passed for {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
