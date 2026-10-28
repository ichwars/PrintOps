"""All embedded decoder copies must be verified before the Windows build proceeds."""

import subprocess
import zipfile
from types import SimpleNamespace

import pytest

from installers.windows import brotli_runtime, build


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    internal = tmp_path / "internal"
    internal.mkdir()
    for name in (brotli_runtime.PYD, *brotli_runtime.DLLS):
        (internal / name).write_bytes(b"old decoder")
    wheel = tmp_path / "brotli.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr(brotli_runtime.PYD, b"MZfixed Python decoder")
        z.writestr("ignored.exe", b"do not stage")
    archive = tmp_path / "brotli.pkg.tar.zst"
    archive.write_bytes(b"verified fixture")
    monkeypatch.setattr(
        brotli_runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"MZfixed native decoder")
    )

    def download(url, _target, digest):
        if url == brotli_runtime.WHEEL_URL:
            assert digest == brotli_runtime.WHEEL_SHA256
            return wheel
        assert url == brotli_runtime.DLL_URL and digest == brotli_runtime.DLL_SHA256
        return archive

    return internal, download


def test_replaces_python_and_native_decoders_and_no_other_members(bundle, tmp_path):
    internal, download = bundle
    brotli_runtime.stage_brotli_runtime(internal, tmp_path, download)
    assert (internal / brotli_runtime.PYD).read_bytes() == b"MZfixed Python decoder"
    assert all((internal / name).read_bytes() == b"MZfixed native decoder" for name in brotli_runtime.DLLS)
    assert not (internal / "ignored.exe").exists()


def test_unknown_upstream_bundle_layout_stops_before_patch(bundle, tmp_path):
    internal, download = bundle
    (internal / brotli_runtime.PYD).unlink()
    with pytest.raises(RuntimeError, match="Unsupported WeasyPrint bundle"):
        brotli_runtime.stage_brotli_runtime(internal, tmp_path, download)
    assert (internal / brotli_runtime.DLLS[0]).read_bytes() == b"old decoder"


def test_failed_native_extraction_does_not_partially_replace_bundle(bundle, tmp_path, monkeypatch):
    internal, download = bundle

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "tar")

    monkeypatch.setattr(brotli_runtime.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        brotli_runtime.stage_brotli_runtime(internal, tmp_path, download)
    assert all((internal / name).read_bytes() == b"old decoder" for name in (brotli_runtime.PYD, *brotli_runtime.DLLS))


def test_unverified_download_is_rejected_and_removed(bundle, tmp_path, monkeypatch):
    internal, _ = bundle
    artifact = tmp_path / "tampered.whl"
    artifact.write_bytes(b"tampered")
    monkeypatch.setattr(build, "download", lambda *_: artifact)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        brotli_runtime.stage_brotli_runtime(internal, tmp_path, build.download_verified)
    assert not artifact.exists()
    assert (internal / brotli_runtime.PYD).read_bytes() == b"old decoder"


def test_verify_only_checks_archives_without_touching_bundle(bundle, tmp_path):
    internal, download = bundle
    brotli_runtime.stage_brotli_runtime(internal, tmp_path, download, verify_only=True)
    assert (internal / brotli_runtime.PYD).read_bytes() == b"old decoder"
