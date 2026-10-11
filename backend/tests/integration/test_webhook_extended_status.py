"""API-key clients receive enough state to distinguish jobs and HMS pauses."""

from unittest.mock import patch

import pytest

from backend.app.services.bambu_mqtt import HMSError, PrinterState
from backend.tests.integration.test_webhook_printer_status import api_key_data, printer_row  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id, expected", [("1234", "1234"), (1234, "1234"), ("0", None), ("", None), (None, None)])
async def test_extended_status_preserves_minutes_and_supplies_seconds(
    async_client, api_key_data, printer_row, job_id, expected
):
    state = PrinterState(
        connected=True,
        state="PAUSE",
        remaining_time=12,
        layer_num=3,
        total_layers=60,
        subtask_id=job_id,
        hms_errors=[
            HMSError(
                code="0700_8011",
                attr=0x07000000,
                module=7,
                severity=2,
                actions=["RESUME_PRINTING"],
                full_code="0700000000008011",
            )
        ],
    )
    with patch("backend.app.api.routes.webhook.printer_manager.get_status", return_value=state):
        response = await async_client.get(
            f"/api/v1/webhook/printer/{printer_row.id}/status", headers={"X-API-Key": api_key_data}
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["serial_number"] == printer_row.serial_number
    assert data["remaining_time"] == 12
    assert data["remaining_seconds"] == 720
    assert (data["layer_num"], data["total_layers"], data["subtask_id"]) == (3, 60, expected)
    assert data["hms_errors"][0]["actions"] == ["RESUME_PRINTING"]
    assert data["hms_errors"][0]["full_code"] == "0700000000008011"


@pytest.mark.asyncio
async def test_unknown_status_has_explicit_empty_additional_fields(async_client, api_key_data, printer_row):
    with patch("backend.app.api.routes.webhook.printer_manager.get_status", return_value=None):
        response = await async_client.get(
            f"/api/v1/webhook/printer/{printer_row.id}/status", headers={"X-API-Key": api_key_data}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["serial_number"] == printer_row.serial_number
    assert data["remaining_seconds"] is None
    assert data["hms_errors"] == []
