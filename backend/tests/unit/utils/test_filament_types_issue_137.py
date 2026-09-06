"""Protocol-safe AMS filament types for PrintOps issue #137."""

import json
from pathlib import Path

import pytest

from backend.app.core.catalog_defaults import DEFAULT_COLOR_CATALOG
from backend.app.utils.filament_types import (
    _PRINTER_TYPES,
    is_material_name,
    nozzle_temp_range,
    printer_filament_type,
)


@pytest.mark.parametrize(
    ("product_name", "protocol_type"),
    [
        ("PLA+", "PLA"),
        ("PLA Wood", "PLA"),
        ("PLA Silk", "PLA"),
        ("PolyTerra PLA", "PLA"),
        ("PLA-AERO", "PLA-AERO"),
        ("PLA Aero", "PLA-AERO"),
        ("PLA-GF", "PLA-GF"),
        ("ASA-GF", "ASA-GF"),
    ],
)
def test_product_name_and_protocol_type_stay_distinct(product_name: str, protocol_type: str):
    assert printer_filament_type(product_name) == protocol_type


def test_unknown_material_is_not_guessed():
    assert printer_filament_type("CPE HG100") == "CPE HG100"


@pytest.mark.parametrize("product_name", ["PLA+", "PLA Wood", "PLA Silk", "PolyTerra PLA"])
def test_product_names_are_not_reused_as_filament_ids(product_name: str):
    assert is_material_name(product_name)


def test_filled_and_foamed_types_use_safe_temperature_fallbacks():
    assert nozzle_temp_range("PLA-AERO", "PLA-AERO") == (190, 230)
    assert nozzle_temp_range("ASA-GF", "ASA-GF") == (240, 270)
    assert nozzle_temp_range("PETG-CF", "PETG-CF") == (240, 270)


def test_every_offered_profile_type_remains_distinct():
    path = Path(__file__).resolve().parents[3] / "app" / "data" / "filament_fields.json"
    fields = json.loads(path.read_text(encoding="utf-8"))["fields"]
    options = next(field["options"] for field in fields if field["key"] == "filament_type")
    assert {option["value"] for option in options} <= set(_PRINTER_TYPES)
    assert all(printer_filament_type(option["value"]) == option["value"] for option in options)


def test_shipped_product_names_are_placed_or_explicitly_left_unknown():
    known = set(_PRINTER_TYPES)
    leftovers = {row[3] for row in DEFAULT_COLOR_CATALOG if printer_filament_type(row[3]) not in known}
    assert leftovers == {"CPE HG100", "FiberSilk Metallic", "NylonG", "NylonX", "XT"}
