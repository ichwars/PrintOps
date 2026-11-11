"""Airduct accessory presence survives partial reports and reaches live clients."""

import json
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.printer_manager import printer_state_to_dict
from backend.app.services.printer_status_fingerprint import machine_status_key


@pytest.fixture
def client():
    c = BambuMQTTClient(ip_address="192.0.2.1", serial_number="QA-FAN", access_code="fixture", model="X2D")
    c.state.connected = True
    c._client = MagicMock()
    return c


def report(c, parts):
    c._process_message({"print": {"command": "push_status", "device": {"airduct": {"parts": parts}}}})


def test_packed_ids_and_speeds_are_decoded_before_clamping(client):
    report(
        client,
        [
            {"id": 16, "state": 30},
            {"id": 32, "state": 40},
            {"id": 48, "state": 0},
            {"id": 160, "state": (100 << 16) | 80},
        ],
    )
    assert client.state.left_aux_fan_speed == 80
    assert client.state.exhaust_fan_present is True
    payload = printer_state_to_dict(client.state)
    assert payload["left_aux_fan_speed"] == 80
    assert payload["exhaust_fan_present"] is True


def test_partial_report_preserves_presence_full_inventory_can_retract_it(client):
    report(client, [{"id": 160, "state": 0}, {"id": 48, "state": 0}])
    before = machine_status_key(client.state)
    report(client, [{"id": 16, "state": 50}])
    assert client.state.left_aux_fan_speed == 0
    assert client.state.exhaust_fan_present is True
    report(client, [{"id": 16, "state": 0}, {"id": 32, "state": 0}])
    assert client.state.left_aux_fan_speed is None
    assert client.state.exhaust_fan_present is False
    assert machine_status_key(client.state) != before


def test_malformed_parts_cannot_remove_a_known_accessory(client):
    client.state.left_aux_fan_speed = 80
    report(client, [None, {"id": "bad", "state": 0}, {"id": 32, "state": None}, {"id": True, "state": False}])
    assert client.state.left_aux_fan_speed == 80


def test_second_aux_uses_m106_p10(client):
    assert client.set_fan_speed(10, 128)
    assert "M106 P10 S128" in json.loads(client._client.publish.call_args.args[1])["print"]["param"]
