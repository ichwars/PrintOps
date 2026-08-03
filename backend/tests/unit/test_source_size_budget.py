from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_source_size_budget.py"


@pytest.fixture
def checker() -> ModuleType:
    assert CHECKER_PATH.exists(), "the repository-wide source budget checker is missing"
    spec = importlib.util.spec_from_file_location("check_source_size_budget", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checks_non_python_file_limits(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "frontend" / "src" / "Large.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    errors = checker.check_file_sizes(
        [source],
        root=tmp_path,
        suffix_limits={".tsx": 2},
        test_prefix_limits={},
        allowlist={},
    )

    assert errors == ["frontend/src/Large.tsx: 3 lines exceeds max 2"]


def test_grandfathered_file_cannot_grow(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "app" / "legacy.py"
    source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    errors = checker.check_file_sizes(
        [source],
        root=tmp_path,
        suffix_limits={".py": 2},
        test_prefix_limits={},
        allowlist={"backend/app/legacy.py": 2},
    )

    assert errors == ["backend/app/legacy.py: 3 lines exceeds grandfathered budget 2"]


def test_grandfathered_file_budget_must_shrink_with_file(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "app" / "legacy.py"
    source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\n", encoding="utf-8")

    errors = checker.check_file_sizes(
        [source],
        root=tmp_path,
        suffix_limits={".py": 1},
        test_prefix_limits={},
        allowlist={"backend/app/legacy.py": 3},
    )

    assert errors == ["backend/app/legacy.py: grandfathered budget 3 is stale; current size is 2"]


def test_uses_a_separate_test_file_limit(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "tests" / "test_large.py"
    source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    errors = checker.check_file_sizes(
        [source],
        root=tmp_path,
        suffix_limits={".py": 2},
        test_prefix_limits={"backend/tests/": 3},
        allowlist={},
    )

    assert errors == []


def test_excludes_generated_vendor_and_locale_paths(tmp_path: Path, checker: ModuleType) -> None:
    included = tmp_path / "frontend" / "src" / "App.tsx"
    generated = tmp_path / "static" / "bundle.js"
    vendor = tmp_path / "gcode_viewer" / "vendor.js"
    locale = tmp_path / "frontend" / "src" / "i18n" / "locales" / "en.ts"
    for path in (included, generated, vendor, locale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source\n", encoding="utf-8")

    files = checker.iter_source_files([tmp_path], root=tmp_path)

    assert files == [included]


def test_includes_dockerfiles(tmp_path: Path, checker: ModuleType) -> None:
    dockerfile = tmp_path / "Dockerfile"
    test_dockerfile = tmp_path / "Dockerfile.test"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    test_dockerfile.write_text("FROM scratch\n", encoding="utf-8")

    files = checker.iter_source_files([tmp_path], root=tmp_path)

    assert files == [dockerfile, test_dockerfile]


def test_checks_python_function_budget(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "app" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def oversized():\n    first = 1\n    second = 2\n    return first + second\n",
        encoding="utf-8",
    )

    errors = checker.check_python_function_sizes([source], root=tmp_path, max_lines=3, allowlist={})

    assert errors == ["backend/app/service.py::oversized: 4 lines exceeds max 3"]


def test_grandfathered_function_budget_must_shrink_with_function(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "app" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def legacy():\n    return True\n", encoding="utf-8")

    errors = checker.check_python_function_sizes(
        [source],
        root=tmp_path,
        max_lines=1,
        allowlist={"backend/app/service.py::legacy": 3},
    )

    assert errors == ["backend/app/service.py::legacy: grandfathered budget 3 is stale; current size is 2"]


def test_rejects_decorative_separator_comments(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "frontend" / "src" / "App.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("// ----------------\nexport const app = true;\n", encoding="utf-8")

    errors = checker.check_decorative_comments([source], root=tmp_path)

    assert errors == ["frontend/src/App.tsx:1: decorative separator comment is not allowed"]


def test_allows_section_comments_outside_application_code(tmp_path: Path, checker: ModuleType) -> None:
    source = tmp_path / "backend" / "tests" / "test_service.py"
    source.parent.mkdir(parents=True)
    source.write_text("# ----------------\ndef test_service():\n    pass\n", encoding="utf-8")

    errors = checker.check_decorative_comments([source], root=tmp_path)

    assert errors == []
