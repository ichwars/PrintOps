"""Automatic camera lighting stays scoped and releases only its own commands."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services import camera_light

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class CameraLamp:
    def __init__(self):
        self.state = SimpleNamespace(chamber_light=False)
        self.commands = []

    def set_chamber_light(self, enabled):
        self.commands.append(enabled)
        self.state.chamber_light = enabled
        return True


async def test_snapshots_follow_settings_and_manual_lighting_survives_viewers(async_client, printer_factory):
    chosen = await printer_factory(
        external_camera_enabled=True, external_camera_url="http://camera/snap", external_camera_type="snapshot"
    )
    other = await printer_factory()
    lamp = CameraLamp()
    light_api = f"/api/v1/printers/{chosen.id}"
    for update in (
        {"camera_light_mode": "invalid"},
        {"camera_light_mode": None},
        {"camera_light_delay": 6},
        {"camera_light_delay": None},
    ):
        assert (await async_client.patch("/api/v1/settings/", json=update)).status_code == 422

    saved = await async_client.patch(
        "/api/v1/settings/", json={"camera_light_mode": "selected", "camera_light_delay": 0}
    )
    assert saved.status_code == 200 and saved.json()["camera_light_mode"] == "selected"
    response = await async_client.patch(light_api, json={"camera_light_auto": True})
    assert response.status_code == 200 and response.json()["camera_light_auto"] is True

    async def capture(*_args, **_kwargs):
        assert lamp.state.chamber_light is True
        return b"jpeg"

    with (
        patch("backend.app.services.printer_manager.printer_manager.get_client", return_value=lamp) as client,
        patch("backend.app.services.external_camera.capture_frame", AsyncMock(side_effect=capture)),
    ):
        async with camera_light.automatic_camera_light(other):
            assert lamp.commands == []
        client.assert_not_called()
        reply = await async_client.get(f"{light_api}/camera/snapshot")
        assert reply.status_code == 200 and reply.content == b"jpeg", reply.text
        assert lamp.commands == [True, False]

        selected = SimpleNamespace(id=chosen.id, camera_light_auto=True)
        async with camera_light.automatic_camera_light(selected):
            async with camera_light.automatic_camera_light(selected):
                assert lamp.commands == [True, False, True]
            assert lamp.state.chamber_light is True
            lamp.set_chamber_light(False)
            camera_light.hand_back_camera_light(chosen.id)
            async with camera_light.automatic_camera_light(selected):
                assert lamp.state.chamber_light is False
        assert lamp.commands == [True, False, True, False]


async def test_printer_lighting_patch_checks_credentials_and_printer_scope(async_client, db_session, printer_factory):
    visible, hidden = await printer_factory(), await printer_factory()
    operator = User(
        username="camera-light-operator",
        allowed_printer_ids=[visible.id],
        groups=[Group(name="Printer edit", permissions=[Permission.PRINTERS_UPDATE.value])],
    )
    token, key_hash, prefix = generate_api_key()
    disabled, disabled_hash, disabled_prefix = generate_api_key()
    db_session.add_all(
        [
            operator,
            Settings(key="auth_enabled", value="true"),
            APIKey(name="Status key", key_hash=key_hash, key_prefix=prefix),
            APIKey(name="Revoked key", key_hash=disabled_hash, key_prefix=disabled_prefix, enabled=False),
        ]
    )
    await db_session.commit()
    session = {"Authorization": f"Bearer {create_access_token({'sub': operator.username})}"}
    expired = create_access_token({"sub": operator.username}, expires_delta=timedelta(seconds=-30))
    body = {"camera_light_auto": True}
    for headers, status in (
        ({}, 401),
        ({"X-API-Key": "wrong"}, 401),
        ({"X-API-Key": token}, 403),
        ({"X-API-Key": disabled}, 401),
        ({"Authorization": f"Bearer {expired}"}, 401),
    ):
        denied = await async_client.patch(f"/api/v1/printers/{visible.id}", json=body, headers=headers)
        assert denied.status_code == status, denied.text
    forbidden = await async_client.patch(f"/api/v1/printers/{hidden.id}", json=body, headers=session)
    assert forbidden.status_code == 404, forbidden.text
    allowed = await async_client.patch(f"/api/v1/printers/{visible.id}", json=body, headers=session)
    assert allowed.status_code == 200 and allowed.json()["camera_light_auto"] is True, allowed.text
