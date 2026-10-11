"""Offline manufacturer regeneration preserves namespaces and model-specific silence."""

import importlib.util
import json
from pathlib import Path


def test_offline_generator_keeps_model_override_empty_text_and_manufacturer_precedence(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[4] / "scripts/generate_hms_catalog.py"
    spec = importlib.util.spec_from_file_location("hms_catalog_generator", script)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    root = tmp_path / "output"
    root.mkdir()
    studio = tmp_path / "Studio"
    resources = studio / "resources/hms"
    resources.mkdir(parents=True)
    for model, text in [("093", "Paused by the file."), ("20P", "")]:
        (resources / f"hms_en_{model}.json").write_text(
            json.dumps(
                {
                    "ver": 7,
                    "data": {
                        "device_hms": {"en": [{"ecode": "0300020000010008", "intro": "Manufacturer nozzle fault."}]},
                        "device_error": {"en": [{"ecode": "03008001", "intro": text}]},
                    },
                }
            )
        )
    extra = root / "extra.json"
    extra.write_text(
        json.dumps(
            {"error": {"03008001": "Legacy text must not replace silence.", "0300C012": "Legacy-only nozzle prompt."}}
        )
    )
    output = root / "catalog.json"
    monkeypatch.setattr(generator, "REPO_ROOT", root)
    monkeypatch.setattr(generator, "OUTPUT", output)
    monkeypatch.setattr(generator, "EXTRA", extra)
    monkeypatch.setattr(generator, "_studio_commit", lambda _: "fixture-commit")
    monkeypatch.setattr(generator.sys, "argv", ["generate_hms_catalog.py", str(studio)])
    generator.main()
    first = output.read_bytes()
    generator.main()
    assert output.read_bytes() == first
    catalog = json.loads(first)
    assert catalog["hms"]["0300020000010008"] == "Manufacturer nozzle fault."
    assert catalog["error"]["03008001"] == "Paused by the file."
    assert catalog["error_by_model"]["20P"]["03008001"] == ""
    assert catalog["error"]["0300C012"] == "Legacy-only nozzle prompt."
    assert "03008001" not in catalog["hms"] and "0300020000010008" not in catalog["error"]
    assert catalog["_source"]["bambu_studio_commit"] == "fixture-commit"
