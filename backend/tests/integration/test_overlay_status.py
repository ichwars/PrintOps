"""The public overlay returns only scoped, allowlisted streaming details."""

from unittest.mock import patch

import pytest

from backend.app.services.bambu_mqtt import PrinterState
from backend.tests.integration.test_long_lived_tokens_api import _create_user, _login, _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("model,chamber", [("H2D", True), ("A1", False)])
async def test_overlay_allowlists_sensor_readings_and_heating_targets(async_client, printer_factory, model, chamber):
    printer = await printer_factory(model=model)
    state = PrinterState()
    state.connected = True
    state.temperatures = {
        "nozzle": 180,
        "nozzle_target": 220,
        "nozzle_heating": True,
        "nozzle_2": 215,
        "nozzle_2_target": 200,
        "nozzle_2_heating": False,
        "bed": 60,
        "bed_target": 60,
        "bed_heating": False,
        "chamber": 35,
        "chamber_target": 50,
        "chamber_heating": True,
        "target_updated_at": 1791900000,
        "private": "never expose",
    }
    with patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=state):
        response = await async_client.get(f"/api/v1/printers/{printer.id}/overlay-status")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == model
    assert body["supports_chamber_sensor"] is chamber
    expected = {"nozzle": 180, "nozzle_target": 220, "nozzle_2": 215, "bed": 60}
    if chamber:
        expected.update(chamber=35, chamber_target=50)
    assert body["temperatures"] == expected
    assert not {"ip_address", "access_code", "serial_number", "hms_errors", "ams"} & body.keys()


async def test_offline_overlay_keeps_model_and_capability_but_has_no_readings(async_client, printer_factory):
    printer = await printer_factory(model="A1")
    with patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=None):
        response = await async_client.get(f"/api/v1/printers/{printer.id}/overlay-status")
    assert response.json()["model"] == "A1"
    assert response.json()["supports_chamber_sensor"] is False
    assert response.json()["temperatures"] == {}


async def test_overlay_token_is_bound_to_current_owner_printer_scope(async_client, printer_factory):
    allowed = await printer_factory()
    denied = await printer_factory()
    admin = await _setup_admin(async_client)
    user_id = await _create_user(async_client, admin, "overlayviewer")
    owner = await _login(async_client, "overlayviewer")
    headers = {"Authorization": f"Bearer {admin}"}
    update = await async_client.patch(
        f"/api/v1/users/{user_id}", headers=headers, json={"allowed_printer_ids": [allowed.id]}
    )
    assert update.status_code == 200, update.text
    created = await async_client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {owner}"},
        json={"name": "OBS", "scope": "overlay", "expires_in_days": 1},
    )
    assert created.status_code == 201, created.text
    params = {"token": created.json()["token"]}
    response = await async_client.get(f"/api/v1/printers/{allowed.id}/overlay-status", params=params)
    assert response.status_code == 200
    response = await async_client.get(f"/api/v1/printers/{denied.id}/overlay-status", params=params)
    assert response.status_code == 403
    for path in [f"/api/v1/printers/{allowed.id}", f"/api/v1/printers/{allowed.id}/status", "/api/v1/settings"]:
        response = await async_client.get(path, params=params)
        assert response.status_code in (401, 403), path
    # Current ownership scope is evaluated on every poll, not frozen at mint time.
    await async_client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"allowed_printer_ids": [denied.id]})
    assert (await async_client.get(f"/api/v1/printers/{allowed.id}/overlay-status", params=params)).status_code == 403
    assert (await async_client.get(f"/api/v1/printers/{denied.id}/overlay-status", params=params)).status_code == 200

    response = await async_client.post("/api/v1/auth/ws-token", params=params)
    assert response.status_code in (401, 403)
    for scope in ("camera_stream", "camwall"):
        wrong_scope = await async_client.post(
            "/api/v1/auth/tokens",
            headers={"Authorization": f"Bearer {owner}"},
            json={"name": scope, "scope": scope, "expires_in_days": 1},
        )
        response = await async_client.get(
            f"/api/v1/printers/{denied.id}/overlay-status", params={"token": wrong_scope.json()["token"]}
        )
        assert response.status_code == 401
