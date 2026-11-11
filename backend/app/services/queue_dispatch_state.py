"""Conditional dispatch outcomes that preserve a concurrently completed user action."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.notification_service import notification_service

logger = logging.getLogger(__name__)
MODEL_GATE_WAIT_REASON = "The last print failed on every free matching printer"


async def fail_dispatch(db: AsyncSession, item: PrintQueueItem, message: str) -> bool:
    """Fail only an item still awaiting or executing this dispatch."""
    result = await db.execute(
        update(PrintQueueItem)
        .where(PrintQueueItem.id == item.id, PrintQueueItem.status.in_(("pending", "printing")))
        .values(
            status="failed", error_message=message, completed_at=datetime.now(timezone.utc), color_substitutions=None
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if not result.rowcount:
        logger.info("Queue item %s already ended or was removed; preserving its outcome", item.id)
        return False
    await db.refresh(item)
    if item.batch_id is not None:
        from backend.app.services.print_batch import refresh_batches_after

        await refresh_batches_after([item.id])
    return True


async def defer_dispatch(db: AsyncSession, item: PrintQueueItem) -> None:
    """Return an unstarted printing item to pending, preserving cancellations."""
    await db.execute(
        update(PrintQueueItem)
        .where(PrintQueueItem.id == item.id, PrintQueueItem.status == "printing")
        .values(status="pending", started_at=None, color_substitutions=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


# Include local dispatch controls as well as the upstream mapping inputs.
DISPATCH_INPUTS = (
    "printer_id",
    "status",
    "ams_mapping",
    "plate_id",
    "filament_overrides",
    "skip_filament_check",
    "require_previous_success",
    "target_model",
    "target_location",
    "manual_start",
    "scheduled_time",
    "nozzle_mapping",
    "archive_id",
    "library_file_id",
)


async def edited_since_loaded(db: AsyncSession, item: PrintQueueItem) -> bool:
    """Leave concurrent edits to the next scheduler pass instead of overwriting them."""
    row = (
        await db.execute(
            select(*(getattr(PrintQueueItem, field) for field in DISPATCH_INPUTS)).where(PrintQueueItem.id == item.id)
        )
    ).one_or_none()
    unchanged = row is not None and all(
        getattr(item, field) == value for field, value in zip(DISPATCH_INPUTS, row, strict=True)
    )
    if not unchanged:
        logger.info("Queue item %s changed during this pass; leaving it to the next", item.id)
    return not unchanged


async def previous_print_succeeded(db: AsyncSession, item: PrintQueueItem, printer_id: int | None = None) -> bool:
    """Check if the previous print on this printer succeeded.

    A user-cancelled predecessor is treated as neutral — `cancelled` is a
    deliberate action, not a failure, so subsequent items should still
    dispatch (#1667). `skipped` is excluded from the lookback entirely:
    a skip isn't an actual print attempt, so it must not gate downstream
    items — counting it as a failed predecessor was the cascade bug that
    let a single cancellation block 18 items over 3 days for the reporter.
    Only `failed` and `aborted` — real print-attempt failures — block.

    Failures with `gate_acknowledged=True` (set by the per-printer Resume
    action — #1818) are also excluded from the lookback so the user can
    clear the gate after fixing the physical issue without having to
    re-queue every downstream job.
    """
    result = await db.execute(
        select(PrintQueueItem)
        .where(PrintQueueItem.printer_id == (printer_id if printer_id is not None else item.printer_id))
        .where(PrintQueueItem.id != item.id)
        .where(PrintQueueItem.status.in_(["completed", "failed", "cancelled", "aborted"]))
        .where(PrintQueueItem.gate_acknowledged == False)  # noqa: E712
        .order_by(PrintQueueItem.completed_at.desc().nullslast(), PrintQueueItem.id.desc())
        .limit(1)
    )
    prev_item = result.scalar_one_or_none()

    # If no previous item, assume success (first in queue)
    if not prev_item:
        return True

    return prev_item.status in ("completed", "cancelled")


async def skip_after_previous_failure(scheduler, db, item, printer_id) -> bool:
    if not item.require_previous_success:
        return False
    succeeded = await scheduler._check_previous_success(db, item)
    if await edited_since_loaded(db, item):
        return True
    if succeeded:
        return False
    item.status = "skipped"
    item.error_message = "Previous print failed or was aborted"
    item.completed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Skipped queue item %s - previous print failed", item.id)
    job_name = await scheduler._get_job_name(db, item)
    printer = await scheduler._get_printer(db, printer_id)
    await notification_service.on_queue_job_skipped(
        job_name=job_name,
        printer_id=printer_id,
        printer_name=printer.name if printer else "Unknown",
        reason=item.error_message,
        db=db,
    )
    return True


async def find_ungated_printer(scheduler, db, item, gate_blocked, model, exclude_ids, *args, **kwargs):
    """Pass over failed predecessors on the actual printer, retaining alternative models."""
    while True:
        printer_id, reason = await scheduler._find_idle_printer_for_model(
            db, model, exclude_ids | gate_blocked, *args, **kwargs
        )
        if (
            printer_id
            and item.require_previous_success
            and not await scheduler._check_previous_success(db, item, printer_id=printer_id)
        ):
            gate_blocked.add(printer_id)
            continue
        return printer_id, reason
