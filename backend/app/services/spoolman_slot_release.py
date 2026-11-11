"""Release obsolete Spoolman slot rows after archive/delete and usage booking."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.ams_assignment_lock import lock_spoolman_assignments
from backend.app.services.print_usage_lifecycle import printer_is_charging


async def release_spool_slots(db: AsyncSession, spool_id: int, *, keep_tracked: bool) -> list[tuple[int, int, int]]:
    """Delete a spool's slot rows; returns the freed (printer, ams, tray) slots.

    ``keep_tracked`` keeps the rows of a printer with a print being tracked:
    its usage is charged at completion by the slot's spool, which only the row
    knows for a spool without a tag. ``release_archived_slot_rows`` frees them
    once that print is reported. Commit before releasing the writer lock; the caller announces.
    """
    async with lock_spoolman_assignments(db, spool_id):
        try:
            query = select(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.spoolman_spool_id == spool_id)
            if keep_tracked:
                query = query.where(SpoolmanSlotAssignment.printer_id.not_in(select(ActivePrintSpoolman.printer_id)))
            rows = (await db.execute(query)).scalars().all()
            freed = []
            for row in rows:
                if keep_tracked and printer_is_charging(row.printer_id):
                    continue
                result = await db.execute(
                    delete(SpoolmanSlotAssignment)
                    .where(
                        SpoolmanSlotAssignment.id == row.id,
                        SpoolmanSlotAssignment.spoolman_spool_id == spool_id,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount:
                    freed.append((row.printer_id, row.ams_id, row.tray_id))
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return freed
