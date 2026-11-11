"""An ambiguous H2 local slot never turns into an invented AMS0 usage event."""

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.fixture
def client():
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client._is_dual_nozzle = True
    client.state.tray_now = 5
    client.state.ams_extruder_map = {"0": 0, "1": 0, "2": 1}
    return client


def test_ambiguous_slot_keeps_loaded_tray(client):
    client._process_message({"print": {"ams": {"tray_now": "3"}}})
    assert client.state.tray_now == 5


def test_no_known_unit_keeps_loaded_tray(client):
    client.state.ams_extruder_map = {"0": 1}
    client._process_message({"print": {"ams": {"tray_now": "2"}}})
    assert client.state.tray_now == 5


def test_running_print_mapping_resolves_within_active_nozzle(client):
    client._was_running = True
    client.state.state = "RUNNING"
    client._process_message({"print": {"mapping": [259, 515], "ams": {"tray_now": "3"}}})
    assert client.state.tray_now == 7


def test_idle_print_mapping_cannot_override_loaded_tray(client):
    client._process_message({"print": {"mapping": [259], "ams": {"tray_now": "3"}}})
    assert client.state.tray_now == 5


def test_unsupported_snow_is_not_fresh_evidence(client):
    client.state.ams_extruder_map = {"0": 0}
    client.state.h2d_extruder_snow = {0: 0}
    client._process_message(
        {
            "print": {
                "device": {"extruder": {"info": [{"id": 0, "snow": 0xFA0001}, {"id": 1, "snow": 65535}]}},
                "ams": {"tray_now": "2"},
            }
        }
    )
    assert client.state.tray_now == 2


def test_mapping_candidates_can_be_narrowed_but_single_match_is_retained(client):
    assert client._resolve_local_slot_from_mapping(1, [1, 513], [1, 2]) == 9
    assert client._resolve_local_slot_from_mapping(2, [514], [0]) == 10
    assert client._resolve_local_slot_from_mapping(3, [3, 259], [0, 1]) is None
