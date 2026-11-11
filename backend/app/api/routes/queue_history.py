"""Read or clear terminal queue items using the visible history filters."""

from contextlib import AsyncExitStack
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.print_queue import enrich_queue_items, queue_read_query
from backend.app.core.auth import OwnershipAccess, require_ownership_permission
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import RowVisibility, resolve_row_visibility
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.schemas.print_queue import PrintQueueItemResponse
from backend.app.services.print_batch import (
    batch_dispatch_lock,
    refresh_batches_after_queue_removal,
    remove_queue_item_in_transaction,
)

router = APIRouter(prefix="/queue", tags=["print-queue"])
_HISTORY_STATUSES = ("completed", "failed", "skipped", "cancelled")
_READ = Depends(
    require_ownership_permission(Permission.QUEUE_READ_ALL, Permission.QUEUE_READ_OWN, include_api_key=True)
)
_DELETE = Depends(
    require_ownership_permission(Permission.QUEUE_DELETE_ALL, Permission.QUEUE_DELETE_OWN, include_api_key=True)
)


class QueueHistoryResponse(BaseModel):
    items: list[PrintQueueItemResponse]
    related_items: list[PrintQueueItemResponse]
    total: int
    locations: list[str]


class QueueHistoryClearResponse(BaseModel):
    cleared: int
    kept: int


def _history_conditions(visibility: RowVisibility, printer_id: int | None, status: str | None, location: str | None):
    conditions = [
        *visibility.criteria(
            PrintQueueItem.created_by_id,
            Permission.QUEUE_READ_ALL,
            Permission.QUEUE_READ_OWN,
            PrintQueueItem.printer_id,
        ),
        PrintQueueItem.status.in_(
            (status,) if status in _HISTORY_STATUSES else _HISTORY_STATUSES if not status else ()
        ),
    ]
    if printer_id is not None:
        if printer_id == -1:
            conditions.append(PrintQueueItem.printer_id.is_(None))
        elif visibility.allows_printer(printer_id):
            conditions.append(PrintQueueItem.printer_id == printer_id)
        else:
            raise HTTPException(404, "Printer not found")
    if location:
        printer_location = (
            select(Printer.location)
            .where(Printer.id == PrintQueueItem.printer_id)
            .correlate(PrintQueueItem)
            .scalar_subquery()
        )
        conditions.append(func.coalesce(func.nullif(PrintQueueItem.target_location, ""), printer_location) == location)
    return conditions


@router.get("/history", response_model=QueueHistoryResponse)
async def get_queue_history(
    printer_id: int | None = Query(None, ge=-1),
    status: str | None = Query(None),
    location: str | None = Query(None, max_length=255),
    sort_by: Literal["date", "name", "printer"] = Query("date"),
    reverse: bool = Query(False),
    limit: int = Query(50, ge=0, le=500),
    offset: int = Query(0, ge=0),
    access: OwnershipAccess = _READ,
    db: AsyncSession = DB_SESSION,
):
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    conditions = _history_conditions(visibility, printer_id, status, location)
    total = await db.scalar(select(func.count(PrintQueueItem.id)).where(*conditions))
    locations = await _history_locations(db, visibility)
    if not total or not limit:
        return QueueHistoryResponse(items=[], related_items=[], total=total or 0, locations=locations)

    query = (
        queue_read_query(visibility)
        .outerjoin(PrintArchive, PrintArchive.id == PrintQueueItem.archive_id)
        .outerjoin(LibraryFile, LibraryFile.id == PrintQueueItem.library_file_id)
        .outerjoin(Printer, Printer.id == PrintQueueItem.printer_id)
        .where(*conditions)
        .order_by(*_history_order(sort_by, reverse))
    )
    items = list(await db.scalars(query.limit(limit).offset(offset)))
    batches = {item.batch_id for item in items if item.batch_id is not None}
    siblings = []
    if batches:
        siblings = list(
            await db.scalars(
                query.where(PrintQueueItem.batch_id.in_(batches), PrintQueueItem.id.not_in([item.id for item in items]))
            )
        )
    responses = await enrich_queue_items(db, [*items, *siblings])
    return QueueHistoryResponse(
        items=responses[: len(items)], related_items=responses[len(items) :], total=total, locations=locations
    )


