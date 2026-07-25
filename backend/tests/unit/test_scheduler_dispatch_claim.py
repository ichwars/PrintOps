"""Queue dispatch claim regression tests."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.app.models  # noqa: F401 - populate Base.metadata
import backend.app.services.print_scheduler as scheduler_module
from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.app.services.print_scheduler import PrintScheduler


@pytest.fixture
async def claim_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                Printer.__table__,
                Project.__table__,
                PrintArchive.__table__,
                LibraryFolder.__table__,
                LibraryFile.__table__,
                PrintBatch.__table__,
                PrintQueueItem.__table__,
            ],
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as db:
        printer = Printer(
            name="Claim Test Printer",
            serial_number="CLAIM0001",
            ip_address="127.0.0.1",
            access_code="12345678",
            model="X1C",
        )
        db.add(printer)
        await db.flush()
        item = PrintQueueItem(printer_id=printer.id, status="pending")
        db.add(item)
        await db.commit()
        item_id = item.id

    try:
        yield SimpleNamespace(sessionmaker=sessionmaker, item_id=item_id)
    finally:
        await engine.dispose()


async def _get_item(ctx):
    async with ctx.sessionmaker() as db:
        return await db.get(PrintQueueItem, ctx.item_id)


@pytest.mark.asyncio
async def test_dispatch_claim_is_exclusive(claim_ctx):
    scheduler = PrintScheduler()

    async with claim_ctx.sessionmaker() as db:
        assert await scheduler._claim_for_dispatch(db, claim_ctx.item_id) is True

    assert (await _get_item(claim_ctx)).dispatching_at is not None

    async with claim_ctx.sessionmaker() as db:
        assert await scheduler._claim_for_dispatch(db, claim_ctx.item_id) is False


@pytest.mark.asyncio
async def test_dispatch_with_claim_holds_then_releases(claim_ctx):
    scheduler = PrintScheduler()
    seen = {}

    async def fake_start_print(db, item):
        row = await db.get(PrintQueueItem, item.id)
        seen["claimed_during_dispatch"] = row.dispatching_at is not None

    async with claim_ctx.sessionmaker() as db:
        item = await db.get(PrintQueueItem, claim_ctx.item_id)
        with patch.object(scheduler, "_start_print", side_effect=fake_start_print) as start_print:
            assert await scheduler._dispatch_with_claim(db, item) is True

    start_print.assert_awaited_once()
    assert seen["claimed_during_dispatch"] is True
    assert (await _get_item(claim_ctx)).dispatching_at is None


@pytest.mark.asyncio
async def test_startup_reconciliation_clears_stale_claim(claim_ctx):
    scheduler = PrintScheduler()

    async with claim_ctx.sessionmaker() as db:
        assert await scheduler._claim_for_dispatch(db, claim_ctx.item_id) is True

    with patch.object(scheduler_module, "async_session", claim_ctx.sessionmaker):
        await scheduler._clear_stale_dispatch_claims()

    assert (await _get_item(claim_ctx)).dispatching_at is None
