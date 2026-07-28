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
