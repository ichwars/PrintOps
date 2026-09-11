"""Portable installer tests for PrintOps' stable Windows PDF runtime path."""

from __future__ import annotations

import zipfile

import pytest

from installers.windows import build


@pytest.mark.parametrize("include_executable", [True, False])
def test_windows_onedir_runtime_is_staged_with_native_libraries(tmp_path, monkeypatch, include_executable):
    weasy = tmp_path / "weasy.zip"
    with zipfile.ZipFile(weasy, "w") as archive:
        archive.writestr("onedir/weasyprint/_internal/libpango-1.0-0.dll", b"native fixture")
        if include_executable:
            archive.writestr("onedir/weasyprint/weasyprint.exe", b"executable fixture")
    jre = tmp_path / "jre.zip"
    with zipfile.ZipFile(jre, "w") as archive:
        archive.writestr("temurin/bin/java.exe", b"java fixture")
    monkeypatch.setattr(build, "STAGING", tmp_path / "staging")
    monkeypatch.setattr(build, "DOWNLOADS", tmp_path / "downloads")
    monkeypatch.setattr(
        build, "download_verified", lambda url, *_: weasy if url == build.WEASYPRINT_RUNTIME_URL else jre
    )
    commands = []
    monkeypatch.setattr(build.subprocess, "run", lambda command, **_: commands.append(command))

    if not include_executable:
        with pytest.raises(RuntimeError, match="official WeasyPrint executable missing"):
            build.stage_document_runtimes(tmp_path / "python")
        assert commands == []
        return

    build.stage_document_runtimes(tmp_path / "python")
    runtime = build.STAGING / "runtime"
    assert (runtime / "weasyprint/dist/weasyprint.exe").read_bytes() == b"executable fixture"
    assert (runtime / "weasyprint/dist/_internal/libpango-1.0-0.dll").read_bytes() == b"native fixture"
    assert not (runtime / "weasyprint/onedir").exists()
    assert (runtime / "java/bin/java.exe").read_bytes() == b"java fixture"
    assert len(commands) == 1
    assert commands[0][1] == str(build.REPO_ROOT / "scripts/vendor_pdf_runtime.py")
