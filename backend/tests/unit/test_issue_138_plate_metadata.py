"""Regression coverage for plate-specific archive metadata (issue #138)."""

import json
import zipfile

import pytest

from backend.app.services.archive import ThreeMFParser
from backend.app.utils.threemf_tools import (
    bed_temperature_from_config,
    extract_bed_temperature_from_3mf,
    extract_layer_height_from_3mf,
)

BED_KEYS = {
    "Cool Plate": "cool_plate_temp_initial_layer",
    "Engineering Plate": "eng_plate_temp_initial_layer",
    "High Temp Plate": "hot_plate_temp_initial_layer",
    "Textured PEI Plate": "textured_plate_temp_initial_layer",
    "Supertack Plate": "supertack_plate_temp_initial_layer",
}

BED_ALIASES = {
    "Smooth PEI Plate": "hot_plate_temp_initial_layer",
    "Cool Plate (SuperTack)": "supertack_plate_temp_initial_layer",
    "Cool Plate SuperTack": "supertack_plate_temp_initial_layer",
    "textured_pei": "textured_plate_temp_initial_layer",
    "TEXTURED PEI PLATE": "textured_plate_temp_initial_layer",
}


def _write_multi_plate_3mf(path) -> None:
    project = {
        "layer_height": ["0.20"],
        "curr_bed_type": "Cool Plate",
        "cool_plate_temp_initial_layer": ["35", "40"],
        "textured_plate_temp_initial_layer": ["65", "70"],
    }
    slice_info = """<config>
      <plate><metadata key="index" value="1"/><metadata key="curr_bed_type" value="Cool Plate"/><filament id="1" used_g="8" type="PLA" color="#ffffff"/></plate>
      <plate><metadata key="index" value="2"/><metadata key="curr_bed_type" value="Textured PEI Plate"/><filament id="2" used_g="9" type="ABS" color="#000000"/></plate>
    </config>"""
    padding = "; " + ("padding" * 900) + "\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps(project))
        archive.writestr("Metadata/slice_info.config", slice_info)
        archive.writestr(
            "Metadata/plate_1.gcode",
            "; total layer number: 100\n" + padding + "; layer_height = 0.20\n",
        )
        archive.writestr(
            "Metadata/plate_2.gcode",
            "; total layer number: 500\n" + padding + "; layer_height = 0.08\n",
        )


def test_parser_uses_the_plate_that_actually_printed(tmp_path):
    path = tmp_path / "multi.3mf"
    _write_multi_plate_3mf(path)

    metadata = ThreeMFParser(path, plate_number=2).parse()

    assert metadata["layer_height"] == 0.08
    assert metadata["total_layers"] == 500
    assert metadata["bed_type"] == "Textured PEI Plate"
    assert metadata["bed_temperature"] == 70


@pytest.mark.parametrize("bed_type,key", BED_KEYS.items())
def test_bambu_bed_temperature_follows_curr_bed_type(bed_type, key):
    config = {
        "curr_bed_type": bed_type,
        key: ["0", "55", "60"],
        "bed_temperature_initial_layer": ["25"],
    }

    assert bed_temperature_from_config(config) == 60


@pytest.mark.parametrize("bed_type,key", BED_ALIASES.items())
def test_supported_bed_aliases_are_normalized(bed_type, key):
    assert bed_temperature_from_config({"curr_bed_type": bed_type, key: ["58"]}) == 58


def test_selected_plate_uses_only_its_filament_temperature_slot(tmp_path):
    path = tmp_path / "different-materials.3mf"
    _write_multi_plate_3mf(path)

    assert extract_bed_temperature_from_3mf(path, 1) == 35
    assert extract_bed_temperature_from_3mf(path, 2) == 70


def test_single_exported_plate_ignores_configured_but_unused_filaments(tmp_path):
    path = tmp_path / "single-export.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"cool_plate_temp_initial_layer": ["35", "110"]}),
        )
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/><metadata key="curr_bed_type" '
            'value="Cool Plate"/><filament id="1" used_g="8"/></plate></config>',
        )

    assert extract_bed_temperature_from_3mf(path, 1) == 35


def test_unknown_plate_uses_generic_orca_fallback_only_when_present():
    assert bed_temperature_from_config({"curr_bed_type": "Future Plate", "bed_temperature": ["72"]}) == 72
    assert bed_temperature_from_config({"curr_bed_type": "Future Plate", "hot_plate_temp": ["90"]}) is None


def test_zero_first_layer_array_falls_back_to_the_regular_plate_array():
    assert (
        bed_temperature_from_config(
            {
                "curr_bed_type": "Cool Plate",
                "cool_plate_temp_initial_layer": ["0", "0"],
                "cool_plate_temp": ["30", "35"],
            }
        )
        == 35
    )


def test_disk_extractors_refuse_ambiguous_multi_plate_values(tmp_path):
    path = tmp_path / "multi.3mf"
    _write_multi_plate_3mf(path)

    assert extract_bed_temperature_from_3mf(path) is None
    assert extract_bed_temperature_from_3mf(path, 2) == 70
    assert extract_layer_height_from_3mf(path, 2) == 0.08
    assert extract_layer_height_from_3mf(path, 9) is None


def test_explicit_plate_requires_slice_info_evidence(tmp_path):
    path = tmp_path / "project-only.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"curr_bed_type": "Cool Plate", "cool_plate_temp_initial_layer": ["35"]}),
        )

    assert extract_bed_temperature_from_3mf(path, 2) is None


def test_explicit_plate_requires_its_own_bed_type(tmp_path):
    path = tmp_path / "missing-bed-type.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"curr_bed_type": "Cool Plate", "cool_plate_temp_initial_layer": ["35", "40"]}),
        )
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="2"/><filament id="2" used_g="9"/></plate></config>',
        )

    assert extract_bed_temperature_from_3mf(path, 2) is None
