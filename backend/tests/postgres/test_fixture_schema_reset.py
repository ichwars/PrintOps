"""Verify data cleanup and recovery from test DDL on the disposable database."""

import pytest
from sqlalchemy import text

from backend.tests.conftest import TEST_PG_URL, _pg_fixture_schema

pytestmark = pytest.mark.skipif(TEST_PG_URL is None, reason="requires the PostgreSQL fixture database")


async def test_resets_rows_and_identity_without_recreating_the_table(test_engine, printer_factory, db_session):
    old = await printer_factory()
    assert old.id == 1
    await db_session.rollback()  # The factory refresh opens a read transaction.
    async with test_engine.begin() as conn:
        relation = text("SELECT 'public.printers'::regclass::oid")
        before = await conn.scalar(relation)
        await _pg_fixture_schema.reset(conn)
        assert await conn.scalar(relation) == before
        assert await conn.scalar(text("SELECT count(*) FROM printers")) == 0
    assert (await printer_factory()).id == 1


@pytest.mark.parametrize(
    "change, remains",
    [
        (
            "ALTER TABLE printers ADD COLUMN fixture_only integer",
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'printers' AND column_name = 'fixture_only'",
        ),
        (
            "CREATE INDEX fixture_only ON printers (name)",
            "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'fixture_only'",
        ),
        (
            "CREATE FUNCTION fixture_only() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
            "SELECT to_regprocedure('public.fixture_only()')",
        ),
    ],
)
async def test_restores_original_schema_after_a_test_changes_it(test_engine, change, remains):
    async with test_engine.begin() as conn:
        await conn.execute(text(change))
        await _pg_fixture_schema.reset(conn)
        assert await conn.scalar(text(remains)) is None
