"""A restored SQLite allocation floor survives when new IDs are issued on PostgreSQL."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.identity_sequence_migration import raise_postgres_identity_sequences


async def test_postgres_raises_sequences_past_orphans_and_sqlite_counters():
    dsn = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not dsn:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")
    engine = create_async_engine(dsn)
    schema = "identity_test_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            await conn.exec_driver_sql("CREATE TABLE printers (id SERIAL PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE users (id SERIAL PRIMARY KEY, allowed_printer_ids JSON)")
            await conn.exec_driver_sql("CREATE TABLE print_log_entries (printer_id INTEGER)")
            await conn.exec_driver_sql("INSERT INTO users (id, allowed_printer_ids) VALUES (3, '[74]')")
            await conn.exec_driver_sql("INSERT INTO print_log_entries VALUES (75)")

            await raise_postgres_identity_sequences(conn, MetaData(), {"users": 49, "printers": 60})
            user_id = (await conn.exec_driver_sql("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar_one()
            printer_id = (await conn.exec_driver_sql("INSERT INTO printers DEFAULT VALUES RETURNING id")).scalar_one()
            assert user_id == 50
            assert printer_id == 76

            await conn.exec_driver_sql("DELETE FROM printers")
            await raise_postgres_identity_sequences(conn, MetaData(), {"printers": 2})
            next_id = (await conn.exec_driver_sql("INSERT INTO printers DEFAULT VALUES RETURNING id")).scalar_one()
            assert next_id == 77
            await conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await engine.dispose()
