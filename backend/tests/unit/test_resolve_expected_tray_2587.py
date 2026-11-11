from backend.app.services.printer_manager import resolve_expected_tray


def test_single_regular_ams_resolves_local_slot_to_global_id():
    assert resolve_expected_tray(2, [(1, False)], None) == 6


def test_multiple_regular_ams_uses_mapping_when_unambiguous():
    assert resolve_expected_tray(2, [(0, False), (1, False)], [0 * 256 + 0, 1 * 256 + 2]) == 6


def test_multiple_regular_ams_returns_none_when_ambiguous():
    assert resolve_expected_tray(2, [(0, False), (1, False)], [0 * 256 + 2, 1 * 256 + 2]) is None


def test_external_and_ams_ht_are_already_global():
    assert resolve_expected_tray(254, [(0, False)], None) == 254
    assert resolve_expected_tray(128, [(128, True)], None) == 128


def test_idle_or_unknown_values_return_none():
    assert resolve_expected_tray(255, [(0, False)], None) is None
    assert resolve_expected_tray(-1, [(0, False)], None) is None
    assert resolve_expected_tray(None, [(0, False)], None) is None


def test_active_nozzle_narrows_ambiguous_local_slots_only_with_complete_wiring():
    layout = [(0, False), (1, False)]
    snow = [2, 258]
    assert resolve_expected_tray(2, layout, snow, active_extruder=1, ams_extruder_map={"0": 0, "1": 1}) == 6
    assert resolve_expected_tray(2, layout, None, active_extruder=1, ams_extruder_map={"0": 0, "1": 1}) == 6
    assert resolve_expected_tray(2, layout, snow, active_extruder=1, ams_extruder_map={"0": 0}) is None
    assert resolve_expected_tray(2, layout, snow, active_extruder=1, ams_extruder_map=None) is None


def test_invalid_mapping_values_do_not_prove_a_slot():
    assert resolve_expected_tray(False, [(0, False)], None) is None
    assert resolve_expected_tray(2, [(0, False), (1, False)], [-254, True]) is None
