"""Service for writing independent print log entries.

Log entries are written to a separate table and never touch archives or queue items.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_log import PrintLogEntry

logger = logging.getLogger(__name__)


async def write_log_entry(
    db: AsyncSession,
    *,
    status: str,
    archive_id: int | None = None,
    queue_item_id: int | None = None,
    print_name: str | None = None,
    printer_name: str | None = None,
    printer_id: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    filament_type: str | None = None,
    filament_color: str | None = None,
    filament_used_grams: float | None = None,
    cost: float | None = None,
    energy_kwh: float | None = None,
    energy_cost: float | None = None,
    failure_reason: str | None = None,
    thumbnail_path: str | None = None,
    created_by_id: int | None = None,
    created_by_username: str | None = None,
    reconciled: bool = False,
) -> PrintLogEntry:
    """Write a print log entry.

    Reconciled completions are synthetic reconnect cleanups. Their real end
    time is unknown, so store 0 instead of charging the disconnect gap as print
    time.
    """
    if reconciled:
        duration: int | None = 0
    elif started_at and completed_at:
        duration = int((completed_at - started_at).total_seconds())
    else:
        duration = None

    # Snapshot the run's intended quantity and project. Reprints reuse archives,
    # so later metadata edits must not move earlier production between orders.
    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_queue import PrintQueueItem

    archive = await db.get(PrintArchive, archive_id) if archive_id is not None else None
    item = await db.get(PrintQueueItem, queue_item_id) if queue_item_id is not None else None
    entry = PrintLogEntry(
        archive_id=archive_id,
        project_id=(
            item.project_id if item and item.project_id is not None else archive.project_id if archive else None
        ),
        quantity=max(1, item.expected_parts or 1)
        if item and item.expected_parts
        else max(1, archive.quantity or 1)
        if archive
        else 1,
        confirm_requested=bool(item.confirm_outcome if item else archive and archive.confirm_requested),
        queue_item_id=queue_item_id,
        print_name=print_name,
        printer_name=printer_name,
        printer_id=printer_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        filament_type=filament_type,
        filament_color=filament_color,
        filament_used_grams=filament_used_grams,
        cost=cost,
        energy_kwh=energy_kwh,
        energy_cost=energy_cost,
        failure_reason=failure_reason,
        thumbnail_path=thumbnail_path,
        created_by_id=created_by_id,
        created_by_username=created_by_username,
    )
    db.add(entry)
    await db.flush()
    return entry
