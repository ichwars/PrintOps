#!/usr/bin/env python3
"""Verify and stage the pinned veraPDF CLI for offline PrintOps use.

This is a packaging tool, never an application-startup downloader.  It accepts
only the source URLs and cryptographic receipts recorded in the repository
manifest, verifies both SHA-256 and the detached OpenPGP signature, performs a
CLI-only unattended install, and rejects an unexpected runtime version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = REPO_ROOT / "backend" / "app" / "resources" / "pdf"
MANIFEST_PATH = RESOURCE_DIR / "runtime-manifest.json"
ALLOWED_DOWNLOAD_HOST = "software.verapdf.org"


class VendorError(RuntimeError):
    """Raised when a runtime cannot be proven safe and reproducible."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual.lower() != expected.lower():
        raise VendorError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def _load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in ("version", "url", "signature_url", "sha256", "signature_sha256", "signing_fingerprint"):
        if not manifest.get("verapdf", {}).get(key):
            raise VendorError(f"runtime manifest is missing verapdf.{key}")
    return manifest


def _download(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_DOWNLOAD_HOST:
        raise VendorError(f"refusing non-pinned veraPDF source: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "PrintOps-runtime-vendor/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - host checked above
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != ALLOWED_DOWNLOAD_HOST:
                raise VendorError(f"refusing redirected veraPDF source: {response.geturl()}")
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _obtain(url: str, destination: Path, expected_hash: str, label: str) -> Path:
    if not destination.exists():
        _download(url, destination)
    try:
        _require_hash(destination, expected_hash, label)
    except VendorError:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _verify_signature(archive: Path, signature: Path, manifest: dict) -> None:
    verapdf = manifest["verapdf"]
    key = RESOURCE_DIR / verapdf["signing_key"]
    _require_hash(key, verapdf["signing_key_sha256"], "veraPDF signing key")
    candidates = [
        shutil.which("gpg"),
        shutil.which("gpg.exe"),
        shutil.which("gpg2"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "gpg.exe",
    ]
    gpg = next((str(candidate) for candidate in candidates if candidate and Path(candidate).is_file()), None)
    if not gpg:
        raise VendorError("GnuPG is required to verify the veraPDF release signature")

    expected = verapdf["signing_fingerprint"].replace(" ", "").upper()
    def gpg_path(value: str | Path) -> str:
        resolved = str(Path(value).resolve())
        if os.name == "nt" and "\\Git\\usr\\bin\\" in gpg:
            drive, tail = os.path.splitdrive(resolved)
            return f"/{drive[0].lower()}{tail.replace(chr(92), '/')}"
        return resolved

    with tempfile.TemporaryDirectory(prefix="printops-verapdf-gpg-") as home:
        base = [gpg, "--homedir", gpg_path(home), "--batch", "--no-tty"]
        subprocess.run([*base, "--import", gpg_path(key)], check=True, capture_output=True, text=True)
        listed = subprocess.run(
            [*base, "--with-colons", "--fingerprint", "--list-keys"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        fingerprints = {
            fields[9].upper()
            for line in listed.splitlines()
            if (fields := line.split(":"))[0] == "fpr" and len(fields) > 9
        }
        if expected not in fingerprints:
            raise VendorError(f"veraPDF signing key fingerprint mismatch: expected {expected}")
        subprocess.run(
            [*base, "--status-fd", "1", "--verify", gpg_path(signature), gpg_path(archive)],
            check=True,
            capture_output=True,
            text=True,
        )


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise VendorError(f"unsafe path in veraPDF installer archive: {member.filename}")
        bundle.extractall(destination)


def _automation_file(path: Path, install_path: Path) -> None:
    content = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<AutomatedInstallation langpack="eng">
  <com.izforge.izpack.panels.htmlhello.HTMLHelloPanel id="welcome"/>
  <com.izforge.izpack.panels.target.TargetPanel id="install_dir">
    <installpath>{escape(str(install_path))}</installpath>
  </com.izforge.izpack.panels.target.TargetPanel>
  <com.izforge.izpack.panels.packs.PacksPanel id="sdk_pack_select">
    <selected><pack index="1"/></selected>
  </com.izforge.izpack.panels.packs.PacksPanel>
  <com.izforge.izpack.panels.install.InstallPanel id="install"/>
  <com.izforge.izpack.panels.finish.FinishPanel id="finish"/>
</AutomatedInstallation>
"""
    path.write_text(content, encoding="utf-8")


def _cli_command(cli: Path) -> list[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(cli), "--version"]
    return [str(cli), "--version"]


def _stage_cli(archive: Path, destination: Path, expected_version: str) -> Path:
    java = shutil.which("java")
    if not java:
        raise VendorError("a Java runtime is required to install veraPDF")
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="printops-verapdf-install-") as working:
        working_path = Path(working)
        _safe_extract(archive, working_path)
        jars = list(working_path.rglob("verapdf-izpack-installer-*.jar"))
        if len(jars) != 1:
            raise VendorError(f"expected one veraPDF installer JAR, found {len(jars)}")
        automation = working_path / "cli-only.xml"
        _automation_file(automation, destination.resolve())
        subprocess.run([java, "-jar", str(jars[0]), str(automation)], check=True)

    # The upstream IzPack descriptor preselects GUI and documentation even in
    # automated mode.  Reduce the verified installation to its CLI payload so
    # production packages do not ship or expose an unused desktop application.
    for relative in (
        "verapdf-gui",
        "verapdf-gui.bat",
        "bin/gui-1.30.2.jar",
        "documents",
        "Uninstaller",
        ".installationinformation",
    ):
        candidate = destination / relative
        if candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink(missing_ok=True)

    cli = destination / ("verapdf.bat" if os.name == "nt" else "verapdf")
    if not cli.exists():
        raise VendorError(f"veraPDF CLI was not installed at {cli}")
    gui_files = [p for p in destination.rglob("*") if p.is_file() and "gui" in p.name.lower()]
    if gui_files:
        raise VendorError(f"CLI-only staging unexpectedly contains GUI files: {gui_files[0].name}")
    result = subprocess.run(_cli_command(cli), check=True, capture_output=True, text=True)
    reported = f"{result.stdout}\n{result.stderr}"
    if expected_version not in reported:
        raise VendorError(f"veraPDF version mismatch: expected {expected_version}, got {reported.strip()!r}")
    return cli


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True, help="clean directory that receives the CLI")
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / ".cache" / "pdf-runtime")
    parser.add_argument("--verify-only", action="store_true", help="verify downloads and signature without installing")
    args = parser.parse_args()

    try:
        manifest = _load_manifest()
        verapdf = manifest["verapdf"]
        archive = _obtain(
            verapdf["url"],
            args.cache_dir / Path(urllib.parse.urlparse(verapdf["url"]).path).name,
            verapdf["sha256"],
            "veraPDF installer",
        )
        signature = _obtain(
            verapdf["signature_url"],
            args.cache_dir / Path(urllib.parse.urlparse(verapdf["signature_url"]).path).name,
            verapdf["signature_sha256"],
            "veraPDF signature",
        )
        _verify_signature(archive, signature, manifest)
        if args.verify_only:
            print(f"verified veraPDF {verapdf['version']} ({archive.name})")
            return 0
        cli = _stage_cli(archive, args.destination, verapdf["version"])
        print(f"staged verified veraPDF {verapdf['version']} CLI at {cli}")
        return 0
    except (OSError, subprocess.CalledProcessError, VendorError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
