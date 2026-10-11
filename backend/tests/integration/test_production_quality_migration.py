"""Exercise an actual legacy SQLite upgrade and PostgreSQL DDL selection."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core import database


async def test_legacy_sqlite_upgrade_is_repeatable_and_guards_part_counts(monkeypatch):
    monkeypatch.setattr(database, "is_sqlite", lambda: True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            for statement in (
                "CREATE TABLE projects(id INTEGER PRIMARY KEY)",
                "CREATE TABLE print_archives(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE print_log_entries(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE print_queue(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE notification_providers(id INTEGER PRIMARY KEY)",
                "INSERT INTO print_log_entries(id,status) VALUES(1,'completed')",
            ):
                await conn.execute(text(statement))
            await database._migrate_production_quality(conn)
            await database._migrate_production_quality(conn)
            row = (
                await conn.execute(
                    text(
                        "SELECT quantity, confirm_requested, good_quantity, reject_quantity FROM print_log_entries WHERE id=1"
                    )
                )
            ).one()
            assert tuple(row) == (1, 0, None, None), "legacy completed runs must never become pending inspections"
            await conn.execute(
                text("UPDATE print_log_entries SET quantity=4,good_quantity=3,reject_quantity=1 WHERE id=1")
            )
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.execute(
                        text("UPDATE print_log_entries SET good_quantity=4,reject_quantity=1 WHERE id=1")
                    )
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.execute(
                        text(
                            "INSERT INTO print_log_entries(id,status,quantity,good_quantity,reject_quantity) VALUES(2,'completed',1,-1,2)"
                        )
                    )
    finally:
        await engine.dispose()


async def test_postgresql_migration_uses_boolean_timestamp_and_check_constraint(monkeypatch):
    statements = []

    async def capture(_connection, statement):
        statements.append(statement)

    monkeypatch.setattr(database, "is_sqlite", lambda: False)
    monkeypatch.setattr(database, "_safe_execute", capture)
    await database._migrate_production_quality(object())
    assert any("confirm_requested BOOLEAN DEFAULT FALSE" in statement for statement in statements)
    assert any("confirm_token_expires_at TIMESTAMP" in statement for statement in statements)
    assert any("ADD CONSTRAINT ck_print_log_quality_quantities CHECK" in statement for statement in statements)
    assert any("CREATE UNIQUE INDEX" in statement and "confirm_token_hash" in statement for statement in statements)
    assert all(
        "DATETIME" not in statement and "DEFAULT 0" not in statement and "TRIGGER" not in statement
        for statement in statements
    )


async def test_real_postgresql_legacy_upgrade_constraints_and_repeatability(monkeypatch):
    dsn = os.environ.get("W18_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set W18_TEST_POSTGRES_DSN to an isolated PostgreSQL test database")
    monkeypatch.setattr(database, "is_sqlite", lambda: False)
    engine = create_async_engine(dsn)
    schema = "w18_quality_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for statement in (
                "CREATE TABLE projects(id INTEGER PRIMARY KEY)",
                "CREATE TABLE print_archives(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE print_log_entries(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE print_queue(id INTEGER PRIMARY KEY, status TEXT)",
                "CREATE TABLE notification_providers(id INTEGER PRIMARY KEY)",
                "INSERT INTO print_log_entries(id,status) VALUES(1,'completed')",
            ):
                await conn.execute(text(statement))
            await database._migrate_production_quality(conn)
            await database._migrate_production_quality(conn)
            row = (
                await conn.execute(
                    text(
                        "SELECT quantity, confirm_requested, good_quantity, reject_quantity FROM print_log_entries WHERE id=1"
                    )
                )
            ).one()
            assert tuple(row) == (1, False, None, None)
            await conn.execute(
                text(
                    "UPDATE print_log_entries SET quantity=4,good_quantity=3,reject_quantity=1,confirm_token_hash='hash' WHERE id=1"
                )
            )
            for statement in (
                "UPDATE print_log_entries SET good_quantity=4,reject_quantity=1 WHERE id=1",
                "INSERT INTO print_log_entries(id,status,quantity,good_quantity,reject_quantity) VALUES(2,'completed',1,-1,2)",
                "UPDATE print_log_entries SET quantity=NULL WHERE id=1",
                "INSERT INTO print_log_entries(id,status,confirm_token_hash) VALUES(2,'completed','hash')",
                "UPDATE print_log_entries SET project_id=100 WHERE id=1",
            ):
                with pytest.raises(IntegrityError):
                    async with conn.begin_nested():
                        await conn.execute(text(statement))
            await conn.execute(text("INSERT INTO projects(id) VALUES(1)"))
            await conn.execute(text("UPDATE print_log_entries SET project_id=1 WHERE id=1"))
            await conn.execute(text("DELETE FROM projects WHERE id=1"))
            assert (
                await conn.execute(text("SELECT project_id FROM print_log_entries WHERE id=1"))
            ).scalar_one() is None
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
