"""Long imports revalidate the account, and old MFA settings are retired on PostgreSQL."""

import os
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.core.account_retirement import AccountSnapshot, repair_deleted_accounts, require_current_account


async def test_postgres_account_revalidation_and_mfa_cleanup():
    dsn = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not dsn:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")

    engine = create_async_engine(dsn)
    schema = f"account_retirement_{uuid4().hex}"
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(
                text(
                    "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, connected_identity TEXT, "
                    "created_at TIMESTAMP, is_active BOOLEAN)"
                )
            )
            await conn.execute(text("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)"))
            await conn.execute(text("INSERT INTO users VALUES (7,'same-name','current',CURRENT_TIMESTAMP,true)"))
            await conn.execute(
                text(
                    "INSERT INTO settings VALUES ('user_7_email_2fa_enabled','true'), ('user_99_email_2fa_enabled','true')"
                )
            )
            await repair_deleted_accounts(conn)
            assert (await conn.scalars(text("SELECT key FROM settings"))).all() == ["user_7_email_2fa_enabled"]

            async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint") as db:
                original = AccountSnapshot(7, "deleted", "same-name", datetime(2024, 1, 1))
                with pytest.raises(HTTPException) as error:
                    await require_current_account(db, original)
                assert error.value.status_code == 401
                current = AccountSnapshot(7, "current", "same-name", datetime(2024, 1, 1))
                assert await require_current_account(db, current) == 7

            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await engine.dispose()
