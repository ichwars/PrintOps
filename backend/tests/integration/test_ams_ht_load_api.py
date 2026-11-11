"""Public load requests accept actual HT and Lite global tray ids."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("tray", [128, 135, 24, 27])
async def test_load_accepts_ht_and_lite(async_client, printer_factory, tray):
    printer = await printer_factory()
    client = MagicMock()
    client.ams_load_filament.return_value = True
    with patch("backend.app.api.routes.printers_ams.printer_manager") as manager:
        manager.get_client.return_value = client
        response = await async_client.post(f"/api/v1/printers/{printer.id}/ams/load", params={"tray_id": tray})
    assert response.status_code == 200, response.text
    client.ams_load_filament.assert_called_once_with(tray)


@pytest.mark.parametrize("tray", [16, 23, 28, 127, 136, 253, 256, -1])
async def test_invalid_global_slot_never_reaches_mqtt(async_client, printer_factory, tray):
    printer = await printer_factory()
    with patch("backend.app.api.routes.printers_ams.printer_manager") as manager:
        response = await async_client.post(f"/api/v1/printers/{printer.id}/ams/load", params={"tray_id": tray})
    assert response.status_code == 400, response.text
    manager.get_client.assert_not_called()
