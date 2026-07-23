"""Pinned, offline PDF rendering runtime contract."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
RESOURCE_DIR = REPO_ROOT / "backend" / "app" / "resources" / "pdf"


def test_python_pdf_packages_are_exactly_pinned() -> None:
    assert version("weasyprint") == "69.0"
    assert version("pikepdf") == "10.10.0"
    assert version("fonttools") == "4.63.0"


def test_verapdf_runtime_manifest_is_pinned_and_signed() -> None:
    manifest = json.loads((RESOURCE_DIR / "runtime-manifest.json").read_text(encoding="utf-8"))
    verapdf = manifest["verapdf"]

    assert verapdf["version"] == "1.30.2"
    assert verapdf["url"] == (
        "https://software.verapdf.org/rel/1.30/"
        "verapdf-greenfield-1.30.2-installer.zip"
    )
    assert verapdf["signature_url"] == f'{verapdf["url"]}.asc'
    assert verapdf["signing_fingerprint"] == "13DD102B4DD69354D12DE5A83184863278B17FE7"
    assert len(verapdf["sha256"]) == 64


def test_srgb_output_intent_matches_manifest_receipt() -> None:
    manifest = json.loads((RESOURCE_DIR / "runtime-manifest.json").read_text(encoding="utf-8"))
    profile = RESOURCE_DIR / manifest["srgb"]["filename"]
    content = profile.read_bytes()

    assert len(content) >= 3_000
    assert hashlib.sha256(content).hexdigest() == manifest["srgb"]["sha256"]
    assert manifest["srgb"]["color_space"] == "RGB"
