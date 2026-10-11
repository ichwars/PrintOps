import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


def test_only_explicit_target_drying_values_refresh_observations():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    with patch("time.time", return_value=1000):
        client._handle_ams_data({"ams": [{"id": "0", "module_type": "n3f", "dry_time": 20, "tray": []}]})
    telemetry = getattr(client.state, "drying_telemetry", None)
    assert telemetry is not None, "scheduled drying requires explicit observations rather than cached raw_data"
    assert telemetry.units[0].observed_at == 1000
    assert telemetry.units[0].remaining_minutes == 20
    with patch("time.time", return_value=1010):
        client._handle_ams_data({"ams": [{"id": "0", "tray": []}, {"id": "1", "dry_time": 0}]})
    assert telemetry.units[0].observed_at == 1000
    assert telemetry.units[1].observed_at == 1010


def test_invalid_or_missing_dry_time_is_never_observed_stopped():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._handle_ams_data({"ams": [{"id": "0", "dry_time": "bad"}]})
    telemetry = getattr(client.state, "drying_telemetry", None)
    assert telemetry is not None
    assert telemetry.units[0].remaining_minutes is None


def test_malformed_cannot_dry_reasons_are_not_normalized_into_permission():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._handle_ams_data({"ams": [{"id": "0", "dry_time": 0, "dry_sf_reason": ["malformed"]}]})
    assert client.state.drying_telemetry.units[0].blocked


def test_idle_and_firmware_freshness_requires_actual_fields():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678", firmware_version="01.03.00.00")
    telemetry = getattr(client.state, "drying_telemetry", None)
    assert telemetry is not None
    assert telemetry.firmware_observed_at == 0
    assert telemetry.idle_observed_at == 0
    with patch("time.time", return_value=1000):
        client._handle_version_info({"module": [{"name": "ota", "sw_ver": "01.03.00.00"}]})
        client._update_state({"gcode_state": "IDLE"})
    assert telemetry.firmware_observed_at == 1000
    assert telemetry.idle_observed_at == 1000
    with patch("time.time", return_value=1010):
        client._update_state({"mc_percent": 0})
    assert telemetry.idle_observed_at == 1000


def test_changed_or_empty_version_inventory_invalidates_previous_capability():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._handle_version_info(
        {"module": [{"name": "ota", "sw_ver": "01.03.00.00"}, {"name": "n3f/0", "sw_ver": "05.00.22.22"}]}
    )
    assert client.state.drying_telemetry.modules[0][0] == "n3f"
    client._handle_ams_data({"ams": [{"id": "0", "dry_time": 0, "dry_sf_reason": []}]})
    assert client.state.drying_telemetry.units
    client._handle_version_info(
        {"module": [{"name": "ota", "sw_ver": "01.03.00.00"}, {"name": "ams/0", "sw_ver": "00.00.00.00"}]}
    )
    assert client.state.drying_telemetry.modules[0][0] == "ams"
    assert not client.state.drying_telemetry.units
    client._handle_version_info({"module": []})
    assert client.state.drying_telemetry.modules == {}
    assert client.state.drying_telemetry.firmware_observed_at == 0


def test_actual_disconnect_and_reconnect_clear_all_capability_proof():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._handle_version_info(
        {"module": [{"name": "ota", "sw_ver": "01.03.00.00"}, {"name": "n3f/0", "sw_ver": "05.00.22.22"}]}
    )
    client._handle_ams_data({"ams": [{"id": "0", "dry_time": 0, "dry_sf_reason": []}]})
    client._update_state({"gcode_state": "IDLE"})
    client._last_message_time = 0
    client._on_disconnect(MagicMock(), None, rc=1)
    assert not client.state.connected
    assert not client.state.drying_telemetry.modules
    client.state.drying_telemetry.modules[0] = ("n3f", "05.00.22.22")
    mqtt = MagicMock()
    mqtt.subscribe.return_value = (0, 1)
    client._on_connect(mqtt, None, {}, 0)
    assert client.state.connected
    assert not client.state.drying_telemetry.modules
    assert not client.state.drying_telemetry.units
    assert client.state.drying_telemetry.firmware_observed_at == 0
    assert client.state.drying_telemetry.idle_observed_at == 0


@pytest.mark.parametrize("qos", [0, 1])
def test_scheduled_no_retry_qos_preserves_existing_manual_wire_payload(qos):
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._client = MagicMock()
    client._client.publish.return_value.rc = 0
    assert client.send_drying_command(0, 45, 4, filament="PLA", **({"qos": 0} if qos == 0 else {}))
    call = client._client.publish.call_args
    assert call.kwargs["qos"] == qos
    wire = json.loads(call.args[1])["print"]
    assert wire["command"] == "ams_filament_drying"
    assert wire["close_power_conflict"] is False
    assert (wire["ams_id"], wire["temp"], wire["duration"], wire["mode"]) == (0, 45, 4, 1)


def test_qos_zero_publish_rejection_is_not_reported_delivered():
    client = BambuMQTTClient("192.0.2.1", "TEST", "12345678")
    client._client = MagicMock()
    client._client.publish.return_value.rc = 4
    assert not client.send_drying_command(0, 45, 4, qos=0)
    assert not client._drying_targets
