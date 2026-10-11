"""Manufacturer words and alert levels must survive the actual MQTT parser."""

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


def client(serial="093TEST"):
    return BambuMQTTClient(ip_address="192.0.2.1", serial_number=serial, access_code="fixture")


def test_hms_uses_code_alert_level_and_full_manufacturer_description():
    mqtt = client()
    mqtt._update_state({"hms": [{"attr": 0x03000200, "code": 0x00010008}], "subtask_id": "job-7"})
    fault = mqtt.state.hms_errors[0]
    assert fault.severity == 1, "level lives in code bits 16–23, not attr part bits"
    assert "nozzle temperature" in fault.description
    assert fault.full_code == "0300020000010008" and fault.job_id == "job-7"


@pytest.mark.parametrize("code,level", [(0x03004000, 1), (0x03008004, 2), (0x0300C012, 3)])
def test_print_error_level_matches_task_stop_pause_or_prompt(code, level):
    mqtt = client()
    mqtt._update_state({"print_error": code})
    fault = mqtt.state.hms_errors[0]
    assert fault.severity == level
    assert fault.description
    assert fault.full_code == f"{code:08X}"


def test_zero_hms_level_is_not_promoted_and_real_small_error_number_is_retained():
    mqtt = client()
    mqtt._update_state({"hms": [{"attr": 0x03000200, "code": 0x00000008}]})
    assert len(mqtt.state.hms_errors) == 1
    assert mqtt.state.hms_errors[0].severity == 0


def test_model_specific_manufacturer_text_and_cancel_echo_exceptions():
    texts = []
    for serial in ("093TEST", "20PTEST"):
        mqtt = client(serial)
        mqtt._update_state({"print_error": 0x03008001})
        texts.append(mqtt.state.hms_errors[0].description)
        mqtt._update_state({"hms": [], "print_error": 0x0300400C})
        assert mqtt.state.hms_errors == []
        mqtt._update_state({"print_error": 0x0500400E})
        assert mqtt.state.hms_errors == []
    assert "pause command" in texts[0] and "by the user" in texts[1]


def test_fault_keyspaces_do_not_collapse_and_empty_manufacturer_text_stays_empty():
    from backend.app.services.hms_errors import describe_fault, lookup_fault

    # An HMS identifier ending 4000 must not borrow the short print_error's text.
    assert describe_fault("0300020000014000") is None
    assert describe_fault("03004000")
    assert lookup_fault("0500C011") == ""
    assert describe_fault("0500C011") is None
    assert lookup_fault("NOTHEX0000000000") is None


def test_notification_keys_distinguish_faults_on_the_same_part_and_counts_use_actual_levels():
    from backend.app.main import _hms_errors_to_notify, _hms_notify_key
    from backend.app.services.bambu_mqtt import HMSError

    faults = [
        HMSError(
            code=f"0x{n:x}",
            attr=0x03000200,
            module=3,
            severity=1,
            description="Manufacturer warning",
            full_code=f"030002000001{n:04X}",
        )
        for n in (8, 9)
    ]
    notice = HMSError(
        code="0x30001",
        attr=0x03009700,
        module=3,
        severity=3,
        description="The top cover is open.",
        full_code="0300970000030001",
    )
    unknown = HMSError(code="0x10008", attr=0xFFFFFFFF, module=255, severity=1, full_code="FFFFFFFF00010008")
    assert len({_hms_notify_key(fault) for fault in faults}) == 2
    assert (
        _hms_errors_to_notify(
            [*faults, notice, unknown], {_hms_notify_key(fault) for fault in [*faults, notice, unknown]}
        )
        == faults
    )


def test_mqtt_completion_payload_keeps_the_resolved_description_and_firmware_action_context():
    mqtt = client()
    completions = []
    mqtt.on_print_complete = completions.append
    mqtt._update_state({"gcode_state": "RUNNING", "subtask_name": "fixture", "subtask_id": "job-7"})
    mqtt._update_state({"gcode_state": "FAILED", "hms": [{"attr": 0x03000200, "code": 0x00010008}]})
    assert len(completions) == 1
    fault = completions[0]["hms_errors"][0]
    assert fault["description"] == mqtt.state.hms_errors[0].description
    assert fault["full_code"] == "0300020000010008" and fault["severity"] == 1
    assert fault["job_id"] == "job-7" and fault["actions"] == mqtt.state.hms_errors[0].actions
