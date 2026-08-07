from pathlib import Path

from tools.check_dependency_boundaries import (
    check_dependency_boundaries,
    included_requirement_files,
    requirement_names,
)


def _write_dependency_files(root: Path) -> None:
    (root / "requirements.txt").write_text(
        "fastapi>=1\npillow[image]>=12; python_version >= '3.10'\n", encoding="utf-8"
    )
    (root / "requirements-dev.txt").write_text("-r requirements.txt\npytest>=9\nruff==1\n", encoding="utf-8")
    (root / "requirements.lock.txt").write_text("fastapi==1\npillow==12\n", encoding="utf-8")
    (root / "requirements-dev.lock.txt").write_text("fastapi==1\npillow==12\npytest==9\nruff==1\n", encoding="utf-8")


def test_repository_dependency_boundaries_are_valid():
    root = Path(__file__).resolve().parents[3]

    assert check_dependency_boundaries(root) == []


def test_requirement_names_support_extras_markers_and_lock_continuations(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "# comment\nPy_Test.Plugin[extra]>=1; python_version >= '3.10'\n    --hash=sha256:abc\n-r base.txt\n",
        encoding="utf-8",
    )

    assert requirement_names(requirements) == {"py-test-plugin"}


def test_requirement_includes_support_short_and_long_forms(tmp_path):
    requirements = tmp_path / "requirements-dev.txt"
    requirements.write_text("-r requirements.txt\n--requirement=constraints.txt\n", encoding="utf-8")

    assert included_requirement_files(requirements) == {"constraints.txt", "requirements.txt"}


def test_rejects_development_tool_in_runtime_input(tmp_path):
    _write_dependency_files(tmp_path)
    (tmp_path / "requirements.txt").write_text("fastapi>=1\npytest>=9\n", encoding="utf-8")
    (tmp_path / "requirements.lock.txt").write_text("fastapi==1\npytest==9\n", encoding="utf-8")

    errors = check_dependency_boundaries(tmp_path)

    assert "requirements.txt contains development-only packages: pytest" in errors
    assert "requirements.lock.txt contains development-only packages: pytest" in errors


def test_rejects_development_tool_only_in_runtime_lock(tmp_path):
    _write_dependency_files(tmp_path)
    (tmp_path / "requirements.lock.txt").write_text("fastapi==1\npillow==12\nruff==1\n", encoding="utf-8")

    assert "requirements.lock.txt contains development-only packages: ruff" in check_dependency_boundaries(tmp_path)


def test_requires_runtime_include_in_development_input(tmp_path):
    _write_dependency_files(tmp_path)
    (tmp_path / "requirements-dev.txt").write_text("pytest>=9\nruff==1\n", encoding="utf-8")

    assert "requirements-dev.txt must include requirements.txt with -r or --requirement" in check_dependency_boundaries(
        tmp_path
    )


def test_rejects_stale_runtime_lock(tmp_path):
    _write_dependency_files(tmp_path)
    (tmp_path / "requirements.lock.txt").write_text("fastapi==1\n", encoding="utf-8")

    assert "requirements.lock.txt is missing direct runtime packages: pillow" in check_dependency_boundaries(tmp_path)


def test_rejects_stale_development_lock(tmp_path):
    _write_dependency_files(tmp_path)
    (tmp_path / "requirements-dev.lock.txt").write_text("fastapi==1\npillow==12\npytest==9\n", encoding="utf-8")

    assert "requirements-dev.lock.txt is missing direct packages: ruff" in check_dependency_boundaries(tmp_path)
