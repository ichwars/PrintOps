"""PostgreSQL upgrades old cascade rules without deleting usage history."""

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.spool_usage_migration import migrate_spool_usage_history


async def test_postgres_spool_usage_survives_spool_and_archive_deletes_after_legacy_upgrade():
    dsn = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not dsn:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")
    engine = create_async_engine(dsn)
    schema = "spool_usage_test_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            await conn.exec_driver_sql("CREATE TABLE spool (id SERIAL PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE print_archives (id SERIAL PRIMARY KEY)")
            await conn.exec_driver_sql("""
                CREATE TABLE spool_usage_history (
                    id SERIAL PRIMARY KEY, spool_id INTEGER NOT NULL,
                    cost DOUBLE PRECISION, archive_id INTEGER REFERENCES print_archives(id),
                    CONSTRAINT legacy_cascade FOREIGN KEY (spool_id) REFERENCES spool (id) ON DELETE CASCADE
                )
            """)
            await conn.exec_driver_sql("INSERT INTO spool DEFAULT VALUES")
            await conn.exec_driver_sql("INSERT INTO print_archives DEFAULT VALUES")
            await conn.exec_driver_sql(
                "INSERT INTO spool_usage_history (spool_id, cost, archive_id) VALUES (1, 2.5, 1)"
            )
            await migrate_spool_usage_history(conn)
            await migrate_spool_usage_history(conn)

            await conn.exec_driver_sql("DELETE FROM spool WHERE id = 1")
            await conn.exec_driver_sql("DELETE FROM print_archives WHERE id = 1")
            history = (await conn.exec_driver_sql("SELECT spool_id, cost, archive_id FROM spool_usage_history")).one()
            assert history == (None, 2.5, None)
            next_spool = (await conn.exec_driver_sql("INSERT INTO spool DEFAULT VALUES RETURNING id")).scalar_one()
            assert next_spool == 2
            await conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await engine.dispose()
