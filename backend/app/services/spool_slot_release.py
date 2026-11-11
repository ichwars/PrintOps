"""Release slot references before spools are archived or deleted."""

from sqlalchemy import select

from backend.app.core.websocket import ws_manager
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services import slot_unlink_grace


async def release_slots(db, spool_ids: list[int]) -> list[tuple[int, int, int]]:
    if not spool_ids:
        return []
    rows = (await db.execute(select(SpoolAssignment).where(SpoolAssignment.spool_id.in_(spool_ids)))).scalars().all()
    freed = [(row.printer_id, row.ams_id, row.tray_id) for row in rows]
    for row in rows:
        await db.delete(row)
    return freed


async def announce_freed_slots(freed: list[tuple[int, int, int]]) -> None:
    for printer_id, ams_id, tray_id in freed:
        slot_unlink_grace.forget_slot(printer_id, ams_id, tray_id)
        await ws_manager.broadcast(
            {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": ams_id, "tray_id": tray_id}
        )
