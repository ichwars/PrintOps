"""Real token/route boundaries use software camera fixtures, never hardware."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _create_user, _login, _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def mint(client, allowed, scope="overlay"):
    admin = await _setup_admin(client)
    uid = await _create_user(client, admin, "boundaryviewer")
    owner = await _login(client, "boundaryviewer")
    headers = {"Authorization": f"Bearer {admin}"}
    update = await client.patch(f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": allowed})
    assert update.status_code == 200, update.text
    created = await client.post(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {owner}"},
        json={"name": "boundary", "scope": scope, "expires_in_days": 1},
    )
    assert created.status_code == 201
    return uid, headers, {"token": created.json()["token"]}


async def software_camera(*args, **kwargs):
    yield b"SOFTWARE_CAMERA_FRAME"


async def test_overlay_camera_http_scope_tracks_owner_changes(async_client, printer_factory):
    allowed = await printer_factory()
    denied = await printer_factory()
    uid, headers, params = await mint(async_client, [allowed.id])
    with (
        patch("backend.app.api.routes.camera.get_camera_source", return_value=None),
        patch("backend.app.services.external_camera.generate_mjpeg_stream", software_camera),
    ):
        response = await async_client.get(f"/api/v1/printers/{allowed.id}/camera/stream", params=params)
        assert response.status_code == 200
        assert response.content == b"SOFTWARE_CAMERA_FRAME"
        for suffix in ("stream", "snapshot", "plate-detection/references/0/thumbnail"):
            response = await async_client.get(f"/api/v1/printers/{denied.id}/camera/{suffix}", params=params)
            assert response.status_code == 403, suffix
        # A query parameter cannot replace the trusted path/token-owner binding.
        response = await async_client.get(
            f"/api/v1/printers/{denied.id}/camera/stream", params={**params, "printer_id": allowed.id, "user_id": 1}
        )
        assert response.status_code == 403
        await async_client.patch(f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": [denied.id]})
        assert (
            await async_client.get(f"/api/v1/printers/{allowed.id}/camera/stream", params=params)
        ).status_code == 403
        assert (await async_client.get(f"/api/v1/printers/{denied.id}/camera/stream", params=params)).status_code == 200


@pytest.mark.parametrize("scope", ["camera_stream", "camwall"])
async def test_other_camera_scope_contracts_remain_unchanged(async_client, printer_factory, scope):
    allowed = await printer_factory()
    other = await printer_factory()
    _, _, params = await mint(async_client, [allowed.id], scope)
    from backend.app.core.auth import verify_camera_stream_token

    assert await verify_camera_stream_token(params["token"])
    request, writer = await authenticate_rtsp(params["token"], other.id)
    assert request is not None and request.token == params["token"]
    writer.write.assert_not_called()
    with (
        patch("backend.app.api.routes.camera.get_camera_source", return_value=None),
        patch("backend.app.services.external_camera.generate_mjpeg_stream", software_camera),
    ):
        assert (await async_client.get(f"/api/v1/printers/{other.id}/camera/stream", params=params)).status_code == 200


async def test_mse_and_unbound_rtsp_reject_overlay_outside_scope(async_client, printer_factory):
    from backend.app.api.routes.camera import camera_mse_stream

    allowed = await printer_factory()
    denied = await printer_factory()
    _, _, params = await mint(async_client, [allowed.id])
    # Invoke the actual WebSocket handler with an inert socket: no external relay.
    from backend.app.core import auth

    with (
        patch("backend.app.api.routes.camera.async_session", auth.async_session),
        patch("backend.app.api.routes.camera.get_camera_source", return_value=None),
    ):
        for printer, expected in ((denied, 4401), (allowed, 4404)):
            socket = AsyncMock()
            await camera_mse_stream(socket, printer.id, token=params["token"])
            socket.close.assert_awaited_once_with(code=expected)
            socket.accept.assert_not_awaited()
    request, writer = await authenticate_rtsp(params["token"], allowed.id)
    assert request is None
    assert b"401 Unauthorized" in writer.write.call_args.args[0]
    # Explicit rejection rather than a no-token Digest challenge proves parsing.
    assert b"WWW-Authenticate" not in writer.write.call_args.args[0]


async def authenticate_rtsp(token, printer_id):
    from backend.app.services.rtsp_auth_proxy import _authenticate

    reader = asyncio.StreamReader()
    reader.feed_data(
        f"DESCRIBE rtsp://localhost/printer-{printer_id} RTSP/1.0\r\nCSeq: 1\r\n"
        f'Authorization: Digest username="{token}"\r\n\r\n'.encode()
    )
    reader.feed_eof()
    writer = MagicMock()
    writer.drain = AsyncMock()
    return await _authenticate(reader, writer), writer


async def test_delete_recreate_restart_and_api_roundtrip_do_not_transfer_grant(
    async_client, printer_factory, db_session, test_engine
):
    from backend.app.core.database import init_db

    # Actual startup establishes the one-time compatibility marker before edits.
    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    original = await printer_factory()
    uid, headers, params = await mint(async_client, [original.id])
    original_id = original.id
    with patch("backend.app.api.routes.printers.printer_manager.disconnect_printer"):
        deleted = await async_client.delete(f"/api/v1/printers/{original_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    db_session.expunge(original)
    # A stale edit/create payload cannot reinstall the grant before ID reuse.
    stale = await async_client.patch(
        f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": [original_id]}
    )
    assert stale.status_code == 400
    stale_create = await async_client.post(
        "/api/v1/users/",
        headers=headers,
        json={"username": "staleviewer", "password": "ValidPassword123!", "allowed_printer_ids": [original_id]},
    )
    assert stale_create.status_code == 400
    replacement = await printer_factory(name="Unrelated replacement")
    assert replacement.id == original_id  # Exercise actual SQLite reuse.
    response = await async_client.get(f"/api/v1/users/{uid}", headers=headers)
    assert response.json()["allowed_printer_ids"] == []
    updated = await async_client.patch(f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": []})
    assert updated.json()["allowed_printer_ids"] == []
    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    response = await async_client.get(f"/api/v1/printers/{replacement.id}/overlay-status", params=params)
    assert response.status_code == 403
    assert (
        await async_client.get(f"/api/v1/printers/{replacement.id}/camera/stream", params=params)
    ).status_code == 403


async def test_deletion_preserves_other_grants_and_unrestricted_users(async_client, printer_factory, db_session):
    survivor = await printer_factory()
    removed = await printer_factory()
    uid, headers, _ = await mint(async_client, [survivor.id, removed.id])
    with patch("backend.app.api.routes.printers.printer_manager.disconnect_printer"):
        assert (await async_client.delete(f"/api/v1/printers/{removed.id}", headers=headers)).status_code == 200
    users = (await db_session.execute(select(User).execution_options(populate_existing=True))).scalars().all()
    assert next(user for user in users if user.id == uid).allowed_printer_ids == [survivor.id]
    assert next(user for user in users if user.role == "admin").allowed_printer_ids is None


async def test_explicit_empty_scope_and_invalid_grants_on_user_create_update(async_client, printer_factory):
    printer = await printer_factory()
    uid, headers, params = await mint(async_client, [])
    assert (await async_client.get(f"/api/v1/printers/{printer.id}/overlay-status", params=params)).status_code == 403
    data = {"username": "emptyviewer", "password": "ValidPassword123!", "allowed_printer_ids": []}
    created = await async_client.post("/api/v1/users/", headers=headers, json=data)
    assert created.status_code == 201, created.text
    assert created.json()["allowed_printer_ids"] == []
    invalid_id = printer.id + 12345
    bad_update = await async_client.patch(
        f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": [invalid_id]}
    )
    assert bad_update.status_code == 400
    bad_create = await async_client.post(
        "/api/v1/users/",
        headers=headers,
        json={**data, "username": "invalidviewer", "allowed_printer_ids": [invalid_id]},
    )
    assert bad_create.status_code == 400
    # Only an explicit admin choice of null restores unrestricted access.
    restored = await async_client.patch(f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": None})
    assert restored.json()["allowed_printer_ids"] is None
    assert (await async_client.get(f"/api/v1/printers/{printer.id}/overlay-status", params=params)).status_code == 200


async def test_startup_legacy_empty_scope_is_compatible_only_once(async_client, db_session, test_engine):
    from backend.app.core.database import init_db

    legacy = User(username="legacyviewer", password_hash="unused", role="user", allowed_printer_ids=[])
    db_session.add(legacy)
    await db_session.commit()
    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    await db_session.refresh(legacy)
    assert legacy.allowed_printer_ids is None  # Historical [] meant unrestricted.
    legacy.allowed_printer_ids = []  # New intentional deny-all state.
    await db_session.commit()
    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    await db_session.refresh(legacy)
    assert legacy.allowed_printer_ids == []


async def test_settings_reset_preserves_deny_all_migration_history(
    async_client, printer_factory, db_session, test_engine
):
    from backend.app.api.routes.auth import set_auth_enabled
    from backend.app.api.routes.settings import DEFAULT_SETTINGS
    from backend.app.core.database import init_db
    from backend.app.models.settings import Settings

    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    printer = await printer_factory()
    uid, headers, params = await mint(async_client, [])
    changed = await async_client.put("/api/v1/settings/", headers=headers, json={"currency": "JPY"})
    assert changed.status_code == 200
    reset = await async_client.post("/api/v1/settings/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["currency"] == DEFAULT_SETTINGS.currency
    assert "migration_user_printer_scope_deny_all_v1" not in reset.json()
    with patch("backend.app.core.database.engine", test_engine):
        await init_db()
    owner = await db_session.get(User, uid, populate_existing=True)
    assert owner.allowed_printer_ids == []
    marker = await db_session.scalar(select(Settings).where(Settings.key == "migration_user_printer_scope_deny_all_v1"))
    assert marker is not None
    # Public reset retains its established auth-off defaults. Restore auth in
    # the isolated fixture to observe token authorization, without changing reset.
    await set_auth_enabled(db_session, True)
    await db_session.commit()
    assert (await async_client.get(f"/api/v1/printers/{printer.id}/overlay-status", params=params)).status_code == 403
