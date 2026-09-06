"""AMS wire colours remain stable across firmware telemetry (#137)."""

import json
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient, wire_tray_color
from backend.app.utils.color_utils import colors_similar


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("09ff00ff", "09FF00FF"),
        ("#09ff00ff", "09FF00FF"),
        (" AbCdEf12 ", "ABCDEF12"),
        ("00000000", "00000000"),
        ("", ""),
        (None, ""),
    ],
)
def test_wire_color_is_uppercase_bare_hex(stored: str | None, expected: str):
    assert wire_tray_color(stored) == expected


def test_normalized_color_survives_assignment_match():
    assert colors_similar(wire_tray_color("#09ff00ff"), "09FF00FF")


def test_mqtt_command_normalizes_color_at_the_wire_boundary():
    client = BambuMQTTClient("10.0.0.1", "ISSUE137", "secret", "P1S")
    client._client = MagicMock()
    client.state.connected = True

    assert client.ams_set_filament_setting(0, 2, "GFL99", "PLA", "eSUN PLA+", "#09ff00ff", 190, 230)

    payload = json.loads(client._client.publish.call_args.args[1])["print"]
    assert payload["tray_color"] == "09FF00FF"
    assert payload["tray_type"] == "PLA"
    assert payload["tray_sub_brands"] == "eSUN PLA+"
