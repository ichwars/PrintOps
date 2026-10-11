"""Legacy defaults must preserve existing photos on both supported databases."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core import database


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
async def test_legacy_photo_preference_upgrade_and_repeatability(monkeypatch, dialect, test_engine):
    dsn = "sqlite+aiosqlite:///:memory:" if dialect == "sqlite" else os.environ.get("F01_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set F01_TEST_POSTGRES_DSN to an isolated PostgreSQL test database")
    monkeypatch.setattr(database.settings, "database_url", dsn)
    monkeypatch.setattr(database, "is_sqlite", lambda: dialect == "sqlite")
    engine = create_async_engine(dsn)
    schema = "f01_photos_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            if dialect == "postgresql":
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            from backend.app.models.notification import NotificationProvider

            await conn.run_sync(database.Base.metadata.create_all)
            await conn.execute(
                NotificationProvider.__table__.insert().values(id=1, name="Legacy", provider_type="ntfy", config="{}")
            )
            await conn.execute(text("ALTER TABLE notification_providers DROP COLUMN attach_photo"))
            await database.run_migrations(conn)
            assert (
                await conn.execute(text("SELECT attach_photo FROM notification_providers WHERE id=1"))
            ).scalar_one() in (True, 1)
            await conn.execute(text("UPDATE notification_providers SET attach_photo=FALSE WHERE id=1"))
            await database.run_migrations(conn)
            assert (
                await conn.execute(text("SELECT attach_photo FROM notification_providers WHERE id=1"))
            ).scalar_one() in (False, 0)
            await conn.execute(
                NotificationProvider.__table__.insert().values(id=2, name="New", provider_type="ntfy", config="{}")
            )
            assert (
                await conn.execute(text("SELECT attach_photo FROM notification_providers WHERE id=2"))
            ).scalar_one() in (True, 1)
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.execute(text("UPDATE notification_providers SET attach_photo=NULL WHERE id=1"))
    finally:
        if dialect == "postgresql":
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
