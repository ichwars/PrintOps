"""Configuring Silk never borrows the Matte preset from a live slot."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize(("supplied", "expected"), [("", "GFL96"), ("PFUS9ac902733670a9", "PFUS9ac902733670a9")])
async def test_configure_silk_rejects_automatic_matte_reuse_but_keeps_explicit_identity(
    async_client: AsyncClient, printer_factory, supplied, expected
):
    """Same material, another finish: the slot's Matte id is not reused, and
    the generic is the one for the preset's finish."""
    printer = await printer_factory(name="H2D")
    mock_client = MagicMock()
    mock_client.ams_set_filament_setting.return_value = True
    mock_client.extrusion_cali_sel.return_value = True
    mock_client.request_status_update.return_value = True
    mock_status = MagicMock()
    tray = {"id": 3, "tray_info_idx": "GFA01", "tray_type": "PLA", "tray_sub_brands": "PLA Matte"}
    mock_status.raw_data = {"ams": {"ams": [{"id": 2, "tray": [tray]}]}}

    with patch("backend.app.api.routes.printers.printer_manager") as mock_pm:
        mock_pm.get_client.return_value = mock_client
        mock_pm.get_status.return_value = mock_status
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/slots/2/3/configure",
            params={
                "tray_info_idx": supplied,
                "tray_type": "PLA",
                "tray_sub_brands": "My PLA Silk",
                "tray_color": "FF0000FF",
                "nozzle_temp_min": 190,
                "nozzle_temp_max": 230,
            },
        )

    assert response.status_code == 200
    assert mock_client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
