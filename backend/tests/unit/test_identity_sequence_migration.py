"""SQLite upgrades preserve data and never issue an ID retained by old state."""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, text
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateTable

from backend.app.core.identity_sequence_migration import IDENTITY_TABLES, migrate_sqlite_identity_sequences


def test_new_identity_tables_use_autoincrement():
    from backend.app.core.database import Base
    from backend.app.models import api_key, archive, long_lived_token, printer, user  # noqa: F401

    for table in IDENTITY_TABLES:
        ddl = str(CreateTable(Base.metadata.tables[table]).compile(dialect=dialect()))
        assert "PRIMARY KEY AUTOINCREMENT" in ddl


@pytest.mark.asyncio
async def test_sqlite_upgrade_preserves_legacy_columns_indexes_triggers_and_historical_ids(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("printers", metadata, Column("id", Integer, primary_key=True))
    Table("subscriptions", metadata, Column("printer_id", ForeignKey("printers.id")))
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, allowed_printer_ids TEXT)")
            await conn.exec_driver_sql(
                """CREATE TABLE printers (
                    id INTEGER NOT NULL, original_name TEXT DEFAULT '{"kind":"printer"}',
                    upper_name TEXT GENERATED ALWAYS AS (upper(original_name)) STORED, PRIMARY KEY (id)
                )"""
            )
            await conn.exec_driver_sql("CREATE INDEX printers_name ON printers (original_name)")
            await conn.exec_driver_sql("CREATE TABLE subscriptions (printer_id INTEGER REFERENCES printers(id))")
            await conn.exec_driver_sql("CREATE TABLE print_log_entries (printer_id INTEGER)")
            await conn.exec_driver_sql("CREATE TABLE printer_name_changes (printer_id INTEGER, name TEXT)")
            await conn.exec_driver_sql("CREATE VIEW printer_names AS SELECT id, original_name FROM printers")
            await conn.exec_driver_sql("""
                CREATE TRIGGER printer_changed AFTER UPDATE ON printers BEGIN
                    INSERT INTO printer_name_changes VALUES (NEW.id, NEW.original_name);
                END
            """)
            await conn.exec_driver_sql("INSERT INTO printers (id, original_name) VALUES (7, 'Original')")
            await conn.exec_driver_sql("INSERT INTO subscriptions VALUES (200)")
            await conn.exec_driver_sql("INSERT INTO print_log_entries VALUES (202)")
            await conn.exec_driver_sql("INSERT INTO users VALUES (5, '[205]')")
            await migrate_sqlite_identity_sequences(conn, metadata)
            await migrate_sqlite_identity_sequences(conn, metadata)

            original = (await conn.exec_driver_sql("SELECT * FROM printers")).one()
            assert original == (7, "Original", "ORIGINAL")
            assert (await conn.exec_driver_sql("SELECT * FROM printer_names")).one() == (7, "Original")
            assert any(row[1] == "printers_name" for row in await conn.exec_driver_sql("PRAGMA index_list(printers)"))
            assert (await conn.exec_driver_sql("PRAGMA foreign_key_list(subscriptions)")).one()[2] == "printers"
            await conn.exec_driver_sql("UPDATE printers SET original_name = 'Changed' WHERE id = 7")
            assert (await conn.exec_driver_sql("SELECT * FROM printer_name_changes")).one() == (7, "Changed")
            new_id = (await conn.exec_driver_sql("INSERT INTO printers DEFAULT VALUES RETURNING id")).scalar_one()
            assert new_id > 205
            await conn.execute(text("DELETE FROM printers WHERE id = :id"), {"id": new_id})
            await migrate_sqlite_identity_sequences(conn, metadata)
            next_id = (await conn.exec_driver_sql("INSERT INTO printers DEFAULT VALUES RETURNING id")).scalar_one()
            assert next_id > new_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_rebuild_rolls_back_earlier_tables_when_later_table_cannot_be_copied(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rollback.db'}")
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            await conn.exec_driver_sql("CREATE TABLE printers (id INTEGER PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE printers_identity_migration (id INTEGER)")
            await conn.exec_driver_sql("INSERT INTO users VALUES (2, 'Original')")
            with pytest.raises(OperationalError, match="already exists"):
                await migrate_sqlite_identity_sequences(conn, MetaData())
            ddl = (await conn.exec_driver_sql("SELECT sql FROM sqlite_schema WHERE name = 'users'")).scalar_one()
            assert "AUTOINCREMENT" not in ddl
            assert (await conn.exec_driver_sql("SELECT * FROM users")).one() == (2, "Original")
            assert (await conn.exec_driver_sql("PRAGMA legacy_alter_table")).scalar_one() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_uses_only_camera_token_provider_ids_as_key_references(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'credentials.db'}")
    try:
        async with engine.begin() as conn:
            for table in ("api_keys", "print_archives", "long_lived_tokens"):
                await conn.exec_driver_sql(f'CREATE TABLE "{table}" ("id" INTEGER PRIMARY KEY)')
            await conn.exec_driver_sql("CREATE TABLE auth_ephemeral_tokens (provider_id INTEGER, token_type TEXT)")
            await conn.exec_driver_sql(
                "INSERT INTO auth_ephemeral_tokens VALUES (160, 'camera_stream'), (170, 'websocket'), (300, 'oidc_state')"
            )
            await migrate_sqlite_identity_sequences(conn, MetaData())

            key_id = (await conn.exec_driver_sql("INSERT INTO api_keys DEFAULT VALUES RETURNING id")).scalar_one()
            assert key_id == 171
            for table in ("print_archives", "long_lived_tokens"):
                await conn.exec_driver_sql(f'INSERT INTO "{table}" (id) VALUES (40)')
                await conn.exec_driver_sql(f'DELETE FROM "{table}"')
                new_id = (await conn.exec_driver_sql(f'INSERT INTO "{table}" DEFAULT VALUES RETURNING id')).scalar_one()
                assert new_id == 41
    finally:
        await engine.dispose()
