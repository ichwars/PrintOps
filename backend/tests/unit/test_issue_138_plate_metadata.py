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


def _write_multi_plate_3mf(path) -> None:
    project = {
        "layer_height": ["0.20"],
        "curr_bed_type": "Cool Plate",
        "cool_plate_temp_initial_layer": ["35", "40"],
        "textured_plate_temp_initial_layer": ["65", "70"],
    }
    slice_info = """<config>
      <plate><metadata key="index" value="1"/><metadata key="curr_bed_type" value="Cool Plate"/></plate>
      <plate><metadata key="index" value="2"/><metadata key="curr_bed_type" value="Textured PEI Plate"/></plate>
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
