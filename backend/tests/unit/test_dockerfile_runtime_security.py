from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_runtime_image_removes_python_package_manager_tooling() -> None:
    dockerfile_path = ROOT / "Dockerfile"
    if not dockerfile_path.exists():
        pytest.skip("Dockerfile is not copied into the backend Docker test image")

    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert "'setuptools>=83.0.0'" in dockerfile
    assert "python -m pip uninstall -y pip setuptools wheel" in dockerfile
    assert "/usr/local/lib/python*/site-packages/pip*" in dockerfile
    assert "/usr/local/lib/python*/site-packages/setuptools*" in dockerfile
    assert "/usr/local/bin/pip3.*" in dockerfile
