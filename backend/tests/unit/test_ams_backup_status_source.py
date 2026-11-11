"""Legacy backup toggles are telemetry only, with per-connection source trust."""

import time
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.fixture
def client():
    return BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")


def full_status(flag):
    return {"home_flag": flag, "command": "push_status", **{f"unused_{i}": 0 for i in range(31)}}


def test_legacy_delta_waits_for_a_full_status_then_follows_toggles(client):
    client._process_message({"print": {"home_flag": 1024}})
    assert client.state.ams_filament_backup is None
    client._process_message({"print": full_status(1024)})
    assert client.state.ams_filament_backup is True
    client._process_message({"print": {"home_flag": 0}})
    assert client.state.ams_filament_backup is False
    client._process_message({"print": {"home_flag": 1024}})
    assert client.state.ams_filament_backup is True


def test_cfg_stays_authoritative_after_it_is_seen(client):
    client._process_message({"print": full_status(1024)})
    client._process_message({"print": {"cfg": "0"}})
    assert client.state.ams_filament_backup is False
    client._process_message({"print": full_status(1024)})
    assert client.state.ams_filament_backup is False


def test_acknowledgement_does_not_claim_cfg_or_change_backup(client):
    client._process_message({"print": {"command": "project_file", "result": "SUCCESS", "cfg": "0"}})
    assert not getattr(client, "_backup_cfg_seen", False)
    client._process_message({"print": full_status(1024)})
    assert client.state.ams_filament_backup is True


def test_legacy_toggle_preserves_the_existing_hold_timer(client):
    client._process_message({"print": full_status(0)})
    client.state.ams_filament_backup = True
    client._xcam_hold_start["print_option_auto_switch_filament"] = time.time()
    client._process_message({"print": {"home_flag": 0}})
    assert client.state.ams_filament_backup is True
    client._xcam_hold_start["print_option_auto_switch_filament"] -= 10
    client._process_message({"print": {"home_flag": 0}})
    assert client.state.ams_filament_backup is False


def test_reconnect_clears_source_trust(client):
    client._process_message({"print": {"cfg": "0"}})
    mqtt = MagicMock()
    mqtt.subscribe.return_value = (0, 1)
    client._on_connect(mqtt, None, None, 0)
    assert client._backup_cfg_seen is False
    assert client._backup_home_flag_trusted is False
