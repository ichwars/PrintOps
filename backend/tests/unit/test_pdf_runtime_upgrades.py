"""Runtime replacement preserves a working installation until verification succeeds."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import vendor_pdf_runtime as vendor


def _old_runtime(tmp_path):
    runtime = tmp_path / "runtime" / "verapdf"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "cli-1.30.2.jar").write_bytes(b"old runtime")
    return runtime


@pytest.mark.parametrize("keep_backup", [False, True])
def test_verified_runtime_replaces_old_jars(tmp_path, monkeypatch, keep_backup):
    runtime = _old_runtime(tmp_path)
    backup = tmp_path / "previous" if keep_backup else None

    def install(_archive, candidate, _version):
        assert (runtime / "bin" / "cli-1.30.2.jar").exists()
        (candidate / "bin").mkdir(parents=True)
        (candidate / "bin" / "cli-1.30.3.jar").write_bytes(b"verified runtime")
        cli = candidate / "verapdf"
        cli.write_text("verified launcher")
        return cli

    monkeypatch.setattr(vendor, "_install_cli", install)
    cli = vendor._stage_cli(Path("verified.zip"), runtime, "1.30.3", backup)
    assert cli == runtime / "verapdf"
    assert (runtime / "bin" / "cli-1.30.3.jar").exists()
    assert not (runtime / "bin" / "cli-1.30.2.jar").exists()
    if backup:
        assert (backup / "bin" / "cli-1.30.2.jar").exists()


def test_failed_runtime_verification_preserves_installed_runtime(tmp_path, monkeypatch):
    runtime = _old_runtime(tmp_path)

    def fail(*_):
        raise vendor.VendorError("version mismatch")

    monkeypatch.setattr(vendor, "_install_cli", fail)
    with pytest.raises(vendor.VendorError, match="version mismatch"):
        vendor._stage_cli(Path("verified.zip"), runtime, "1.30.3")
    assert (runtime / "bin" / "cli-1.30.2.jar").read_bytes() == b"old runtime"
    assert list(runtime.parent.iterdir()) == [runtime]


@pytest.mark.parametrize("script", ["update.sh", "update_macos.sh"])
@pytest.mark.parametrize("failure", ["none", "verification", "restart"])
def test_native_updater_refreshes_runtime_and_rolls_it_back(tmp_path, script, failure):
    install = tmp_path / "install"
    install.mkdir()
    (install / ".git").mkdir()
    (install / "scripts").mkdir()
    (install / "requirements.lock.txt").touch()
    _old_runtime(install)
    venv = install / "venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(sys.executable)
    tools = tmp_path / "tools"
    tools.mkdir()
    log = tmp_path / "commands"
    stub = f"""#!{sys.executable}
import os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with Path(os.environ["TEST_COMMAND_LOG"]).open("a") as out:
    out.write(name + " " + " ".join(args) + "\\n")
if name == "git":
    if args[0] == "diff": sys.exit(1)
    if args[0] == "rev-parse": print("old1234" if args[-1] == "HEAD" else "new5678")
elif name == "systemctl" and args[0] == "show": print("loaded")
if name in ("systemctl", "launchctl") and args[0] in ("start", "load"):
    marker = Path(os.environ["TEST_RESTART_MARKER"])
    if os.environ["TEST_FAILURE"] == "restart" and not marker.exists():
        marker.touch()
        sys.exit(1)
"""
    for name in ("git", "systemctl", "launchctl", "curl"):
        path = tools / name
        path.write_text(stub)
        path.chmod(0o755)
    (venv / "pip").write_text("#!/bin/sh\nexit 0\n")
    (venv / "pip").chmod(0o755)
    # The updater runs the real shared replacement function with a fixture
    # installer; no network, host service or system runtime is touched.
    (install / "scripts/vendor_pdf_runtime.py").write_text(
        f"""import os, sys
from pathlib import Path
sys.path.insert(0, {str(vendor.REPO_ROOT)!r})
from scripts import vendor_pdf_runtime as vendor
def install(archive, candidate, version):
    if os.environ["TEST_FAILURE"] == "verification":
        raise vendor.VendorError("signature rejected")
    (candidate / "bin").mkdir(parents=True)
    (candidate / "bin/cli-1.30.3.jar").write_bytes(b"new runtime")
    return candidate / "verapdf"
vendor._install_cli = install
args = sys.argv[1:]
vendor._stage_cli(Path("fixture.zip"), Path(args[args.index("--destination") + 1]),
                  "1.30.3", Path(args[args.index("--backup-dir") + 1]))
"""
    )
    source = (vendor.REPO_ROOT / "install" / script).read_text()
    # Exercise Linux behavior without requiring root: every privileged tool
    # is a stub and INSTALL_DIR is a disposable fixture.
    source = source.replace('[ "${EUID:-$(id -u)}" -eq 0 ] || die "Run as root (or with sudo)."', ":")
    updater = tmp_path / script
    updater.write_text(source)
    plist = tmp_path / "app.plist"
    plist.touch()
    result = subprocess.run(
        ["bash", str(updater)],
        input="y\n",
        text=True,
        capture_output=True,
        timeout=20,
        env={
            **os.environ,
            "PATH": f"{tools}:{os.environ['PATH']}",
            "INSTALL_DIR": str(install),
            "PLIST_PATH": str(plist),
            "BACKUP_MODE": "skip",
            "BRANCH": "main",
            "FORCE": "1",
            "TEST_COMMAND_LOG": str(log),
            "TEST_RESTART_MARKER": str(tmp_path / "restarted"),
            "TEST_FAILURE": failure,
        },
    )
    runtime = install / "runtime/verapdf/bin"
    if failure == "none":
        assert result.returncode == 0, result.stderr
        assert [path.name for path in runtime.iterdir()] == ["cli-1.30.3.jar"]
    else:
        assert result.returncode != 0
        assert [path.name for path in runtime.iterdir()] == ["cli-1.30.2.jar"]
        assert "git reset --hard old1234" in log.read_text()
    assert not list((install / "runtime").glob(".verapdf-*"))


def test_failed_runtime_swap_restores_installed_runtime(tmp_path, monkeypatch):
    runtime = _old_runtime(tmp_path)

    def install(_archive, candidate, _version):
        candidate.mkdir()
        return candidate / "verapdf"

    rename = Path.rename

    def fail_candidate(path, target):
        if path.name == "candidate":
            raise OSError("replacement failed")
        return rename(path, target)

    monkeypatch.setattr(vendor, "_install_cli", install)
    monkeypatch.setattr(Path, "rename", fail_candidate)
    with pytest.raises(OSError, match="replacement failed"):
        vendor._stage_cli(Path("verified.zip"), runtime, "1.30.3")
    assert (runtime / "bin" / "cli-1.30.2.jar").read_bytes() == b"old runtime"
