"""Exercise SQLite deletion rules and the normal archive/warehouse entry points."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.archive_relation_migration import migrate_archive_relations, rebuild_legacy_archive_fts
from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.location import Location
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.project import Project
from backend.app.models.project_production import ProjectProductionOutput, ProjectProductionReceipt
from backend.app.models.small_part import SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry
from backend.tests.integration.test_order_reservation_lifecycle import _accepted_order

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.sqlite_only
async def test_sqlite_archive_delete_cascades_queue_and_keeps_run_and_batch(
    async_client, test_engine, db_session, archive_factory, printer_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    batch = PrintBatch(name="Retained batch", archive_id=archive.id)
    db_session.add(batch)
    await db_session.flush()
    queue = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, batch_id=batch.id, status="completed")
    db_session.add(queue)
    await db_session.flush()
    log = PrintLogEntry(archive_id=archive.id, queue_item_id=queue.id, status="completed", cost=2.5)
    db_session.add(log)
    await db_session.commit()

    async with test_engine.begin() as conn:
        await migrate_archive_relations(conn, Base.metadata)
        await migrate_archive_relations(conn, Base.metadata)
        await conn.execute(delete(PrintArchive).where(PrintArchive.id == archive.id))

    assert await db_session.scalar(select(PrintQueueItem.id).where(PrintQueueItem.id == queue.id)) is None
    await db_session.refresh(log)
    await db_session.refresh(batch)
    assert (log.archive_id, log.queue_item_id, log.cost) == (None, None, 2.5)
    assert batch.archive_id is None


@pytest.mark.sqlite_only
async def test_startup_clears_legacy_orphans_without_dropping_running_job(
    async_client, test_engine, db_session, printer_factory
):
    printer = await printer_factory()
    running = PrintQueueItem(printer_id=printer.id, archive_id=901, status="printing")
    waiting = PrintQueueItem(printer_id=printer.id, library_file_id=902, status="pending")
    db_session.add_all([running, waiting])
    await db_session.commit()

    async with test_engine.begin() as conn:
        await migrate_archive_relations(conn, Base.metadata)
    await db_session.refresh(running)
    await db_session.refresh(waiting)
    assert (running.archive_id, running.status) == (None, "printing")
    assert (waiting.library_file_id, waiting.status) == (None, "cancelled")


@pytest.fixture
async def production_receipt(db_session):
    project = Project(name="Production")
    location = Location(name="Finished stock", name_key="finished stock")
    article = WarehouseArticle(sku="FINISHED-1", name="Finished article", kind="finished", unit_code="C62")
    if await db_session.get(SmallPartUnit, "C62") is None:
        db_session.add(SmallPartUnit(code="C62", label="Piece", decimal_places=0))
        await db_session.flush()
    db_session.add_all([project, location, article])
    await db_session.flush()
    run = PrintLogEntry(project_id=project.id, status="completed")
    ledger_entry = WarehouseArticleLedgerEntry(
        article_id=article.id,
        entry_kind="receipt",
        location_id=location.id,
        quantity=Decimal(6),
        physical_delta=Decimal(6),
        reserved_delta=Decimal(0),
        unit_code="C62",
        reason="Production receipt",
        idempotency_key="production-receipt",
        command_hash="production-receipt",
    )
    db_session.add_all([run, ledger_entry])
    await db_session.flush()
    db_session.add_all(
        [
            ProjectProductionOutput(project_id=project.id, article_id=article.id, location_id=location.id),
            ProjectProductionReceipt(ledger_entry_id=ledger_entry.id, project_id=project.id, run_id=run.id),
        ]
    )
    await db_session.commit()
    return project.id, run.id, ledger_entry.id


@pytest.mark.sqlite_only
@pytest.mark.parametrize("legacy_trigger", [False, True], ids=["fresh", "upgrade"])
async def test_sqlite_project_delete_releases_production_links(test_engine, production_receipt, legacy_trigger):
    project_id, run_id, ledger_id = production_receipt
    async with test_engine.begin() as conn:
        assert (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar_one() == 0
        if legacy_trigger:
            await conn.exec_driver_sql("""
                CREATE TRIGGER printops_delete_projects_refs AFTER DELETE ON projects BEGIN
                    UPDATE print_log_entries SET project_id = NULL WHERE project_id = OLD.id;
                END
            """)
        await migrate_archive_relations(conn, Base.metadata)
        await migrate_archive_relations(conn, Base.metadata)
        await conn.execute(delete(Project).where(Project.id == project_id))

        assert await conn.scalar(select(ProjectProductionOutput.project_id)) is None
        receipt = await conn.execute(select(ProjectProductionReceipt.project_id, ProjectProductionReceipt.run_id))
        assert receipt.one() == (None, run_id)
        assert await conn.scalar(select(PrintLogEntry.project_id).where(PrintLogEntry.id == run_id)) is None
        assert await conn.scalar(
            select(WarehouseArticleLedgerEntry.physical_delta).where(WarehouseArticleLedgerEntry.id == ledger_id)
        ) == Decimal(6)


@pytest.mark.parametrize("legacy_fk", [False, True], ids=["fresh", "postgres-upgrade"])
async def test_booked_print_runs_survive_database_deletion(test_engine, db_session, production_receipt, legacy_fk):
    project_id, run_id, ledger_id = production_receipt
    unbooked = PrintLogEntry(project_id=project_id, status="completed")
    db_session.add(unbooked)
    await db_session.commit()

    async with test_engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            if legacy_fk:
                pytest.skip("Requires a legacy PostgreSQL constraint")
            assert (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar_one() == 0
            await migrate_archive_relations(conn, Base.metadata)
        elif legacy_fk:
            await conn.exec_driver_sql("""
                ALTER TABLE project_production_receipts
                  DROP CONSTRAINT project_production_receipts_run_id_fkey,
                  ADD CONSTRAINT legacy_production_run_fk
                      FOREIGN KEY (run_id) REFERENCES print_log_entries (id) ON DELETE SET NULL
            """)
            await migrate_archive_relations(conn, Base.metadata)
            await migrate_archive_relations(conn, Base.metadata)
        await conn.execute(delete(PrintLogEntry).where(PrintLogEntry.id == unbooked.id))

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(delete(PrintLogEntry).where(PrintLogEntry.id == run_id))

    assert await db_session.scalar(select(PrintLogEntry.id).where(PrintLogEntry.id == unbooked.id)) is None
    assert await db_session.scalar(select(PrintLogEntry.id).where(PrintLogEntry.id == run_id)) == run_id
    receipt = await db_session.get(ProjectProductionReceipt, ledger_id)
    assert receipt is not None
    assert (receipt.project_id, receipt.run_id) == (project_id, run_id)
    ledger_entry = await db_session.get(WarehouseArticleLedgerEntry, ledger_id)
    assert ledger_entry is not None and ledger_entry.physical_delta == Decimal(6)


@pytest.mark.sqlite_only
async def test_sqlite_startup_repairs_orphaned_production_links(test_engine, production_receipt):
    project_id, run_id, ledger_id = production_receipt
    async with test_engine.begin() as conn:
        assert (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar_one() == 0
        await conn.execute(delete(Project).where(Project.id == project_id))
        await conn.execute(delete(PrintLogEntry).where(PrintLogEntry.id == run_id))
        await migrate_archive_relations(conn, Base.metadata)

        assert await conn.scalar(select(ProjectProductionOutput.project_id)) is None
        receipt = await conn.execute(select(ProjectProductionReceipt.project_id, ProjectProductionReceipt.run_id))
        assert receipt.one() == (None, None)
        assert await conn.scalar(
            select(WarehouseArticleLedgerEntry.physical_delta).where(WarehouseArticleLedgerEntry.id == ledger_id)
        ) == Decimal(6)


@pytest.mark.sqlite_only
async def test_existing_archives_are_indexed_before_startup_data_repairs(test_engine, archive_factory, printer_factory):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, print_name="fixturearchive")
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("""
            CREATE VIRTUAL TABLE archive_fts
            USING fts5(print_name, content='print_archives', content_rowid='id')
        """)
        for _ in range(2):
            await rebuild_legacy_archive_fts(conn)
            result = await conn.exec_driver_sql(
                "SELECT rowid FROM archive_fts WHERE archive_fts MATCH 'fixturearchive'"
            )
            assert result.scalar_one() == archive.id


@pytest.mark.parametrize("purge_stats", [False, True])
async def test_purge_skips_archive_used_by_an_active_print(
    async_client, db_session, archive_factory, printer_factory, purge_stats
):
    source = await printer_factory()
    printing_printer = await printer_factory()
    old = datetime.now(timezone.utc) - timedelta(days=400)
    archive = await archive_factory(source.id, created_at=old, with_run=False)
    queue = PrintQueueItem(printer_id=printing_printer.id, archive_id=archive.id, status="printing")
    db_session.add(queue)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/archives/purge", json={"older_than_days": 365, "purge_stats": purge_stats}
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == 0
    response = await async_client.delete(f"/api/v1/printers/{source.id}")
    assert response.status_code == 409, response.text
    await db_session.refresh(archive)
    await db_session.refresh(queue)
    assert archive.deleted_at is None
    assert queue.archive_id == archive.id and queue.status == "printing"


async def test_order_references_block_project_and_spool_hard_delete(async_client, db_session):
    order, _part, spool = await _accepted_order(async_client, db_session)
    project_id = order["project_id"]
    spool_id = spool.id

    project = await async_client.delete(f"/api/v1/projects/{project_id}")
    single = await async_client.delete(f"/api/v1/inventory/spools/{spool_id}")
    bulk = await async_client.post("/api/v1/inventory/spools/bulk-delete", json={"ids": [spool_id]})
    assert (project.status_code, single.status_code, bulk.status_code) == (409, 409, 409)
    assert (await async_client.get(f"/api/v1/projects/{project_id}")).status_code == 200
    assert (await async_client.get(f"/api/v1/inventory/spools/{spool_id}")).status_code == 200
