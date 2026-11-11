"""Model-specific fan names retain the existing control boundary and wire PWM."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize(
    "model,fan,label,wire",
    [
        ("P2S", "aux", "Auxiliary fan", 2),
        ("P2S", "aux2", "Left auxiliary fan", 10),
        ("X2D", "aux", "Left auxiliary fan", 2),
        ("X2D", "aux2", "Right auxiliary fan", 10),
        ("N6", "aux2", "Right auxiliary fan", 10),
    ],
)
async def test_fans_use_model_side_and_existing_pwm(async_client, printer_factory, model, fan, label, wire):
    printer = await printer_factory(model=model)
    client = MagicMock()
    with patch("backend.app.api.routes.printers.printer_manager") as pm:
        pm.get_status.return_value = SimpleNamespace(connected=True, developer_mode=True, left_aux_fan_speed=0)
        pm.get_client.return_value = client
        response = await async_client.post(f"/api/v1/printers/{printer.id}/fan-speed?fan={fan}&speed=50")
    assert response.status_code == 200
    assert response.json()["message"] == f"{label} set to 50%"
    client.set_fan_speed.assert_called_once_with(wire, 128)


@pytest.mark.parametrize("reported", [None, False, "0"])
async def test_unknown_second_fan_is_rejected_before_any_send(async_client, printer_factory, reported):
    printer = await printer_factory(model="X2D")
    with patch("backend.app.api.routes.printers.printer_manager") as pm:
        pm.get_status.return_value = SimpleNamespace(connected=True, developer_mode=True, left_aux_fan_speed=reported)
        response = await async_client.post(f"/api/v1/printers/{printer.id}/fan-speed?fan=aux2&speed=50")
        pm.get_client.assert_not_called()
    assert response.status_code == 400
    assert "second auxiliary fan" in response.json()["detail"]
