"""A rejected project_file response must not stand in for a running print."""

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.mark.parametrize("result", ["FAIL", "failed", "ERROR"])
def test_refused_start_keeps_previous_print_identity(result):
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client.state.subtask_id = "running"
    client.state.subtask_name = "Current print"
    client._update_state(
        {
            "command": "project_file",
            "result": result,
            "reason": "Refused",
            "subtask_id": "rejected",
            "subtask_name": "Wrong print",
        }
    )
    assert client.state.subtask_id == "running"
    assert client.state.subtask_name == "Current print"
    assert client.last_start_refusal == (result, "Refused")


@pytest.mark.parametrize("extra", [{}, {"command": "project_file", "result": "SUCCESS"}])
def test_regular_status_and_successful_ack_update_identity(extra):
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client._update_state({"subtask_id": "new", "subtask_name": "New print", **extra})
    assert client.state.subtask_id == "new"
    assert client.state.subtask_name == "New print"
    assert client.last_start_refusal is None
