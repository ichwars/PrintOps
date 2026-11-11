"""Relative retractions conserve net filament without allowing invalid totals."""

import pytest

from backend.app.utils.archive_budget import ArchiveBudgetError
from backend.app.utils.threemf_tools import parse_gcode_layer_filament_usage


def test_retraction_and_recovery_do_not_inflate_the_total():
    parsed = parse_gcode_layer_filament_usage("M620 S0\nG1 E10\nG1 E-0.8\nG1 E0.8\nG1 E5")
    assert parsed == {0: {0: 15}}


def test_retraction_across_layers_is_kept_on_its_own_filament():
    parsed = parse_gcode_layer_filament_usage("M620 S0\nG1 E10\nG1 E-0.8\nM73 L1\nG1 E0.8\nG1 E4")
    assert parsed == {0: {0: pytest.approx(9.2)}, 1: {0: pytest.approx(14)}}


def test_retraction_does_not_belong_to_the_next_filament():
    parsed = parse_gcode_layer_filament_usage("M620 S0\nG1 E10\nG1 E-2\nM620 S1\nG1 E6\nG1 E-1\nG1 E1")
    assert parsed == {0: {0: 8, 1: 6}}


def test_a_layer_snapshot_cannot_have_negative_usage():
    parsed = parse_gcode_layer_filament_usage("M620 S1\nG1 E-3\nM73 L1\nG1 E5")
    assert parsed == {0: {1: 0}, 1: {1: 2}}


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_gcode_values_cannot_poison_a_spool_weight(value):
    assert parse_gcode_layer_filament_usage(f"M620 S0\nG1 E{value}\nG1 E10") == {0: {0: 10}}


def test_an_overflowed_extrusion_total_is_rejected():
    with pytest.raises(ArchiveBudgetError, match="not finite"):
        parse_gcode_layer_filament_usage("M620 S0\nG1 E1e308\nG1 E1e308")
