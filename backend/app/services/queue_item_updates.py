"""Atomic bulk queue edits with existing ownership and printer restrictions."""

from sqlalchemy import case, false, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_queue import PrintQueueItem, PrintQueueVariant
from backend.app.services.queue_item_printer import PRINTER_RESOLVED_DEFAULTS


async def apply_bulk_queue_updates(
    db: AsyncSession,
    item_ids: list[int],
    update_data: dict,
    *,
    owner_id: int | None,
    can_modify_all: bool,
    allowed_printer_ids: set[int] | None,
) -> tuple[int, int]:
    """Skip unknown/uneditable rows; guard each update against concurrent claims."""
    # Fetch existing IDs first so skipped_count keeps the legacy behavior of
    # ignoring unknown IDs while still applying edits atomically below.
    result = await db.execute(select(PrintQueueItem.id).where(PrintQueueItem.id.in_(item_ids)))
    item_ids = result.scalars().all()

    updated_count = 0
    skipped_count = 0

    for existing_id in item_ids:
        conditions = [
            PrintQueueItem.id == existing_id,
            PrintQueueItem.status == "pending",
            PrintQueueItem.dispatching_at.is_(None),
        ]
        if not can_modify_all:
            conditions.append(PrintQueueItem.created_by_id == owner_id if owner_id is not None else false())
        if allowed_printer_ids is not None:
            conditions.append(
                or_(PrintQueueItem.printer_id.is_(None), PrintQueueItem.printer_id.in_(allowed_printer_ids))
            )

        item_update_data = update_data.copy()
        if "printer_id" in item_update_data:
            next_printer = item_update_data["printer_id"]
            rebinds = PrintQueueItem.printer_id.is_distinct_from(next_printer)
            # A variant job chooses its own printer. Keep this check and the
            # pending/claim guard in the atomic UPDATE, rather than a stale read.
            has_variants = (
                select(PrintQueueVariant.id).where(PrintQueueVariant.queue_item_id == PrintQueueItem.id).exists()
            )
            conditions.append(or_(~rebinds, ~has_variants))
            for field, default in PRINTER_RESOLVED_DEFAULTS.items():
                item_update_data[field] = case((rebinds, default), else_=getattr(PrintQueueItem, field))
            for field in ("target_model", "target_location"):
                item_update_data[field] = case((rebinds, None), else_=getattr(PrintQueueItem, field))

        result = await db.execute(update(PrintQueueItem).where(*conditions).values(**item_update_data))
        if result.rowcount:
            updated_count += 1
        else:
            skipped_count += 1

    return updated_count, skipped_count