def _history_order(sort_by: str, reverse: bool):
    if sort_by == "date":
        when = func.coalesce(PrintQueueItem.completed_at, PrintQueueItem.created_at)
        return (when.asc(), PrintQueueItem.id.asc()) if reverse else (when.desc(), PrintQueueItem.id.desc())

    if sort_by == "printer":
        label = Printer.name
    else:
        archive_name = case(
            (
                PrintArchive.deleted_at.is_(None),
                func.coalesce(func.nullif(PrintArchive.print_name, ""), PrintArchive.filename),
            )
        )
        label = func.coalesce(archive_name, LibraryFile.filename)
    sort_name = func.lower(func.coalesce(label, ""))
    return (sort_name.desc(), PrintQueueItem.id.desc()) if reverse else (sort_name.asc(), PrintQueueItem.id.asc())


async def _history_locations(db: AsyncSession, visibility: RowVisibility) -> list[str]:
    location = func.coalesce(func.nullif(PrintQueueItem.target_location, ""), func.nullif(Printer.location, ""))
    query = (
        select(location)
        .select_from(PrintQueueItem)
        .outerjoin(Printer, Printer.id == PrintQueueItem.printer_id)
        .where(*_history_conditions(visibility, None, None, None), location.is_not(None))
        .distinct()
        .order_by(location)
    )
    return list(await db.scalars(query))


@router.post("/history/clear", response_model=QueueHistoryClearResponse)
async def clear_queue_history(
    printer_id: int | None = Query(None, ge=-1),
    status: str | None = Query(None),
    location: str | None = Query(None, max_length=255),
    read_access: OwnershipAccess = _READ,
    delete_access: OwnershipAccess = _DELETE,
    db: AsyncSession = DB_SESSION,
):
    read_visibility = await resolve_row_visibility(db, read_access.user, read_access.api_key)
    delete_visibility = await resolve_row_visibility(db, delete_access.user, delete_access.api_key)
    conditions = [
        *_history_conditions(read_visibility, printer_id, status, location),
        *delete_visibility.criteria(
            PrintQueueItem.created_by_id,
            Permission.QUEUE_DELETE_ALL,
            Permission.QUEUE_DELETE_OWN,
            PrintQueueItem.printer_id,
        ),
    ]
    candidates = (
        await db.execute(
            select(PrintQueueItem.id, PrintQueueItem.batch_id)
            .where(*conditions)
            .order_by(PrintQueueItem.position, PrintQueueItem.id)
        )
    ).all()
    if not candidates:
        return QueueHistoryClearResponse(cleared=0, kept=0)

    batches = {row.batch_id for row in candidates if row.batch_id is not None}
    deleted: set[int] = set()
    deleted_batches: set[int] = set()
    kept = 0
    async with AsyncExitStack() as locks:
        for batch_id in sorted(batches):
            await locks.enter_async_context(batch_dispatch_lock(db, batch_id))
        try:
            if db.get_bind().dialect.name == "sqlite":
                await db.execute(text("UPDATE print_queue SET id = id WHERE 0"))
            for start in range(0, len(candidates), 400):
                chunk = candidates[start : start + 400]
                chunk_batches = {row.batch_id for row in chunk if row.batch_id is not None}
                rows = await db.scalars(
                    select(PrintQueueItem)
                    .where(
                        *conditions,
                        PrintQueueItem.id.in_([row.id for row in chunk]),
                        or_(PrintQueueItem.batch_id.is_(None), PrintQueueItem.batch_id.in_(chunk_batches)),
                    )
                    .order_by(PrintQueueItem.position, PrintQueueItem.id)
                    .with_for_update()
                )
                for item in rows:
                    result = await remove_queue_item_in_transaction(db, item)
                    if result["deleted"]:
                        deleted.add(item.id)
                        if item.batch_id is not None:
                            deleted_batches.add(item.batch_id)
                    else:
                        kept += 1
                    await db.flush()
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

    await refresh_batches_after_queue_removal(db, deleted_batches)
    from backend.app.services.print_scheduler import scheduler

    for item_id in deleted:
        scheduler.notify_dispatch_cancelled(item_id)
    return QueueHistoryClearResponse(cleared=len(deleted), kept=kept)
