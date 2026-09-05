"""Per-layer attribution must stay on the selected 3MF plate (issue #128)."""

import zipfile

import pytest

from backend.app.utils.threemf_tools import (
    extract_layer_filament_usage_from_3mf,
    get_cumulative_usage_at_layer,
)


def _layer_gcode(per_layer_mm: float, layers: int) -> str:
    lines = ["M620 S0"]
    for layer in range(1, layers + 1):
        lines.extend((f"M73 L{layer}", f"G1 X1 Y1 E{per_layer_mm}"))
    return "\n".join(lines)


def _multi_plate_3mf(tmp_path):
    path = tmp_path / "multi-plate.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        # Deliberately write plate 2 first: member order is not plate order.
        archive.writestr("Metadata/plate_2.gcode", _layer_gcode(1.0, 5))
        archive.writestr("Metadata/plate_1.gcode", _layer_gcode(10.0, 8))
    return path


def test_layer_usage_reads_requested_plate_not_first_zip_member(tmp_path):
    usage = extract_layer_filament_usage_from_3mf(_multi_plate_3mf(tmp_path), plate_id=1)

    assert usage is not None
    assert get_cumulative_usage_at_layer(usage, 8)[0] == pytest.approx(80.0)


def test_missing_requested_plate_does_not_read_another_plate(tmp_path):
    assert extract_layer_filament_usage_from_3mf(_multi_plate_3mf(tmp_path), plate_id=3) is None


def test_single_unnumbered_gcode_is_unambiguous_for_any_plate(tmp_path):
    path = tmp_path / "single.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("job.gcode", _layer_gcode(2.0, 4))

    usage = extract_layer_filament_usage_from_3mf(path, plate_id=7)

    assert usage is not None
    assert get_cumulative_usage_at_layer(usage, 4)[0] == pytest.approx(8.0)
