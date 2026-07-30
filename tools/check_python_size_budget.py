#!/usr/bin/env python3
"""Fail CI when Python files or functions exceed the current size budget.

The allowlists below are intentional refactoring debt. They let the existing
baseline pass, but only up to the recorded line count, so oversized modules and
functions cannot quietly grow while the routers and services are split further.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

DEFAULT_PATHS = ("backend/app",)
DEFAULT_MAX_FILE_LINES = 2000
DEFAULT_MAX_FUNCTION_LINES = 300


FILE_ALLOWLIST = {
    "backend/app/main.py": 6986,
    "backend/app/core/database.py": 4137,
    "backend/app/services/bambu_mqtt.py": 5804,
    "backend/app/services/notification_service.py": 2053,
    "backend/app/services/print_scheduler.py": 3512,
    "backend/app/api/routes/archives.py": 4806,
    "backend/app/api/routes/inventory.py": 2700,
    "backend/app/api/routes/library.py": 4999,
    "backend/app/api/routes/mfa.py": 2279,
    "backend/app/api/routes/printers.py": 999,
    "backend/app/api/routes/spoolman_inventory.py": 2060,
}


FUNCTION_ALLOWLIST = {
    "backend/app/main.py::on_ams_change": 690,
    "backend/app/main.py::on_print_start": 1073,
    "backend/app/main.py::on_print_complete": 1226,
    "backend/app/main.py::lifespan": 367,
    "backend/app/core/database.py::run_migrations": 2848,
    "backend/app/core/database.py::seed_default_groups": 348,
    "backend/app/services/bambu_mqtt.py::_handle_ams_data": 553,
    "backend/app/services/bambu_mqtt.py::_update_state": 1277,
    "backend/app/services/printer_manager.py::printer_state_to_dict": 335,
    "backend/app/services/print_scheduler.py::check_queue": 433,
    "backend/app/services/print_scheduler.py::_start_print": 603,
    "backend/app/services/usage_tracker.py::_track_from_3mf": 537,
    "backend/app/api/routes/archives.py::get_archive_plates": 302,
    "backend/app/api/routes/library.py::scan_external_folder": 325,
    "backend/app/api/routes/library.py::_run_slicer_with_fallback": 353,
    "backend/app/api/routes/metrics.py::get_metrics": 386,
    "backend/app/api/routes/mfa.py::oidc_callback": 404,
    "backend/app/api/routes/printers_ams.py::configure_ams_slot": 377,
    "backend/app/api/routes/print_queue.py::add_to_queue": 365,
    "backend/app/api/routes/spoolman.py::link_spool": 306,
    "backend/app/api/routes/settings.py::restore_backup": 304,
    "backend/app/api/routes/support.py::_collect_support_info": 452,
    "backend/app/api/routes/updates.py::_perform_update": 303,
}


def normalized(path: Path) -> str:
    return path.as_posix()


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return sorted(set(files))


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def check_file_sizes(files: list[Path], max_lines: int) -> list[str]:
    errors: list[str] = []
    for path in files:
        rel = normalized(path)
        lines = line_count(path)
        budget = FILE_ALLOWLIST.get(rel, max_lines)
        if lines > budget:
            if rel in FILE_ALLOWLIST:
                errors.append(f"{rel}: {lines} lines exceeds allowlisted budget {budget}")
            else:
                errors.append(f"{rel}: {lines} lines exceeds max {max_lines}")
    return errors


def check_function_sizes(files: list[Path], max_lines: int) -> list[str]:
    errors: list[str] = []
    for path in files:
        rel = normalized(path)
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel)
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
            budget = FUNCTION_ALLOWLIST.get(key, max_lines)
            if lines > budget:
                if key in FUNCTION_ALLOWLIST:
                    errors.append(f"{key}: {lines} lines exceeds allowlisted budget {budget}")
                else:
                    errors.append(f"{key}: {lines} lines exceeds max {max_lines}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    parser.add_argument("--max-file-lines", type=int, default=DEFAULT_MAX_FILE_LINES)
    parser.add_argument("--max-function-lines", type=int, default=DEFAULT_MAX_FUNCTION_LINES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = iter_python_files([Path(path) for path in args.paths])
    errors = [
        *check_file_sizes(files, args.max_file_lines),
        *check_function_sizes(files, args.max_function_lines),
    ]
    if errors:
        print("Python size budget failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Python size budget passed for {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
