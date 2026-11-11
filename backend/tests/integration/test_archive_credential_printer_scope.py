"""Printer scope follows the credential accepted by each archive route."""

import pytest
from sqlalchemy import update

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token, _make_user, _mint_media_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def scoped_archives(async_client, db_session, printer_factory, archive_factory):
    visible_printer = await printer_factory(name="Visible printer")
    hidden_printer = await printer_factory(name="Hidden printer")
    visible = await archive_factory(visible_printer.id)
    hidden = await archive_factory(hidden_printer.id)
    admin = await _admin_token(async_client, "_archive_credential")
    jwt, user_id = await _make_user(
        async_client, admin, username="scoped_archive_reader", permissions=["archives:read_all", "printers:read"]
    )
    await db_session.execute(update(User).where(User.id == user_id).values(allowed_printer_ids=[visible_printer.id]))
    secret, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Scoped archive key",
            key_hash=key_hash,
            key_prefix=prefix,
            can_read_status=True,
            can_manage_archives=True,
            printer_ids=[visible_printer.id],
        )
    )
    await db_session.commit()
    return visible, hidden, admin, jwt, secret


async def test_media_scope_comes_from_the_media_token(async_client, scoped_archives):
    visible, hidden, admin, jwt, secret = scoped_archives
    user_media = await _mint_media_token(async_client, jwt)
    admin_media = await _mint_media_token(async_client, admin)

    def get_qr(archive_id, token, headers):
        return async_client.get(f"/api/v1/archives/{archive_id}/qrcode", params={"token": token}, headers=headers)

    admin_headers = {"Authorization": f"Bearer {admin}"}
    assert (await get_qr(visible.id, user_media, admin_headers)).status_code == 200
    assert (await get_qr(hidden.id, user_media, admin_headers)).status_code == 404
    assert (await get_qr(hidden.id, admin_media, {"X-API-Key": secret})).status_code == 200
    assert (await get_qr(visible.id, "invalid", admin_headers)).status_code == 401


@pytest.mark.parametrize("use_key", [False, True])
async def test_query_token_cannot_expand_header_archive_scope(async_client, scoped_archives, use_key):
    visible, hidden, admin, jwt, secret = scoped_archives
    media = await _mint_media_token(async_client, admin)
    headers = {"X-API-Key": secret} if use_key else {"Authorization": f"Bearer {jwt}"}
    allowed = await async_client.get(f"/api/v1/archives/{visible.id}", headers=headers, params={"token": media})
    denied = await async_client.get(f"/api/v1/archives/{hidden.id}", headers=headers, params={"token": media})
    assert allowed.status_code == 200
    assert denied.status_code == (403 if use_key else 404)


async def test_bearer_key_scope_is_enforced_after_invalid_x_api_key(async_client, scoped_archives):
    visible, hidden, _, _, secret = scoped_archives
    headers = {"X-API-Key": "invalid", "Authorization": f"Bearer {secret}"}
    visible_qr = await async_client.get(f"/api/v1/archives/{visible.id}/qrcode", headers=headers)
    hidden_qr = await async_client.get(f"/api/v1/archives/{hidden.id}/qrcode", headers=headers)
    hidden_patch = await async_client.patch(f"/api/v1/archives/{hidden.id}", headers=headers, json={"notes": "Denied"})
    assert visible_qr.status_code == 200
    assert hidden_qr.status_code == 403
    assert hidden_patch.status_code == 403


async def test_printer_media_uses_the_same_credential_for_printer_scope(async_client, scoped_archives):
    _, hidden, admin, jwt, secret = scoped_archives
    path = f"/api/v1/printers/{hidden.printer_id}/cover"
    response = await async_client.get(
        path, params={"token": await _mint_media_token(async_client, admin)}, headers={"X-API-Key": secret}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Printer not connected"

    response = await async_client.get(
        path,
        params={"token": await _mint_media_token(async_client, jwt)},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Printer not found"

    response = await async_client.get(path, headers={"X-API-Key": "invalid", "Authorization": f"Bearer {secret}"})
    assert response.status_code == 403
