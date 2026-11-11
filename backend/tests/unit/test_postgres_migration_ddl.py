"""Use PostgreSQL's idempotent DDL without changing other statements."""

import pytest

from backend.app.core.postgres_migration_ddl import idempotent_postgres_ddl


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        (
            '  ALTER TABLE IF EXISTS "Schema"."Table" ADD COLUMN "Field" INTEGER',
            '  ALTER TABLE IF EXISTS "Schema"."Table" ADD COLUMN IF NOT EXISTS "Field" INTEGER',
        ),
        (
            "CREATE UNIQUE INDEX queue_position ON print_queue (position)",
            "CREATE UNIQUE INDEX IF NOT EXISTS queue_position ON print_queue (position)",
        ),
        ("CREATE TABLE probe (id INT)", "CREATE TABLE IF NOT EXISTS probe (id INT)"),
        (
            "CREATE TABLE    IF NOT EXISTS probe (id INT)",
            "CREATE TABLE    IF NOT EXISTS probe (id INT)",
        ),
        (
            "ALTER TABLE probe ADD COLUMN   IF NOT EXISTS val INT",
            "ALTER TABLE probe ADD COLUMN   IF NOT EXISTS val INT",
        ),
        (
            "CREATE INDEX CONCURRENTLY probe_idx ON probe (id)",
            "CREATE INDEX CONCURRENTLY probe_idx ON probe (id)",
        ),
        ("ALTER TABLE probe RENAME COLUMN old TO new", "ALTER TABLE probe RENAME COLUMN old TO new"),
        ("UPDATE probe SET note = 'CREATE TABLE'", "UPDATE probe SET note = 'CREATE TABLE'"),
    ],
)
def test_rewrite_is_idempotent(statement, expected):
    assert idempotent_postgres_ddl(statement) == expected
    assert idempotent_postgres_ddl(expected) == expected
