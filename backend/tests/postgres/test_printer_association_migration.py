"""Exercise the old SET NULL constraints and JSONB scopes on PostgreSQL."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.printer_associations import repair_deleted_printer_associations


async def test_postgres_repairs_scopes_and_never_detaches_bound_resources():
    url = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not url:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")

    engine = create_async_engine(url)
    schema = f"printer_association_{uuid4().hex}"
    tables = {
        "notification_providers": "printer_id",
        "smart_plugs": "printer_id",
        "virtual_printers": "target_printer_id",
    }
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("CREATE TABLE printers (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, printer_ids JSONB)"))
            await conn.execute(text("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)"))
            await conn.execute(text("INSERT INTO printers VALUES (1), (2)"))
            await conn.execute(text("""INSERT INTO api_keys VALUES (1,'[]'), (2,'[1,999]'), (3,'[999]'), (4,NULL)"""))
            await conn.execute(text("INSERT INTO settings VALUES ('obico_enabled_printers', '[1,999]')"))

            for table, column in tables.items():
                await conn.execute(
                    text(
                        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, "
                        f"{column} INTEGER REFERENCES printers(id) ON DELETE SET NULL)"
                    )
                )
                await conn.execute(text(f"INSERT INTO {table} VALUES (1,1), (2,2), (3,NULL)"))

            await repair_deleted_printer_associations(conn)
            await repair_deleted_printer_associations(conn)
            assert (await conn.execute(text("SELECT printer_ids FROM api_keys ORDER BY id"))).scalars().all() == [
                [],
                [1],
                [],
                None,
            ]
            assert await conn.scalar(text("SELECT value FROM settings WHERE key='obico_enabled_printers'")) == "[1]"

            await conn.execute(text("DELETE FROM printers WHERE id=1"))
            for table, column in tables.items():
                assert (await conn.execute(text(f"SELECT id,{column} FROM {table} ORDER BY id"))).all() == [
                    (2, 2),
                    (3, None),
                ]
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await engine.dispose()
