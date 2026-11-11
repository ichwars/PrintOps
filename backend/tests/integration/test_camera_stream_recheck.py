"""Exercise camera authorization with real credentials and simulated video."""

import asyncio
from contextlib import aclosing, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.api.routes import camera
from backend.app.core import auth
from backend.app.core.auth_camera import camera_request_access
from backend.app.models.api_key import APIKey
from backend.app.models.auth_ephemeral import AuthEphemeralToken
from backend.app.services import camera_fanout
from backend.tests.integration.test_long_lived_tokens_api import _create_user, _login, _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("revoke_via", ["logout", "group"])
async def test_browser_mjpeg_stops_after_revocation_without_delivering_another_frame(
    async_client, printer_factory, monkeypatch, revoke_via
):
    printer = await printer_factory()
    other = await printer_factory()
    admin = await _setup_admin(async_client)
    admin_headers = {"Authorization": f"Bearer {admin}"}
    user_id = await _create_user(async_client, admin, "cameraobserver")
    grants = {"allowed_printer_ids": [printer.id]}
    group_id = None
    if revoke_via == "group":
        group = await async_client.post(
            "/api/v1/groups", headers=admin_headers, json={"name": "Camera viewers", "permissions": ["camera:view"]}
        )
        assert group.status_code == 201
        group_id = group.json()["id"]
        grants["group_ids"] = [group_id]
    response = await async_client.patch(f"/api/v1/users/{user_id}", headers=admin_headers, json=grants)
    assert response.status_code == 200
    jwt = await _login(async_client, "cameraobserver")
    headers = {"Authorization": f"Bearer {jwt}"}
    response = await async_client.post("/api/v1/printers/camera/stream-token", headers=headers)
    assert response.status_code == 200
    token = response.json()["token"]
    for candidate in (None, "invalid-camera-credential"):
        params = {"token": candidate} if candidate else {}
        response = await async_client.get(f"/api/v1/printers/{printer.id}/camera/stream", params=params)
        assert response.status_code == 401
    response = await async_client.get(f"/api/v1/printers/{other.id}/camera/stream", params={"token": token})
    assert response.status_code == 403
    status, opener = await camera_request_access(token, printer.id)
    assert status == 200 and opener is not None

    clock = [100.0]
    next_frame = asyncio.Event()

    async def software_camera(*args, **kwargs):
        yield b"first-frame"
        await next_frame.wait()
        yield b"frame-after-revocation"

    monkeypatch.setattr(camera, "monotonic", lambda: clock[0])
    monkeypatch.setattr(camera, "generate_go2rtc_mjpeg_stream", software_camera)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    try:
        async with auth.async_session() as db:
            response = await camera.camera_stream(printer.id, request, db=db, _=opener)
            async with aclosing(response.body_iterator) as viewer:
                assert await asyncio.wait_for(anext(viewer), timeout=2) == b"first-frame"
                if group_id is None:
                    response = await async_client.post("/api/v1/auth/logout", headers=headers)
                else:
                    response = await async_client.patch(
                        f"/api/v1/groups/{group_id}", headers=admin_headers, json={"permissions": []}
                    )
                assert response.status_code == 200
                clock[0] += 31
                next_frame.set()
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(viewer), timeout=2)
        response = await async_client.get(f"/api/v1/printers/{printer.id}/camera/stream", params={"token": token})
        assert response.status_code == (401 if group_id is None else 403)
    finally:
        await camera_fanout.shutdown_broadcaster(f"printer-{printer.id}")


