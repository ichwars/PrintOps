"""AMS-HT uses its unit id, while AMS Lite uses physical unit16 on the wire."""

import json
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.fixture
def client():
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client.state.connected = True
    client._client = MagicMock()
    return client


@pytest.mark.parametrize(
    "tray,ams,slot,target", [(128, 128, 0, 128), (135, 135, 0, 135), (25, 16, 1, 16), (26, 16, 2, 16), (5, 1, 1, 5)]
)
def test_published_load_addresses_the_actual_unit(client, tray, ams, slot, target):
    assert client.ams_load_filament(tray)
    command = json.loads(client._client.publish.call_args.args[1])["print"]
    assert (command["ams_id"], command["slot_id"], command["target"]) == (ams, slot, target)
    assert client.state.pending_tray_target == tray


@pytest.mark.parametrize("tray,ams", [(128, 128), (135, 135), (25, 16), (5, 1)])
def test_published_unload_keeps_the_loaded_unit(client, tray, ams):
    client.state.tray_now = tray
    assert client.ams_unload_filament()
    command = json.loads(client._client.publish.call_args.args[1])["print"]
    assert (command["ams_id"], command["slot_id"], command["target"]) == (ams, 255, 255)
