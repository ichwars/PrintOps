"""Spool consumption survives the schema upgrade and subsequent hard deletes."""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, select
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.identity_sequence_migration import migrate_sqlite_identity_sequences
from backend.app.core.spool_usage_migration import migrate_spool_usage_history
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.github_restore import GitHubRestoreService, _CategoryTally

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "spool_constraint",
    [
        "spool_id INTEGER NOT NULL REFERENCES spool(id) ON DELETE CASCADE, cost REAL",
        "spool_id INTEGER NOT NULL, cost REAL, FOREIGN KEY (spool_id) REFERENCES spool (id) ON DELETE CASCADE",
    ],
)
async def test_sqlite_upgrade_clears_orphans_and_preserves_costs_indexes_and_sequences(tmp_path, spool_constraint):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'spool-usage.db'}")
    metadata = MetaData()
    Table("spool", metadata, Column("id", Integer, primary_key=True))
    Table("spool_usage_history", metadata, Column("spool_id", ForeignKey("spool.id")))

    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE spool (id INTEGER PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE print_archives (id INTEGER PRIMARY KEY)")
            await conn.exec_driver_sql(
                "CREATE TABLE spool_usage_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                f"archive_id INTEGER REFERENCES print_archives(id), {spool_constraint})"
            )
            await conn.exec_driver_sql("CREATE INDEX usage_cost ON spool_usage_history (cost)")
            await conn.exec_driver_sql("CREATE VIEW usage_costs AS SELECT cost FROM spool_usage_history")
            await conn.exec_driver_sql("INSERT INTO spool VALUES (7)")
            await conn.exec_driver_sql("INSERT INTO print_archives VALUES (10)")
            await conn.exec_driver_sql(
                "INSERT INTO spool_usage_history (id, spool_id, cost, archive_id) "
                "VALUES (1, 7, 2.5, 10), (2, 99, 3.5, 11), (300, 7, 9.5, NULL)"
            )
            await conn.exec_driver_sql("DELETE FROM spool_usage_history WHERE id = 300")

            for _ in range(2):
                await migrate_sqlite_identity_sequences(conn, metadata)
                await migrate_spool_usage_history(conn)

            assert (await conn.exec_driver_sql("SELECT cost FROM usage_costs ORDER BY cost")).scalars().all() == [
                2.5,
                3.5,
            ]
            assert (
                "usage_cost"
                in (await conn.exec_driver_sql("SELECT name FROM pragma_index_list('spool_usage_history')"))
                .scalars()
                .all()
            )
            orphan = (
                await conn.exec_driver_sql("SELECT spool_id, cost, archive_id FROM spool_usage_history WHERE id = 2")
            ).one()
            assert orphan == (None, 3.5, None)
            await conn.exec_driver_sql("DELETE FROM spool WHERE id = 7")
            history = (
                await conn.exec_driver_sql("SELECT spool_id, cost, archive_id FROM spool_usage_history WHERE id = 1")
            ).one()
            assert history == (None, 2.5, 10)
            await conn.exec_driver_sql("DELETE FROM print_archives WHERE id = 10")
            assert (
                await conn.exec_driver_sql("SELECT archive_id FROM spool_usage_history WHERE id = 1")
            ).scalar_one() is None
            new_spool = (await conn.exec_driver_sql("INSERT INTO spool DEFAULT VALUES RETURNING id")).scalar_one()
            assert new_spool == 100
            new_usage = (
                await conn.exec_driver_sql(
                    "INSERT INTO spool_usage_history (spool_id, cost) VALUES (100, 1.5) RETURNING id"
                )
            ).scalar_one()
            assert new_usage == 301
    finally:
        await engine.dispose()


async def test_usage_from_deleted_spools_restores_without_reattaching_or_merging_costs(db_session):
    service = GitHubRestoreService()
    inventory = {"spools": []}
    sample = {
        "spool_id": None,
        "print_name": "same.3mf",
        "weight_used": 5.0,
        "created_at": "2026-02-01 09:00:00",
    }
    usage = {"usage_history": [{**sample, "cost": 0.5}, {**sample, "cost": 0.7}]}
    for expected in (2, 0):
        tally = _CategoryTally()
        await service._restore_spools(db_session, inventory, usage, False, tally, {})
        await db_session.commit()
        assert (tally.restored, tally.skipped) == (expected, 2 - expected)
    rows = (await db_session.scalars(select(SpoolUsageHistory).order_by(SpoolUsageHistory.id))).all()
    assert [(row.spool_id, row.cost) for row in rows] == [(None, 0.5), (None, 0.7)]
