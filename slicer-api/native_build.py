"""Fetch pinned sidecar inputs; reject corrupt or foreign executables before use."""

import argparse
import hashlib
import shutil
import struct
import subprocess
import urllib.request
from pathlib import Path

WRAPPER_COMMIT = "4c05506e40a0057db33234837db164143cbf3ad3"
WRAPPER_SHA256 = "911047b9f86d5400c823dc842b700c334376601c9b2943a25860534a58efb05f"
ORCA_VERSION = "2.4.2"


def engine_asset(arch: str) -> dict:
    assets = {
        "arm64": ("_aarch64", 183, "e1a07275a25f176626c55a5df39e91bc4476d8c28ee4a3192ff758e29dd5c3ba"),
        "amd64": ("", 62, "d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd"),
    }
    if arch not in assets:
        raise ValueError(f"Unsupported architecture: {arch}")
    suffix, machine, sha256 = assets[arch]
    name = f"OrcaSlicer_Linux_AppImage_Ubuntu2404{suffix}_V{ORCA_VERSION}.AppImage"
    return {
        "url": f"https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v{ORCA_VERSION}/{name}",
        "sha256": sha256,
        "machine": machine,
    }


def download_verified(url: str, sha256: str, target: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=120) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        with target.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != sha256:
            raise ValueError(f"SHA256 mismatch for {url}: {actual}")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    print(f"Verified SHA256 {actual}: {url}", flush=True)


def verify_elf(path: Path, arch: str) -> None:
    expected = engine_asset(arch)["machine"]
    with path.open("rb") as source:
        header = source.read(64)
    if len(header) < 64 or header[:6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Expected a 64-bit little-endian ELF: {path}")
    machine = struct.unpack_from("<H", header, 18)[0]
    if machine != expected:
        raise ValueError(f"ELF architecture mismatch: {path}: {machine}, expected {expected} ({arch})")
    print(f"Verified ELF {arch} (e_machine={machine}): {path}", flush=True)


def install_engine(arch: str, root: Path) -> None:
    asset = engine_asset(arch)
    image = root / "orca.AppImage"
    download_verified(asset["url"], asset["sha256"], image)
    verify_elf(image, arch)
    image.chmod(0o755)
    # Extraction runs only a verified native runtime; FUSE is not required.
    subprocess.run([str(image.resolve()), "--appimage-extract"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    verify_elf(root / "squashfs-root/bin/orca-slicer", arch)
    image.unlink()


def install_wrapper(root: Path) -> None:
    archive = root / "wrapper.tar.gz"
    url = f"https://codeload.github.com/maziggy/orca-slicer-api/tar.gz/{WRAPPER_COMMIT}"
    download_verified(url, WRAPPER_SHA256, archive)
    source = root / "wrapper"
    source.mkdir()
    subprocess.run(["tar", "-xzf", str(archive.resolve()), "--strip-components=1", "-C", str(source)], check=True)
    archive.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["engine", "wrapper", "verify-elf"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--arch", default="")
    args = parser.parse_args()
    if args.operation == "verify-elf":
        verify_elf(args.path, args.arch)
    else:
        args.path.mkdir(parents=True, exist_ok=True)
        if args.operation == "engine":
            install_engine(args.arch, args.path)
        else:
            install_wrapper(args.path)
