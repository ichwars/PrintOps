import json

import pytest

from backend.app.utils.printer_models import (
    h2c_nozzle_mapping_capability,
    validate_h2c_nozzle_mapping,
)


@pytest.mark.parametrize("length", [8, 32])
def test_physical_mapping_shapes_are_distinguished(length):
    raw = [16, 1] + [-1] * (length - 2)
    parsed, reason = validate_h2c_nozzle_mapping(json.dumps(raw))
    assert parsed == raw
    assert reason is None


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ([0, 1], "unsupported_length"),
        ([0, 1] + [-1] * 6, "logical_or_unknown_physical_id"),
        ([[16], [1]] + [-1] * 6, "non_integer_or_grouped_value"),
        ("not json", "unparseable_json"),
        ([-1] * 8, "empty_mapping"),
    ],
)
def test_compact_ambiguous_and_unparseable_mappings_are_rejected(raw, reason):
    assert validate_h2c_nozzle_mapping(raw) == (None, reason)


@pytest.mark.parametrize("model", ["H2D", "H2D Pro", "X2D"])
def test_other_dual_nozzle_models_never_gain_h2c_capability(model):
    assert h2c_nozzle_mapping_capability(model, "O1C2", "01.02.00.00") == (False, "not_h2c")


@pytest.mark.parametrize("code", ["O1C", "O1C2"])
def test_h2c_codes_stay_disabled_without_hardware_release(code):
    assert h2c_nozzle_mapping_capability("H2C", code, "01.02.00.00") == (
        False,
        "raw_model_code_not_hardware_validated",
    )
