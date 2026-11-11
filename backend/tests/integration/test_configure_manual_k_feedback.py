"""A sent filament configuration may still have an unsent manual K value."""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.bambu_mqtt import NozzleInfo, PrinterState

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("sent", [True, False])
async def test_manual_k_publish_result_is_reported(async_client, printer_factory, sent):
    printer = await printer_factory(model="P1S")
    client = MagicMock()
    client.ams_set_filament_setting.return_value = True
    client.extrusion_cali_set.return_value = sent
    state = PrinterState()
    state.nozzles = [NozzleInfo(nozzle_diameter="0.4")]
    with patch("backend.app.api.routes.printers_ams.printer_manager") as manager:
        manager.get_client.return_value = client
        manager.get_status.return_value = state
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/slots/0/0/configure",
            params={
                "tray_info_idx": "GFL99",
                "tray_type": "PLA",
                "tray_sub_brands": "Generic PLA",
                "tray_color": "000000FF",
                "nozzle_temp_min": 190,
                "nozzle_temp_max": 230,
                "k_value": 0.032,
                "cali_idx": -1,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert response.json()["k_value_unsent"] is (not sent)
    client.extrusion_cali_set.assert_called_once()
