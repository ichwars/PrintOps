"""Windows release staging must reject type errors before creating a bundle."""

import subprocess

import pytest

from installers.windows import build


@pytest.mark.parametrize("typecheck_rc", [0, 7])
def test_frontend_release_rejects_type_errors(tmp_path, monkeypatch, typecheck_rc):
    monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build.shutil, "which", lambda _: "npm")
    dist = tmp_path / "static"

    def run(command, **kwargs):
        if command == ["npm", "run", "typecheck"] and typecheck_rc:
            raise subprocess.CalledProcessError(typecheck_rc, command)
        if command == ["npm", "run", "build"]:
            dist.mkdir()
            (dist / "index.html").write_text("bundled frontend")

    monkeypatch.setattr(build.subprocess, "run", run)
    if typecheck_rc:
        with pytest.raises(subprocess.CalledProcessError):
            build.build_frontend()
        assert not dist.exists()
    else:
        assert build.build_frontend() == dist
        assert (dist / "index.html").read_text() == "bundled frontend"
