"""Regression coverage for locale-independent PostgreSQL migrations (#142)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine


class _FakePostgresError(Exception):
    def __init__(self, sqlstate: str, message: str):
        super().__init__(message)
        self.sqlstate = sqlstate


def _pg_error(sqlstate: str, message: str, sql: str) -> ProgrammingError:
    return ProgrammingError(sql, {}, _FakePostgresError(sqlstate, message))


ADD_COLUMN = "ALTER TABLE pipeline_runs ADD COLUMN parent_run_id INTEGER"
RENAME_COLUMN = "ALTER TABLE pipeline_runs RENAME COLUMN old_name TO new_name"
CREATE_INDEX = "CREATE INDEX ix_pipeline_runs_parent ON pipeline_runs (parent_run_id)"


class TestMigrationErrorClassification:
    @pytest.mark.parametrize(
        "sqlstate,message,sql",
        [
            ("42701", 'столбец "parent_run_id" уже существует', ADD_COLUMN),
            ("42P07", 'отношение "pipeline_runs" уже существует', "CREATE TABLE pipeline_runs (id INTEGER)"),
            (
                "42710",
                'ограничение "ck_state" уже существует',
                "ALTER TABLE pipeline_runs ADD CONSTRAINT ck_state CHECK (id > 0)",
            ),
            ("23505", "doppelter Schlüssel verletzt Unique-Constraint", CREATE_INDEX),
        ],
    )
    def test_postgres_idempotency_uses_sqlstate_not_message(self, sqlstate: str, message: str, sql: str):
        from backend.app.core.database import _is_already_applied

        assert _is_already_applied(_pg_error(sqlstate, message, sql), sql) is True

    def test_undefined_column_is_idempotent_only_for_rename(self):
        from backend.app.core.database import _is_already_applied

        error = _pg_error("42703", 'столбец "old_name" не существует', RENAME_COLUMN)
        assert _is_already_applied(error, RENAME_COLUMN) is True
        assert _is_already_applied(error, CREATE_INDEX) is False

    @pytest.mark.parametrize("sqlstate", ["42P01", "42704", "42601"])
    def test_unexpected_postgres_errors_are_not_swallowed(self, sqlstate: str):
        from backend.app.core.database import _is_already_applied

        error = _pg_error(sqlstate, "already exists but this is a real failure", ADD_COLUMN)
        assert _is_already_applied(error, ADD_COLUMN) is False

    def test_sqlite_keeps_its_unlocalised_message_fallback(self):
        from backend.app.core.database import _is_already_applied

        duplicate = OperationalError(ADD_COLUMN, {}, Exception("duplicate column name: parent_run_id"))
        missing_table = OperationalError(ADD_COLUMN, {}, Exception("no such table: pipeline_runs"))
        assert _is_already_applied(duplicate, ADD_COLUMN) is True
        assert _is_already_applied(missing_table, ADD_COLUMN) is False

    def test_psycopg_pgcode_is_supported(self):
        from backend.app.core.db_dialect import sqlstate

        class _PsycopgError(Exception):
            pgcode = "42P07"

        error = ProgrammingError("CREATE TABLE issue_142 (id INTEGER)", {}, _PsycopgError())
        assert sqlstate(error) == "42P07"

    @pytest.mark.asyncio
    async def test_safe_execute_repeated_sqlite_migration_is_idempotent(self):
        from backend.app.core.database import _safe_execute

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE TABLE issue_142 (id INTEGER PRIMARY KEY)"))
                await _safe_execute(conn, "ALTER TABLE issue_142 ADD COLUMN value INTEGER")
                await _safe_execute(conn, "ALTER TABLE issue_142 ADD COLUMN value INTEGER")
                columns = {row[1] for row in await conn.execute(text("PRAGMA table_info(issue_142)"))}
        finally:
            await engine.dispose()

        assert columns == {"id", "value"}


class TestPostgresSessionTimezone:
    def test_sqlite_gets_no_connect_args(self, monkeypatch):
        from backend.app.core import database

        monkeypatch.setattr(database, "is_sqlite", lambda: True)
        assert database._resolve_connect_args() == {}

    def test_asyncpg_session_is_pinned_to_utc(self, monkeypatch):
        from backend.app.core import database

        monkeypatch.setattr(database, "is_sqlite", lambda: False)
        monkeypatch.setattr(
            database.settings,
            "database_url",
            "postgresql+asyncpg://user:password@postgres/printops",
            raising=False,
        )
        assert database._resolve_connect_args() == {"server_settings": {"timezone": "UTC"}}

    def test_other_postgres_drivers_use_libpq_options(self, monkeypatch):
        from backend.app.core import database

        monkeypatch.setattr(database, "is_sqlite", lambda: False)
        monkeypatch.setattr(
            database.settings,
            "database_url",
            "postgresql+psycopg://user:password@postgres/printops",
            raising=False,
        )
        assert database._resolve_connect_args() == {"options": "-c timezone=UTC"}

    def test_create_engine_passes_postgres_connect_args(self, monkeypatch):
        from backend.app.core import database

        captured: dict = {}

        def fake_create_async_engine(url: str, **kwargs):
            captured.update(kwargs)
            return create_async_engine("sqlite+aiosqlite:///:memory:")

        monkeypatch.setattr(database, "is_sqlite", lambda: False)
        monkeypatch.setattr(
            database.settings,
            "database_url",
            "postgresql+asyncpg://user:password@postgres/printops",
            raising=False,
        )
        monkeypatch.setattr(database, "create_async_engine", fake_create_async_engine)

        database._create_engine()

        assert captured["connect_args"] == {"server_settings": {"timezone": "UTC"}}

    @pytest.mark.asyncio
    async def test_sqlite_server_default_remains_naive_utc(self):
        metadata = MetaData()
        probe = Table(
            "issue_142_timezone_probe",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("created_at", DateTime, server_default=func.now()),
        )
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
                await conn.execute(probe.insert())
                stored = (await conn.execute(select(probe.c.created_at))).scalar_one()
        finally:
            await engine.dispose()

        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs(stored - utc_now) < timedelta(minutes=1)


@pytest.mark.asyncio
async def test_support_queue_age_uses_naive_utc(db_session, monkeypatch):
    from backend.app.api.routes import support
    from backend.app.models.print_queue import PrintQueueItem

    utc_now = datetime(2026, 9, 7, 7, 0, 0)
    monkeypatch.setattr(support, "utcnow_naive", lambda: utc_now)
    db_session.add(
        PrintQueueItem(
            printer_id=1,
            status="pending",
            created_at=utc_now - timedelta(seconds=30),
        )
    )
    await db_session.commit()

    info = await support._collect_queue_info(db_session)

    assert info["oldest_pending_age_seconds"] == 30
