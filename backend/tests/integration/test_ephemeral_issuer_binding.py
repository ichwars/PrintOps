"""Derived credentials cannot be used after the issuing session or key ends."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.auth import generate_api_key, verify_media_token, verify_websocket_token
from backend.app.core.auth_ephemeral_migration import migrate_auth_ephemeral_columns
from backend.app.models.api_key import APIKey
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.long_lived_token import LongLivedToken
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def mint(client, path, headers):
    response = await client.post(path, headers=headers)
    assert response.status_code == 200
    return response.json()["token"]


async def another_login(client):
    response = await client.post("/api/v1/auth/login", json={"username": "tokenadmin", "password": "AdminPass1!"})
    assert response.status_code == 200
    return bearer(response.json()["access_token"])


async def test_dashboard_and_media_credentials_follow_only_their_issuing_session(async_client):
    first = bearer(await _setup_admin(async_client))
    second = await another_login(async_client)
    credentials = []
    for path, verify in (
        ("/api/v1/auth/ws-token", verify_websocket_token),
        ("/api/v1/auth/media-token", verify_media_token),
    ):
        first_derived = await mint(async_client, path, first)
        second_derived = await mint(async_client, path, second)
        assert await verify(first_derived) == "tokenadmin"
        assert await verify(second_derived) == "tokenadmin"
        credentials.append((verify, first_derived, second_derived))

    assert (await async_client.post("/api/v1/auth/logout", headers=first)).status_code == 200
    for verify, first_derived, second_derived in credentials:
        assert await verify(first_derived) is None
        assert await verify(second_derived) == "tokenadmin"


async def test_key_websocket_credential_is_rejected_after_key_material_changes(async_client, db_session):
    await _setup_admin(async_client)
    secret, key_hash, prefix = generate_api_key()
    key = APIKey(name="Fixture", key_hash=key_hash, key_prefix=prefix, enabled=True, can_read_status=True)
    db_session.add(key)
    await db_session.commit()
    issued = await mint(async_client, "/api/v1/auth/ws-token", {"X-API-Key": secret})
    assert await verify_websocket_token(issued) == ""

    replacement, key.key_hash, key.key_prefix = generate_api_key()
    await db_session.commit()
    assert await verify_websocket_token(issued) is None
    replacement_token = await mint(async_client, "/api/v1/auth/ws-token", {"X-API-Key": replacement})
    assert await verify_websocket_token(replacement_token) == ""


async def test_email_setup_cannot_be_confirmed_from_a_new_session_after_logout(async_client, db_session):
    first = bearer(await _setup_admin(async_client))
    second = await another_login(async_client)
    admin = await db_session.scalar(select(User).where(User.username == "tokenadmin"))
    admin.email = "fixture@example.invalid"
    await db_session.commit()
    with (
        patch("backend.app.api.routes.mfa.get_smtp_settings", AsyncMock(return_value={"fixture": True})),
        patch("backend.app.api.routes.mfa.send_email"),
        patch("backend.app.api.routes.mfa.secrets.randbelow", return_value=123456),
    ):
        response = await async_client.post("/api/v1/auth/2fa/email/enable", headers=first)
    assert response.status_code == 200
    setup = {"setup_token": response.json()["setup_token"], "code": "123456"}

    assert (await async_client.post("/api/v1/auth/logout", headers=first)).status_code == 200
    response = await async_client.post("/api/v1/auth/2fa/email/enable/confirm", json=setup, headers=second)
    assert response.status_code == 400
    response = await async_client.get("/api/v1/auth/2fa/status", headers=second)
    assert response.json()["email_otp_enabled"] is False


async def test_old_camwall_share_cannot_belong_to_a_newer_user(async_client, db_session):
    headers = bearer(await _setup_admin(async_client))
    created = await async_client.post(
        "/api/v1/auth/tokens", headers=headers, json={"name": "Old share", "scope": "camwall", "expires_in_days": 1}
    )
    assert created.status_code == 201
    share = await db_session.get(LongLivedToken, created.json()["id"])
    params = {"token": created.json()["token"]}
    assert (await async_client.get("/api/v1/camwall/printers", params=params)).status_code == 200
    share.created_at -= timedelta(days=1)
    await db_session.commit()
    assert (await async_client.get("/api/v1/camwall/printers", params=params)).status_code == 401


async def test_unbound_legacy_tokens_are_rejected_in_authenticated_mode(async_client, db_session):
    await _setup_admin(async_client)
    for token_type in (TokenType.WEBSOCKET, TokenType.MEDIA):
        db_session.add(
            AuthEphemeralToken(
                token=token_type.value,
                token_type=token_type,
                username="tokenadmin",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            )
        )
    await db_session.commit()
    assert await verify_websocket_token("websocket") is None
    assert await verify_media_token("media") is None


async def test_ephemeral_migration_keeps_legacy_rows_and_adds_nullable_issuer_fields(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ephemeral-legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE auth_ephemeral_tokens (id INTEGER PRIMARY KEY, token VARCHAR(128))"
            )
            await conn.exec_driver_sql("INSERT INTO auth_ephemeral_tokens VALUES (1, 'fixture')")
            await migrate_auth_ephemeral_columns(conn)
            await migrate_auth_ephemeral_columns(conn)
            result = await conn.exec_driver_sql(
                "SELECT token, issuer_identity, issuer_jti, issuer_epoch FROM auth_ephemeral_tokens"
            )
            assert result.one() == ("fixture", None, None, None)
    finally:
        await engine.dispose()
