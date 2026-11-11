"""Upgrade and bind auth timestamps with a non-UTC PostgreSQL session."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.auth_time import migrate_auth_timestamps
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.user import User
from backend.app.utils.local_time import utcnow_naive


async def test_legacy_auth_timestamps_convert_once_and_bind_utc():
    dsn = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not dsn:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")

    engine = create_async_engine(dsn)
    schema = f"auth_timestamps_{uuid4().hex}"
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
            await conn.execute(
                text(
                    "CREATE TABLE users (id INTEGER PRIMARY KEY, password_changed_at TIMESTAMPTZ, updated_at TIMESTAMP)"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE auth_ephemeral_tokens (id INTEGER PRIMARY KEY, token TEXT, token_type TEXT, "
                    "expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ)"
                )
            )
            await conn.execute(
                text("CREATE TABLE auth_rate_limit_events (id INTEGER PRIMARY KEY, occurred_at TIMESTAMPTZ)")
            )
            await conn.execute(text("INSERT INTO users VALUES (1,'2040-01-01T00:00:00Z','2020-01-01')"))
            await conn.execute(
                text("""
                    INSERT INTO auth_ephemeral_tokens VALUES
                      (1,'revocation','revoked_jti','2026-01-01T10:15:00+05:30','2026-01-01T10:14:00+05:30'),
                      (2,'old-flow','oidc_state','2026-01-01T10:15:00+05:30','2026-01-01T10:14:00+05:30')
                """)
            )
            await conn.execute(text("INSERT INTO auth_rate_limit_events VALUES (1, CURRENT_TIMESTAMP)"))

            before = utcnow_naive()
            await migrate_auth_timestamps(conn)
            assert await conn.scalar(select(User.password_changed_at)) >= before
            assert await conn.scalar(select(User.updated_at)) == datetime(2020, 1, 1)
            assert (await conn.execute(select(AuthEphemeralToken.token_type, AuthEphemeralToken.expires_at))).all() == [
                (TokenType.REVOKED_JTI.value, datetime(2026, 1, 1, 4, 45))
            ]
            assert await conn.scalar(text("SELECT count(*) FROM auth_rate_limit_events")) == 0

            aware = datetime(2026, 1, 2, 10, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
            await conn.execute(update(User).values(password_changed_at=aware, updated_at=User.updated_at))
            await conn.execute(
                insert(AuthEphemeralToken).values(
                    id=3, token="new-flow", token_type=TokenType.OIDC_STATE, expires_at=aware
                )
            )
            await migrate_auth_timestamps(conn)
            expected = datetime(2026, 1, 2, 4, 45)
            assert await conn.scalar(select(User.password_changed_at)) == expected
            assert (
                await conn.scalar(select(AuthEphemeralToken.expires_at).where(AuthEphemeralToken.id == 3)) == expected
            )
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await engine.dispose()
