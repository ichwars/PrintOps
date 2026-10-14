"""Archive owner generation is stamped on real ORM writes; legacy ambiguity stays null."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core import database
from backend.app.core.archive_owner_identity import migrate_archive_owner_identity
from backend.app.core.permissions import Permission
from backend.app.models.archive import PrintArchive
from backend.app.models.group import Group
from backend.app.models.user import User
from backend.app.services import telegram_quality as quality
from backend.tests.integration.test_telegram_quality import context, reaction


async def test_model_insert_relationship_and_owner_change(db_session):
    first = User(username="first", groups=[])
    second = User(username="second", groups=[])
    db_session.add_all([first, second])
    await db_session.flush()
    archive = PrintArchive(filename="parts", file_path="/none", file_size=1, created_by=first)
    db_session.add(archive)
    await db_session.commit()
    assert archive.created_by_identity == first.connected_identity
    archive.created_by_id = second.id
    await db_session.commit()
    assert archive.created_by_identity == second.connected_identity
    archive.created_by_id = None
    await db_session.commit()
    assert archive.created_by_identity is None


async def test_replacement_explicitly_trusted_cannot_inherit_archive(context):
    db, user, archive, run, provider, config = context
    old_id = user.id
    old_identity = user.connected_identity
    await db.delete(user)
    await db.commit()
    replacement = User(
        username="replacement",
        role="user",
        groups=[Group(name="own", permissions=[Permission.ARCHIVES_UPDATE_OWN.value])],
    )
    db.add(replacement)
    await db.commit()
    assert replacement.id == old_id and replacement.connected_identity != old_identity
    await quality.configure(db, provider, False, [])
    await db.commit()
    await quality.configure(db, provider, True, [{"actor_id": 42, "user_id": replacement.id}])
    await db.commit()
    assert await quality.bind_message(db, provider, {"message_id": 13, "chat_id": -100}, archive.id, run.id)
    await db.commit()
    assert archive.created_by_identity == old_identity
    assert not await quality.apply_reaction(db, config.id, reaction(message_id=13))


@pytest.mark.parametrize("role,accepted", [("admin", True), ("user", False)])
async def test_legacy_ambiguous_archive_requires_all_scope(context, role, accepted):
    db, user, archive, run, provider, config = context
    archive.created_by_identity = None
    user.role = role
    user.groups = [Group(name="legacy-own", permissions=[Permission.ARCHIVES_UPDATE_OWN.value])]
    await db.commit()
    assert await quality.bind_message(db, provider, {"message_id": 13, "chat_id": -100}, archive.id, run.id)
    await db.commit()
    assert await quality.apply_reaction(db, config.id, reaction(message_id=13)) is accepted


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
async def test_owner_generation_migration_repeatable_no_legacy_backfill(monkeypatch, dialect):
    dsn = "sqlite+aiosqlite:///:memory:" if dialect == "sqlite" else os.environ.get("F01_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set F01_TEST_POSTGRES_DSN for isolated PostgreSQL migration verification")
    monkeypatch.setattr(database, "is_sqlite", lambda: dialect == "sqlite")
    engine = create_async_engine(dsn)
    schema = "o17_owner_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            if dialect == "postgresql":
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("CREATE TABLE print_archives (id INTEGER PRIMARY KEY, created_by_id INTEGER)"))
            await conn.execute(text("INSERT INTO print_archives VALUES (1,1)"))
            await migrate_archive_owner_identity(conn, database._safe_execute)
            assert (await conn.execute(text("SELECT created_by_identity FROM print_archives"))).scalar_one() is None
            await conn.execute(text("UPDATE print_archives SET created_by_identity='persisted-owner-generation'"))
            await migrate_archive_owner_identity(conn, database._safe_execute)
            assert (
                await conn.execute(text("SELECT created_by_identity FROM print_archives"))
            ).scalar_one() == "persisted-owner-generation"
    finally:
        if dialect == "postgresql":
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
