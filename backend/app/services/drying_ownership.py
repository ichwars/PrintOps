"""Serialize PrintOps manual operations with durable drying reservations."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from weakref import WeakKeyDictionary

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.models.drying_schedule import DryingScheduleRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.drying_telemetry import invalidate_drying_availability

_locks: WeakKeyDictionary = WeakKeyDictionary()


@asynccontextmanager
async def printer_operation(db: AsyncSession, printer_id: int):
    locks = _locks.setdefault(asyncio.get_running_loop(), {})
    lock = locks.setdefault(printer_id, asyncio.Lock())
    async with lock:
        # UPDATE obtains SQLite's transaction write lock and PostgreSQL's row lock.
        # Keep metadata timestamps unchanged while using the row as the mutex.
        await db.execute(
            update(Printer).where(Printer.id == printer_id).values(id=Printer.id, updated_at=Printer.updated_at)
        )
        yield


async def reserved_printers(db: AsyncSession) -> set[int]:
    return set(
        (
            await db.execute(
                select(DryingScheduleRun.active_printer_id).where(DryingScheduleRun.active_printer_id.is_not(None))
            )
        )
        .scalars()
        .all()
    )


async def has_drying_reservation(db: AsyncSession, printer_id: int) -> bool:
    return (
        await db.scalar(select(DryingScheduleRun.id).where(DryingScheduleRun.active_printer_id == printer_id))
        is not None
    )


async def claim_queue_item(db: AsyncSession, item_id: int) -> bool:
    printer_id = await db.scalar(select(PrintQueueItem.printer_id).where(PrintQueueItem.id == item_id))
    if printer_id is None:
        return False
    async with printer_operation(db, printer_id):
        result = await db.execute(
            update(PrintQueueItem)
            .where(
                PrintQueueItem.id == item_id,
                PrintQueueItem.printer_id == printer_id,
                PrintQueueItem.status == "pending",
                PrintQueueItem.dispatching_at.is_(None),
            )
            .where(~select(DryingScheduleRun.id).where(DryingScheduleRun.active_printer_id == printer_id).exists())
            .values(dispatching_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return result.rowcount > 0


async def printer_operation_guard(request: Request, db: AsyncSession = Depends(get_db)):
    printer_id = request.path_params.get("printer_id")
    if (
        printer_id is None
        or request.method in ("GET", "HEAD", "OPTIONS")
        or "/drying/schedules" in request.url.path
        or request.url.path.endswith("/stop")
    ):
        yield
        return
    async with printer_operation(db, int(printer_id)):
        if int(printer_id) in await reserved_printers(db):
            raise HTTPException(409, "Scheduled drying owns this printer; stop remains available")
        try:
            yield
        finally:
            from backend.app.services.printer_manager import printer_manager

            invalidate_drying_availability(printer_manager.get_status(int(printer_id)))
        await db.commit()
