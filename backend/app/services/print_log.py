"""Service for writing independent print log entries.

Log entries are written to a separate table and never touch archives or queue items.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_log import PrintLogEntry
from backend.app.utils.local_time import to_naive_utc

logger = logging.getLogger(__name__)


async def write_log_entry(
    db: AsyncSession,
    *,
    status: str,
    run_id: int | None = None,
    archive_id: int | None = None,
    queue_item_id: int | None = None,
    print_name: str | None = None,
    printer_name: str | None = None,
    printer_id: int | None = None,
    plate_id: int | None = None,
    subtask_id: str | None = None,
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
    duration_unmeasured: bool = False,
    ended_offline: bool = False,
) -> PrintLogEntry:
    """Write a print log entry.

    Reconciled completions are synthetic reconnect cleanups. Their real end
    time is unknown, so store 0 instead of charging the disconnect gap as print
    time.
    """
    if reconciled:
        duration: int | None = 0
    elif started_at and completed_at:
        duration = int((to_naive_utc(completed_at) - to_naive_utc(started_at)).total_seconds())
    else:
        duration = None

    # Snapshot the run's intended quantity and project. Reprints reuse archives,
    # so later metadata edits must not move earlier production between orders.
    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_queue import PrintQueueItem

    archive = await db.get(PrintArchive, archive_id) if archive_id is not None else None
    item = await db.get(PrintQueueItem, queue_item_id) if queue_item_id is not None else None
    from backend.app.services.print_log_run import merge_run_entry

    archive_is_this_run = (
        archive is not None
        and archive.printer_id == printer_id
        and started_at is not None
        and to_naive_utc(archive.started_at) == to_naive_utc(started_at)
    )
    fields = {
        "archive_id": archive_id,
        "project_id": item.project_id
        if item and item.project_id is not None
        else archive.project_id
        if archive
        else None,
        "quantity": max(1, item.expected_parts or 1)
        if item and item.expected_parts
        else max(1, archive.quantity or 1)
        if archive
        else 1,
        "confirm_requested": bool(item.confirm_outcome if item else archive and archive.confirm_requested),
        "queue_item_id": queue_item_id,
        "print_name": print_name,
        "printer_name": printer_name,
        "printer_id": printer_id,
        "plate_id": plate_id if plate_id is not None else item.plate_id if item else None,
        "subtask_id": subtask_id,
        "status": status,
        "started_at": to_naive_utc(started_at),
        "completed_at": to_naive_utc(completed_at),
        "duration_seconds": duration,
        "duration_unmeasured": True if duration_unmeasured else None,
        "ended_offline": True if ended_offline else None,
        "filament_type": filament_type,
        "filament_color": filament_color,
        "filament_used_grams": filament_used_grams,
        "cost": cost,
        "energy_start_kwh": archive.energy_start_kwh if archive_is_this_run else None,
        "energy_start_plug_id": archive.energy_start_plug_id if archive_is_this_run else None,
        "energy_kwh": energy_kwh,
        "energy_cost": energy_cost,
        "failure_reason": failure_reason,
        "thumbnail_path": thumbnail_path,
        "created_by_id": created_by_id,
        "created_by_username": created_by_username,
    }
    entry = await merge_run_entry(db, fields, run_id=run_id)
    await db.flush()
    return entry
