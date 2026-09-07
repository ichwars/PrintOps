"""Live PostgreSQL coverage for locale-safe migrations and UTC timestamps (#142)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

POSTGRES_TEST_URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="live PostgreSQL test URL not configured")


@pytest.mark.asyncio
async def test_repeated_startup_localised_errors_and_utc_defaults():
    from backend.app.core import database

    assert database.settings.database_url == POSTGRES_TEST_URL

    # Fresh installation followed by a repeated startup exercises the complete
    # migration sequence against PostgreSQL, including already-applied DDL.
    await database.init_db()
    await database.init_db()

    async with database.engine.begin() as conn:
        assert (await conn.execute(text("SHOW TimeZone"))).scalar_one() == "UTC"

        await conn.execute(text("DROP TABLE IF EXISTS issue_142_runtime_probe"))
        await conn.execute(
            text(
                "CREATE TABLE issue_142_runtime_probe ("
                "id INTEGER PRIMARY KEY, created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        await conn.execute(text("INSERT INTO issue_142_runtime_probe (id) VALUES (1)"))
        stored = (await conn.execute(text("SELECT created_at FROM issue_142_runtime_probe WHERE id = 1"))).scalar_one()
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs(stored - utc_now) < timedelta(minutes=1)

        await database._safe_execute(conn, "ALTER TABLE issue_142_runtime_probe ADD COLUMN value INTEGER")
        await database._safe_execute(conn, "ALTER TABLE issue_142_runtime_probe ADD COLUMN value INTEGER")

        # PostgreSQL emits the error and SQLSTATE; only the message is supplied
        # in German to prove classification never depends on English wording.
        with pytest.raises(ProgrammingError) as duplicate:
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        "DO $$ BEGIN RAISE EXCEPTION USING ERRCODE = '42701', "
                        "MESSAGE = 'Spalte ist bereits vorhanden'; END $$"
                    )
                )
        assert "Spalte ist bereits vorhanden" in str(duplicate.value)
        assert database._is_already_applied(
            duplicate.value,
            "ALTER TABLE issue_142_runtime_probe ADD COLUMN value INTEGER",
        )

        with pytest.raises(ProgrammingError) as unexpected:
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        "DO $$ BEGIN RAISE EXCEPTION USING ERRCODE = '42P01', "
                        "MESSAGE = 'already exists, aber die Tabelle fehlt'; END $$"
                    )
                )
        assert not database._is_already_applied(
            unexpected.value,
            "ALTER TABLE issue_142_runtime_probe ADD COLUMN other INTEGER",
        )
        with pytest.raises(ProgrammingError):
            await database._safe_execute(
                conn,
                "ALTER TABLE issue_142_missing_table ADD COLUMN value INTEGER",
            )

        await conn.execute(text("DROP TABLE issue_142_runtime_probe"))
