"""Restore invalidates incomplete auth flows while retaining the logout blocklist."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.app.core.auth_sessions import invalidate_all_sessions
from backend.app.models.auth_ephemeral import AuthEphemeralToken, AuthRateLimitEvent, TokenType
from backend.app.models.user import User
from backend.app.utils.local_time import utcnow_naive


@pytest.mark.asyncio
async def test_restore_cutoff_invalidates_ephemeral_credentials(db_session):
    before = utcnow_naive()
    user = User(username="restored", password_changed_at=before - timedelta(days=1))
    expires = before + timedelta(minutes=5)
    db_session.add(user)
    db_session.add_all(
        [
            AuthEphemeralToken(token=kind.value, token_type=kind, expires_at=expires)
            for kind in (TokenType.REVOKED_JTI, TokenType.OIDC_STATE, TokenType.WEBSOCKET, TokenType.CAMERA_STREAM)
        ]
    )
    db_session.add(AuthRateLimitEvent(username=user.username, event_type="2fa_attempt"))
    await db_session.flush()
    await invalidate_all_sessions(await db_session.connection())
    await db_session.commit()

    await db_session.refresh(user)
    assert user.password_changed_at >= before
    assert (await db_session.scalars(select(AuthEphemeralToken.token_type))).all() == [TokenType.REVOKED_JTI.value]
    assert await db_session.scalar(select(AuthRateLimitEvent.id)) is None
