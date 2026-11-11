"""A positive timer alone never establishes that drying is parked."""

from unittest.mock import MagicMock, patch

from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.drying_telemetry import DryingTelemetry, invalidate_drying_availability
from backend.app.services.queue_drying import only_parked_countdowns


def _client():
    return BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")


def _push(client, at, **fields):
    with patch("backend.app.services.drying_telemetry.time.monotonic", return_value=at):
        client._handle_ams_data({"ams": [{"id": 0, **fields}]})


def _parked(client):
    manager = MagicMock()
    manager.get_status.return_value = client.state
    return only_parked_countdowns(manager, 1)


def test_two_fresh_inactive_reports_establish_a_parked_timer_then_progress_clears_it():
    client = _client()
    _push(client, 1000, dry_time=60, info="0")
    _push(client, 1149, dry_time=60, info="0")
    assert not _parked(client)
    _push(client, 1151, dry_time=60, info="0")
    assert _parked(client)
    _push(client, 1152, dry_time=59)
    assert not _parked(client)


def test_an_active_heating_phase_does_not_park_even_if_the_counter_stays_constant():
    client = _client()
    _push(client, 1000, dry_time=60, info="10")
    _push(client, 1600, dry_time=60, info="10")
    assert not _parked(client)
    _push(client, 1601, dry_time=60, info="0")
    assert not _parked(client)
    _push(client, 1752, dry_time=60, info="0")
    assert _parked(client)


def test_a_cached_timer_and_missing_phase_do_not_establish_parking():
    client = _client()
    _push(client, 1000, dry_time=60, info="0")
    _push(client, 1600, humidity_raw=40, info="0")
    assert not _parked(client)
    _push(client, 1601, dry_time=60)
    assert not _parked(client)


def test_a_new_connection_or_command_cannot_reuse_previous_parking_evidence():
    client = _client()
    _push(client, 1000, dry_time=60, info="0")
    _push(client, 1151, dry_time=60, info="0")
    assert _parked(client)
    client.state.drying_telemetry = DryingTelemetry()
    assert not _parked(client)
    _push(client, 1200, dry_time=60, info="0")
    _push(client, 1351, dry_time=60, info="0")
    assert _parked(client)
    invalidate_drying_availability(client.state)
    assert not _parked(client)


def test_one_active_unit_keeps_the_printer_held():
    client = _client()
    _push(client, 1000, dry_time=60, info="0")
    _push(client, 1151, dry_time=60, info="0")
    client._handle_ams_data({"ams": [{"id": 1, "dry_time": 60, "info": "10"}]})
    assert not _parked(client)