async def test_api_key_camera_token_tracks_scope_disable_and_expiry(async_client, printer_factory, db_session):
    printer = await printer_factory()
    other = await printer_factory()
    await _setup_admin(async_client)
    secret = "bb_CameraKeyFixture"
    key = APIKey(
        name="Camera fixture",
        key_hash=auth.get_password_hash(secret),
        key_prefix=f"{secret[:8]}...",
        can_read_status=True,
        printer_ids=[printer.id],
    )
    db_session.add(key)
    await db_session.commit()
    response = await async_client.post("/api/v1/printers/camera/stream-token", headers={"X-API-Key": secret})
    assert response.status_code == 200
    token = response.json()["token"]
    assert (await camera_request_access(token, printer.id))[0] == 200
    assert (await camera_request_access(token, other.id))[0] == 403

    key.enabled = False
    await db_session.commit()
    assert (await camera_request_access(token, printer.id))[0] == 401

    key.enabled = True
    row = await db_session.scalar(select(AuthEphemeralToken).where(AuthEphemeralToken.token == token))
    row.expires_at = row.created_at
    await db_session.commit()
    assert (await camera_request_access(token, printer.id))[0] == 401


@pytest.mark.parametrize("revoke_via", ["share", "printer"])
async def test_idle_mse_view_closes_after_revocation(async_client, printer_factory, monkeypatch, revoke_via):
    printer = await printer_factory()
    admin = await _setup_admin(async_client)
    headers = {"Authorization": f"Bearer {admin}"}
    created = await async_client.post(
        "/api/v1/auth/tokens",
        headers=headers,
        json={"name": "Camera test", "scope": "overlay", "expires_in_days": 1},
    )
    assert created.status_code == 201
    share = created.json()
    connected = asyncio.Event()
    idle = asyncio.Event()
    revoked = asyncio.Event()

    async def idle_receive():
        await idle.wait()
        return {"type": "websocket.disconnect"}

    async def idle_upstream():
        await idle.wait()
        yield b"unexpected"

    @asynccontextmanager
    async def mock_connect(*args, **kwargs):
        connected.set()
        yield idle_upstream()

    check_access = camera._stream_access_allowed

    async def check_after_revocation(opener, printer_id):
        # The in-memory SQLite fixture shares one connection. Keep a cancelled
        # poll from invalidating the connection used to commit the revocation.
        await revoked.wait()
        return await check_access(opener, printer_id)

    websocket = SimpleNamespace(accept=AsyncMock(), close=AsyncMock(), receive=idle_receive)
    monkeypatch.setattr(camera, "_stream_access_allowed", check_after_revocation)
    monkeypatch.setattr(camera, "async_session", auth.async_session)
    monkeypatch.setattr(camera, "_STREAM_RECHECK_SECONDS", 0.025)
    monkeypatch.setattr(camera.websockets, "connect", mock_connect)
    acquire = AsyncMock(return_value="printer-fixture")
    release = AsyncMock()
    monkeypatch.setattr(camera.go2rtc_registry, "acquire", acquire)
    monkeypatch.setattr(camera.go2rtc_registry, "release", release)
    remove_stream = AsyncMock()
    if revoke_via == "printer":
        registration = camera.go2rtc_registry._Registration("printer-fixture", None)
        monkeypatch.setattr(camera.go2rtc_registry, "_registrations", {printer.id: registration})
        monkeypatch.setattr(camera.go2rtc_registry.go2rtc_client, "remove_stream", remove_stream)
    task = asyncio.create_task(camera.camera_mse_stream(websocket, printer.id, token=share["token"]))
    try:
        await asyncio.wait_for(connected.wait(), timeout=2)
        websocket.accept.assert_awaited_once()
        path = f"/api/v1/auth/tokens/{share['id']}" if revoke_via == "share" else f"/api/v1/printers/{printer.id}"
        response = await async_client.delete(path, headers=headers)
        assert response.status_code in (200, 204)
        revoked.set()
        await asyncio.wait_for(task, timeout=2)
        websocket.close.assert_awaited_once_with(code=4401 if revoke_via == "share" else 4404)
        release.assert_awaited_once_with(printer.id)
        if revoke_via == "printer":
            assert not camera.go2rtc_registry.is_registered(printer.id)
            remove_stream.assert_awaited_once_with("printer-fixture")
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
