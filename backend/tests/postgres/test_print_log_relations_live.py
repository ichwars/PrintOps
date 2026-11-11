"""Missing print-log constraints are repaired without reassigning old runs."""

import os

import pytest
from sqlalchemy import inspect, select

POSTGRES_URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="live PostgreSQL test URL not configured")


async def test_postgres_restores_missing_constraints_and_does_not_reattach_history():
    from backend.app.core import database
    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import PrintLogEntry

    assert database.settings.database_url == POSTGRES_URL
    try:
        await database.init_db()
        async with database.engine.begin() as conn:
            keys = await conn.run_sync(lambda sync: inspect(sync).get_foreign_keys("print_log_entries"))
            removed = {"archive_id", "created_by_id"}
            quote = conn.dialect.identifier_preparer.quote_identifier
            for key in keys:
                if len(key["constrained_columns"]) == 1 and key["constrained_columns"][0] in removed:
                    await conn.exec_driver_sql(f"ALTER TABLE print_log_entries DROP CONSTRAINT {quote(key['name'])}")
            await conn.execute(
                PrintArchive.__table__.insert().values(
                    filename="matching.3mf", file_path="matching.3mf", file_size=1, print_name="Matching", cost=42
                )
            )
            run_id = await conn.scalar(
                PrintLogEntry.__table__.insert()
                .values(
                    archive_id=987654,
                    created_by_id=987654,
                    created_by_username="Former author",
                    print_name="Matching",
                    status="completed",
                    cost=0.75,
                )
                .returning(PrintLogEntry.id)
            )

        await database.init_db()
        await database.init_db()
        async with database.engine.connect() as conn:
            entry = (
                await conn.execute(
                    select(
                        PrintLogEntry.archive_id,
                        PrintLogEntry.created_by_id,
                        PrintLogEntry.created_by_username,
                        PrintLogEntry.cost,
                    ).where(PrintLogEntry.id == run_id)
                )
            ).one()
            assert entry == (None, None, "Former author", 0.75)
            keys = await conn.run_sync(lambda sync: inspect(sync).get_foreign_keys("print_log_entries"))
            relevant = {
                key["constrained_columns"][0]: (key["referred_table"], key["options"].get("ondelete"))
                for key in keys
                if len(key["constrained_columns"]) == 1 and key["constrained_columns"][0] in removed
            }
            assert relevant == {"archive_id": ("print_archives", "SET NULL"), "created_by_id": ("users", "SET NULL")}
    finally:
        await database.engine.dispose()
