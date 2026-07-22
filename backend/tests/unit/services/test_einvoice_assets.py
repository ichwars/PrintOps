import hashlib
import json
from pathlib import Path

RESOURCE_ROOT = Path(__file__).parents[3] / "app" / "resources" / "einvoice"


def load_manifest() -> dict[str, object]:
    return json.loads((RESOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_vendored_einvoice_assets_match_manifest() -> None:
    manifest = load_manifest()

    assert manifest["en16931"]["version"] == "1.3.16"
    assert manifest["xrechnung"]["version"] == "3.0.2"
    assert manifest["xrechnung"]["bundle_date"] == "2026-01-31"
    assert manifest["zugferd"]["version"] == "2.5"

    files = manifest["files"]
    assert files
    manifested_paths = {item["path"] for item in files}
    for item in files:
        path = RESOURCE_ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert item["source"] in {"en16931", "xrechnung", "zugferd"}
        assert item["syntax"] in {"cii-d16b", "cii-d22b", "ubl-2.1", "n/a"}
        assert item["profile"] in {"en16931", "xrechnung", "license"}

    actual_paths = {
        path.relative_to(RESOURCE_ROOT).as_posix()
        for path in RESOURCE_ROOT.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert manifested_paths == actual_paths
    assert any(path.endswith(".sch") for path in manifested_paths)
    assert any(path.endswith(".xsd") for path in manifested_paths)
    assert any(path.endswith((".xsl", ".xslt")) for path in manifested_paths)
    assert any("codedb.xml" in path for path in manifested_paths)
    assert any("examples/" in path for path in manifested_paths)
    assert not any(path.endswith((".pdf", ".xlsx", ".jpg", ".svg")) for path in manifested_paths)
