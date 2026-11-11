"""Printer acceptance requires telemetry for the desired slot, preset and colour."""

from unittest.mock import Mock, patch

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.fixture
def client():
    mqtt = BambuMQTTClient("192.0.2.1", "TEST", "dummy")
    mqtt.on_assignment_verified = Mock()
    return mqtt


def _tray(**kwargs):
    return {"id": 0, "tray_info_idx": "GFA01", "tray_color": "008800FF", "cali_idx": 4, **kwargs}


def _register(client, *, ams_id=0, tray_id=0, preset="GFA01", cali=4):
    client.register_assignment_verification(ams_id, tray_id, preset, "008800FF", cali)


@pytest.mark.parametrize(
    ("ams_id", "tray_id", "raw"),
    [
        (0, 0, {"ams": [{"id": 0, "tray": [_tray()]}]}),
        (0, 0, {"ams": {"ams": [{"id": 0, "tray": [_tray()]}]}}),
        (128, 0, {"ams": [{"id": 128, "tray": [_tray(id=3)]}]}),
        (255, 0, {"vt_tray": _tray(id=254)}),
        (255, 1, {"vt_tray": [_tray(id=254, tray_info_idx="other"), _tray(id=255)]}),
    ],
)
def test_matching_telemetry_confirms_the_logical_slot_once(client, ams_id, tray_id, raw):
    _register(client, ams_id=ams_id, tray_id=tray_id)
    client.state.raw_data = raw
    client.check_assignment_push({"ams": {}})
    client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_called_once_with(
        ams_id, tray_id, True, {"tray_info_idx": "GFA01", "kprofile_applied": True}
    )


@pytest.mark.parametrize("actual", [_tray(tray_info_idx="GFA00"), _tray(tray_color="FF0000FF")])
def test_another_preset_or_colour_cannot_confirm_an_assignment(client, actual):
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=100):
        _register(client)
        client.state.raw_data = {"ams": [{"id": 0, "tray": [actual]}]}
        client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_not_called()
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=131):
        client.check_assignment_push({"ams": {}})
    event = client.on_assignment_verified.call_args.args
    assert event[:3] == (0, 0, False)
    assert event[3]["saw_tray"] is True


def test_a_missing_kprofile_is_reported_separately(client):
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=100):
        _register(client)
    client.state.raw_data = {"ams": [{"id": 0, "tray": [_tray(cali_idx=7)]}]}
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=101):
        client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_not_called()
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=131):
        client.check_assignment_push({"ams": {}})
    assert client.on_assignment_verified.call_args.args == (
        0,
        0,
        True,
        {"tray_info_idx": "GFA01", "kprofile_applied": False},
    )


def test_command_acknowledgements_do_not_confirm_even_cached_matching_values(client):
    _register(client)
    client.state.raw_data = {"ams": [{"id": 0, "tray": [_tray()]}]}
    client.check_assignment_push({"command": "ams_filament_setting", "result": "success", "ams": {"ams": []}})
    client.on_assignment_verified.assert_not_called()
    assert len(client._pending_assignments) == 1


def test_a_new_assignment_replaces_the_previous_target(client):
    _register(client, preset="GFA00")
    _register(client, preset="GFA01")
    client.state.raw_data = {"ams": [{"id": 0, "tray": [_tray(tray_info_idx="GFA00")]}]}
    client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_not_called()
    assert client._pending_assignments[(0, 0)]["tray_info_idx"] == "GFA01"


@pytest.mark.parametrize("raw", [{}, {"ams": None}, {"ams": [None]}, {"ams": {"ams": "invalid"}}])
def test_missing_or_malformed_trays_do_not_confirm(client, raw):
    _register(client)
    client.state.raw_data = raw
    client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_not_called()


def test_blank_targets_and_reconnect_clear_do_not_leave_old_verifications(client):
    _register(client, preset="")
    assert client._pending_assignments == {}
    _register(client)
    client.clear_assignment_verifications()
    assert client._pending_assignments == {}


@pytest.mark.parametrize(
    ("tray", "expected"),
    [
        (_tray(state=9), False),
        (_tray(state=10), False),
        (_tray(state=9, exists=True), True),
        (_tray(state=11), True),
        (_tray(state=11, exists=False), False),
    ],
)
def test_only_known_empty_slots_are_excluded_from_read_back(client, tray, expected):
    from backend.app.services.assignment_verification import register_sent_assignment

    client.state.raw_data = {"ams": [{"id": 0, "tray": [tray]}]}
    client.request_status_update = Mock()
    register_sent_assignment(client, client.state, 0, 0, "GFA01", "008800FF", 4)
    assert bool(client._pending_assignments) is expected
    assert client.request_status_update.called is expected


def test_calibration_can_arrive_in_a_later_push(client):
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=100):
        _register(client)
        tray = _tray(cali_idx=-1)
        client.state.raw_data = {"ams": [{"id": 0, "tray": [tray]}]}
        client.check_assignment_push({"ams": {}})
        client.on_assignment_verified.assert_not_called()
        tray["cali_idx"] = 4
        client.check_assignment_push({"ams": {}})
    assert client.on_assignment_verified.call_args.args[3]["kprofile_applied"] is True


def test_a_boolean_calibration_index_is_not_an_accepted_index(client):
    with patch("backend.app.services.assignment_verification.time.monotonic", return_value=100):
        _register(client, cali=1)
        client.state.raw_data = {"ams": [{"id": 0, "tray": [_tray(cali_idx=True)]}]}
        client.check_assignment_push({"ams": {}})
    client.on_assignment_verified.assert_not_called()
