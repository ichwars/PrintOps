"""Login steps can't outlive a password, account or 2FA security change."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.app.core.auth_issuers import bind_login_step
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize(
    ("token_type", "path", "body_key", "payload", "expected"),
    [
        (TokenType.PRE_AUTH, "/api/v1/auth/2fa/email/send", "pre_auth_token", {}, 401),
        (TokenType.OIDC_EXCHANGE, "/api/v1/auth/oidc/exchange", "oidc_token", {}, 401),
        (
            TokenType.PASSWORD_RESET,
            "/api/v1/auth/forgot-password/confirm",
            "token",
            {"new_password": "NewAdminPass1!"},
            400,
        ),
    ],
)
@pytest.mark.parametrize("bound", [False, True])
async def test_changed_security_epoch_rejects_every_login_step(
    async_client, db_session, token_type, path, body_key, payload, expected, bound
):
    await _setup_admin(async_client)
    user = await db_session.scalar(select(User).where(User.username == "tokenadmin"))
    earlier = datetime.now(timezone.utc).replace(microsecond=100_000) - timedelta(hours=1)
    user.created_at = earlier - timedelta(days=1)
    user.password_changed_at = earlier
    await db_session.commit()

    issued = AuthEphemeralToken(
        token="fixture-" + token_type.value,
        token_type=token_type,
        username=user.username,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        created_at=earlier.replace(microsecond=200_000),
    )
    if bound:
        bind_login_step(issued, user)
        # Simulate saving the token after the account changed, using an older
        # already-verified account snapshot.
        issued.created_at = earlier.replace(microsecond=900_000)
    token = issued.token
    db_session.add(issued)
    user.password_changed_at = earlier.replace(microsecond=500_000)
    await db_session.commit()

    with patch("backend.app.api.routes.mfa.send_email") as send_email:
        response = await async_client.post(path, json={**payload, body_key: token})
    assert response.status_code == expected
    assert "access_token" not in response.json()
    send_email.assert_not_called()
    if token_type in {TokenType.OIDC_EXCHANGE, TokenType.PASSWORD_RESET}:
        assert await db_session.scalar(select(AuthEphemeralToken.id).where(AuthEphemeralToken.token == token)) is None


async def test_pre_auth_proof_cannot_rebind_after_account_identity_changes(async_client, db_session):
    await _setup_admin(async_client)
    user = await db_session.scalar(select(User).where(User.username == "tokenadmin"))
    step = AuthEphemeralToken(
        token="fixture-pre-auth",
        token_type=TokenType.PRE_AUTH,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    bind_login_step(step, user)
    db_session.add(step)
    user.connected_identity = "a" * 32
    await db_session.commit()
    response = await async_client.post(
        "/api/v1/auth/2fa/verify",
        json={
            "pre_auth_token": "fixture-pre-auth",
            "code": "123456",
            "method": "totp",
        },
    )
    assert response.status_code == 401
    assert "Invalid or expired pre-auth token" in response.json()["detail"]
