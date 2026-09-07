"""API regressions for Obico printer verdicts and permission redaction (#141)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.app.api.routes.obico import (
    TestConnectionRequest as ObicoTestConnectionRequest,
    get_printer_status,
    test_connection as obico_test_connection,
)
from backend.app.services.obico_detection import obico_detection_service
from backend.app.services.obico_smoothing import PrintState


@pytest.fixture(autouse=True)
def clear_detection_state():
    obico_detection_service._states.clear()
    obico_detection_service._last_class.clear()
    obico_detection_service._errors.clear()
    obico_detection_service._last_error = None
    yield
    obico_detection_service._states.clear()
    obico_detection_service._last_class.clear()
    obico_detection_service._errors.clear()
    obico_detection_service._last_error = None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_printer_status_exposes_error_class_and_reason_without_reporting_safe(
    async_client: AsyncClient,
):
    obico_detection_service._states[1] = PrintState()
    obico_detection_service._errors[1] = "Obico ML API rejected the token (401)."

    response = await async_client.get("/api/v1/obico/printer-status")

    assert response.status_code == 200
    entry = response.json()["per_printer"]["1"]
    assert entry["class"] == "error"
    assert entry["error"] == "Obico ML API rejected the token (401)."


@pytest.mark.asyncio
async def test_printer_reader_without_settings_permission_gets_class_but_not_internal_reason():
    obico_detection_service._states[1] = PrintState()
    obico_detection_service._errors[1] = "ML API http://192.168.8.9:3333 refused"
    obico_detection_service._last_error = obico_detection_service._errors[1]
    user = MagicMock()
    user.has_permission.return_value = False
    loaded = {"enabled": True, "enabled_printers": None}

    with patch.object(
        obico_detection_service,
        "_load_settings",
        new=AsyncMock(return_value=loaded),
    ):
        data = await get_printer_status(user=user)

    assert data["per_printer"][1]["class"] == "error"
    assert data["per_printer"][1]["error"] is None
    assert data["last_error"] is None
    assert "192.168.8.9" not in str(data)


@pytest.mark.asyncio
async def test_connection_without_payload_values_checks_saved_configuration():
    loaded = {
        "ml_url": "http://saved-obico:3333",
        "ml_token": "saved-token",
    }
    with (
        patch.object(
            obico_detection_service,
            "_load_settings",
            new=AsyncMock(return_value=loaded),
        ),
        patch.object(
            obico_detection_service,
            "test_connection",
            new=AsyncMock(return_value={"ok": True}),
        ) as probe,
    ):
        result = await obico_test_connection(ObicoTestConnectionRequest())

    assert result == {"ok": True}
    probe.assert_awaited_once_with("http://saved-obico:3333", "saved-token")
