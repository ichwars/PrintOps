"""Expired load hints, duplicate faults and filament-write refusal diagnostics."""

import logging
import time

import pytest

from backend.tests.unit.services.test_bambu_mqtt import (
    _ams_payload,
    _H2DFixtureMixin,
)


@pytest.fixture
def mqtt_client():
    from backend.app.services.bambu_mqtt import BambuMQTTClient

    return BambuMQTTClient(ip_address="192.0.2.1", serial_number="W04", access_code="12345678")


class TestPendingTargetExpiry(_H2DFixtureMixin):
    def test_refused_old_load_does_not_relabel_the_next_print(self, h2d_client):
        h2d_client.state.pending_tray_target = 5
        h2d_client.state.pending_tray_target_at = time.monotonic() - 600
        h2d_client._process_message(_ams_payload(1))
        assert h2d_client.state.tray_now != 5
        assert h2d_client.state.pending_tray_target is None


def test_one_fault_reported_through_both_sources_is_listed_once(mqtt_client):
    mqtt_client._update_state({"hms": [{"attr": 0x05000100, "code": 0x00018061}], "print_error": 0x05008061})
    assert len(mqtt_client.state.hms_errors) == 1


def test_kprofile_refusal_reaches_support_logs(mqtt_client, caplog):
    caplog.set_level(logging.INFO, logger="backend.app.services.bambu_mqtt")
    mqtt_client._process_message(
        {
            "print": {
                "command": "extrusion_cali_sel",
                "result": "fail",
                "reason": "cali_idx not found",
                "ams_id": 0,
                "tray_id": 2,
                "sequence_id": "0",
            }
        }
    )
    lines = [record.message for record in caplog.records if "extrusion_cali_sel refused" in record.message]
    assert len(lines) == 1
    assert "cali_idx not found" in lines[0]


def test_developer_probe_refusal_stays_quiet(mqtt_client, caplog):
    caplog.set_level(logging.INFO, logger="backend.app.services.bambu_mqtt")
    mqtt_client._dev_mode_probe_seq = "17"
    mqtt_client._process_message({"print": {"command": "ams_filament_setting", "result": "fail", "sequence_id": "17"}})
    assert not any("ams_filament_setting refused" in record.message for record in caplog.records)
