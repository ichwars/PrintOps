"""Regression coverage for content-based sliced 3MF detection (issue #132)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from backend.app.api.routes.library import save_3mf_bytes_to_library
from backend.app.utils.library_files import classify_file_type, is_sliced_file
from backend.app.utils.threemf_tools import carries_gcode, names_carry_gcode


def _write_3mf(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    return path


def test_plain_named_sliced_3mf_is_classified_from_its_contents(tmp_path):
    sliced = _write_3mf(
        tmp_path / "Labyrinth - Plate 3.3mf",
        ["3D/3dmodel.model", "Metadata/plate_3.gcode"],
    )

    assert classify_file_type(sliced.name, sliced) == "gcode.3mf"


def test_multi_plate_and_unusual_gcode_locations_are_printable():
    assert names_carry_gcode(
        [
            "3D/3dmodel.model",
            "Metadata/plate_7.gcode",
            "Metadata/plate_2.gcode",
        ]
    )
    assert names_carry_gcode(["3D/3dmodel.model", "vendor/output.gcode"])


def test_source_only_and_malformed_3mf_stay_unprintable(tmp_path):
    source = _write_3mf(
        tmp_path / "source.3mf",
        ["3D/3dmodel.model", "Metadata/project_settings.config"],
    )
    malformed = tmp_path / "broken.3mf"
    malformed.write_bytes(b"PK\x03\x04not-a-valid-zip")

    assert carries_gcode(source) is False
    assert carries_gcode(malformed) is False
    assert carries_gcode(tmp_path / "missing.3mf") is False
    assert classify_file_type(source.name, source) == "3mf"
    assert classify_file_type(malformed.name, malformed) == "3mf"


def test_explicit_sliced_filename_does_not_require_readable_bytes(tmp_path):
    assert classify_file_type("plate.GCODE.3MF", tmp_path / "missing.3mf") == "gcode.3mf"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("model.stl", "stl"), ("preview.png", "png"), ("README", "unknown"), ("model.gcode", "gcode")],
)
def test_only_ambiguous_3mf_files_are_inspected(filename, expected, tmp_path):
    sliced = _write_3mf(tmp_path / "sliced.3mf", ["Metadata/plate_1.gcode"])

    assert classify_file_type(filename, sliced) == expected


def test_archive_capabilities_and_library_classification_share_one_predicate(tmp_path):
    from backend.app.api.routes.archives import names_carry_gcode as archive_predicate

    sliced = _write_3mf(tmp_path / "plain-name.3mf", ["Metadata/plate_8.gcode"])
    with zipfile.ZipFile(sliced) as archive:
        names = archive.namelist()

    assert archive_predicate(names) is True
    assert classify_file_type(sliced.name, sliced) == "gcode.3mf"


def test_queue_gate_trusts_content_classification_over_plain_filename():
    assert is_sliced_file("Labyrinth - Plate 3.3mf", "gcode.3mf") is True
    assert is_sliced_file("Labyrinth source.3mf", "3mf") is False


@pytest.mark.asyncio
async def test_in_process_import_keeps_content_type_and_provenance(db_session, tmp_path, monkeypatch):
    from backend.app.api.routes import library as library_routes

    source = _write_3mf(tmp_path / "cloud-export.3mf", ["Metadata/plate_5.gcode"])
    monkeypatch.setattr(library_routes.app_settings, "base_dir", tmp_path)
    monkeypatch.setattr(library_routes.app_settings, "archive_dir", tmp_path / "archive")

    row, was_existing = await save_3mf_bytes_to_library(
        db_session,
        file_bytes=source.read_bytes(),
        filename="cloud-export.3mf",
        source_type="makerworld",
        source_url="https://example.invalid/model/132",
    )

    assert was_existing is False
    assert row.file_type == "gcode.3mf"
    assert row.source_type == "makerworld"
    assert row.source_url == "https://example.invalid/model/132"
