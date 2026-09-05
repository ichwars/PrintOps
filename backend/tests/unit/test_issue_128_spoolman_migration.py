"""Upgrade coverage for durable active-print tracking columns."""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import run_migrations

LEGACY_TABLE = """
CREATE TABLE active_print_spoolman (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id INTEGER NOT NULL,
    archive_id INTEGER NOT NULL,
    filament_usage TEXT,
    ams_trays TEXT NOT NULL,
    slot_to_tray TEXT,
    layer_usage TEXT,
    filament_properties TEXT,
    tray_remain_start TEXT,
    UNIQUE(printer_id, archive_id)
)
"""

LEGACY_SESSION_TABLE = """
CREATE TABLE active_print_sessions (
    printer_id INTEGER PRIMARY KEY,
    print_name VARCHAR NOT NULL,
    started_at DATETIME NOT NULL,
    tray_now_at_start INTEGER NOT NULL,
    plate_id INTEGER,
    ams_mapping JSON,
    spool_assignments JSON,
    tray_remain_start JSON,
    tray_change_log JSON
)
"""


@pytest.fixture(autouse=True)
def force_sqlite_dialect(monkeypatch):
    from backend.app.core import database as database_module, db_dialect

    monkeypatch.setattr(db_dialect, "is_sqlite", lambda: True)
    monkeypatch.setattr(db_dialect, "is_postgres", lambda: False)
    monkeypatch.setattr(database_module, "is_sqlite", lambda: True)


def _register_every_model() -> None:
    import backend.app.models as models_pkg

    for module in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"backend.app.models.{module.name}")


@pytest.fixture
async def legacy_engine():
    from backend.app.core.database import Base

    _register_every_model()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE active_print_spoolman"))
        await conn.execute(text("DROP TABLE active_print_sessions"))
        await conn.execute(text(LEGACY_TABLE))
        await conn.execute(text(LEGACY_SESSION_TABLE))
        await conn.execute(
            text(
                "INSERT INTO active_print_spoolman (id, printer_id, archive_id, ams_trays, tray_remain_start) "
                'VALUES (1, 1, 42, \'{}\', \'{"0-0": {"remain": 80, "tray_uuid": "AAAA"}}\')'
            )
        )
        await conn.execute(
            text(
                "INSERT INTO active_print_sessions "
                "(printer_id, print_name, started_at, tray_now_at_start) "
                "VALUES (1, 'legacy-print', '2026-09-05 08:00:00', 2)"
            )
        )
    yield engine
    await engine.dispose()


async def test_upgrade_adds_nullable_column_and_preserves_active_print(legacy_engine):
    async with legacy_engine.begin() as conn:
        await run_migrations(conn)

    async with legacy_engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT tray_now_at_start, tray_remain_start FROM active_print_spoolman WHERE id = 1")
            )
        ).one()
        session_row = (
            await conn.execute(
                text(
                    "SELECT subtask_id, print_name, spoolman_owns_usage FROM active_print_sessions WHERE printer_id = 1"
                )
            )
        ).one()

    assert row[0] is None
    assert "AAAA" in row[1]
    assert session_row == (None, "legacy-print", None)


async def test_upgrade_is_idempotent(legacy_engine):
    async with legacy_engine.begin() as conn:
        await run_migrations(conn)
    async with legacy_engine.begin() as conn:
        await run_migrations(conn)

    async with legacy_engine.begin() as conn:
        columns = {row[1] for row in await conn.execute(text("PRAGMA table_info(active_print_spoolman)"))}

    assert "tray_now_at_start" in columns
    async with legacy_engine.begin() as conn:
        session_columns = {row[1] for row in await conn.execute(text("PRAGMA table_info(active_print_sessions)"))}
    assert {"subtask_id", "spoolman_owns_usage"} <= session_columns


async def test_fresh_schema_has_tracking_columns():
    from backend.app.core.database import Base

    _register_every_model()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            spoolman_columns = {row[1] for row in await conn.execute(text("PRAGMA table_info(active_print_spoolman)"))}
            session_columns = {row[1] for row in await conn.execute(text("PRAGMA table_info(active_print_sessions)"))}
    finally:
        await engine.dispose()

    assert "tray_now_at_start" in spoolman_columns
    assert {"printer_id", "print_name", "subtask_id", "tray_change_log", "spoolman_owns_usage"} <= session_columns


@pytest.mark.asyncio
async def test_postgres_upgrade_is_idempotent_by_sql_construction():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.app.core import database as database_module

    class _AsyncContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    statements: list[str] = []

    async def capture(_conn, sql: str) -> None:
        statements.append(sql)

    connection = MagicMock()
    connection.begin_nested = lambda: _AsyncContext()
    connection.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))

    with (
        patch("backend.app.core.database.is_sqlite", return_value=False),
        patch("backend.app.core.database._safe_execute", side_effect=capture),
        patch("backend.app.core.database._migrate_update_auto_link_constraint", AsyncMock()),
        patch("backend.app.core.database._migrate_widen_spoolman_slot_ams_id_range", AsyncMock()),
    ):
        await database_module.run_migrations(connection)

    alters = [statement for statement in statements if "tray_now_at_start" in statement and "ALTER" in statement]
    assert len(alters) == 1
    assert "IF NOT EXISTS" in alters[0]
    session_alters = [statement for statement in statements if "active_print_sessions" in statement]
    assert len(session_alters) == 2
    assert all("IF NOT EXISTS" in statement for statement in session_alters)
    assert any("subtask_id" in statement for statement in session_alters)
    assert any("spoolman_owns_usage" in statement for statement in session_alters)
