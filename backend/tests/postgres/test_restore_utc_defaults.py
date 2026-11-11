"""Empty timestamps in an old SQLite backup use UTC during PostgreSQL import."""

import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.app.api.routes.settings import _import_sqlite_to_postgres
from backend.app.core import database
from backend.tests.conftest import TEST_PG_URL

pytestmark = pytest.mark.skipif(
    TEST_PG_URL is None or not hasattr(time, "tzset"), reason="requires the PostgreSQL fixture database and tzset"
)


async def test_legacy_required_timestamps_use_utc(tmp_path, test_engine, monkeypatch):
    source = tmp_path / "legacy.db"
    with closing(sqlite3.connect(source)) as db:
        db.executescript("""
            CREATE TABLE spool (
                id INTEGER PRIMARY KEY, material TEXT, label_weight INTEGER, core_weight INTEGER,
                weight_used REAL, weight_locked INTEGER, created_at TEXT, updated_at TEXT
            );
            INSERT INTO spool VALUES (1, 'PLA', 1000, 250, 20, 0, NULL, NULL);
        """)

    monkeypatch.setattr(database, "_create_engine", lambda: test_engine)
    try:
        with monkeypatch.context() as zone:
            zone.setenv("TZ", "Pacific/Kiritimati")
            time.tzset()
            assert abs((datetime.now() - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) > 3_600
            before = datetime.now(timezone.utc).replace(tzinfo=None)
            await _import_sqlite_to_postgres(source, TEST_PG_URL)
            after = datetime.now(timezone.utc).replace(tzinfo=None)
    finally:
        time.tzset()

    async with test_engine.connect() as conn:
        created, updated = (await conn.execute(text("SELECT created_at, updated_at FROM spool WHERE id = 1"))).one()
    assert before <= created <= after
    assert before <= updated <= after
