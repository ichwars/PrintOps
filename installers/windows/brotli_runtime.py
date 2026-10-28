"""Patch the separately bundled WeasyPrint Brotli copies using verified artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

WHEEL_URL = (
    "https://files.pythonhosted.org/packages/24/5e/"
    "80cd38322263da5e92ea4935423f1d3cfa2509201673dce77b772c47b997/"
    "brotli-1.2.1-cp314-cp314-win_amd64.whl"
)
WHEEL_SHA256 = "972a2e19dbaab47d0aa77c1d07f71c930bdc53538f2b33decc905e92a4be5cbd"
DLL_URL = "https://mirror.msys2.org/mingw/ucrt64/mingw-w64-ucrt-x86_64-brotli-1.2.1-1-any.pkg.tar.zst"
DLL_SHA256 = "e3257d4303fc0aca4c64f702d4c8cd766a321351c5e61927631c30bfdf2e7536"
PYD = "_brotli.cp314-win_amd64.pyd"
DLLS = ("libbrotlicommon.dll", "libbrotlidec.dll")


def stage_brotli_runtime(
    internal: Path,
    downloads: Path,
    download_verified: Callable[[str, Path, str], Path],
    *,
    verify_only: bool = False,
) -> None:
    """Keep WeasyPrint 70.0/CPython 3.14 while fixing its embedded decoders."""
    wheel = download_verified(WHEEL_URL, downloads / "brotli-1.2.1-cp314-cp314-win_amd64.whl", WHEEL_SHA256)
    archive = download_verified(DLL_URL, downloads / "brotli-ucrt64-1.2.1.pkg.tar.zst", DLL_SHA256)
    if verify_only:
        return
    for name in (PYD, *DLLS):
        if not (internal / name).is_file():
            raise RuntimeError(f"Unsupported WeasyPrint bundle: {name} missing")
    with zipfile.ZipFile(wheel) as source:
        replacements = {PYD: source.read(PYD)}
    # Windows ships bsdtar with zstd support. Stream only the two known members;
    # do not extract package-supplied paths or executables into the runtime.
    tar = str(Path(os.environ["SYSTEMROOT"]) / "System32" / "tar.exe") if os.name == "nt" else "tar"
    for name in DLLS:
        replacements[name] = subprocess.run(
            [tar, "-xOf", str(archive), f"ucrt64/bin/{name}"],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
    if any(not data.startswith(b"MZ") or len(data) > 5_000_000 for data in replacements.values()):
        raise RuntimeError("Invalid Brotli runtime binary")
    for name, data in replacements.items():
        (internal / name).write_bytes(data)
    if os.name == "nt":
        # A child process releases loaded DLLs before installer staging continues.
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import ctypes, os, sys; "
                "directory = os.add_dll_directory(sys.argv[1]); "
                "decoder = ctypes.WinDLL(os.path.join(sys.argv[1], 'libbrotlidec.dll')); "
                "decoder.BrotliDecoderVersion.restype = ctypes.c_uint; "
                "assert decoder.BrotliDecoderVersion() == 0x1002001, 'Brotli DLL version mismatch'",
                str(internal.resolve()),
            ],
            check=True,
            timeout=30,
        )
