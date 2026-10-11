"""Local Spoolman assignment cleanup shared by MQTT and manual sync routes."""

from sqlalchemy import select

from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services import slot_unlink_grace
from backend.app.services.ams_slot_presence import spool_present


async def expire_empty_slots(db, printer_id: int, ams_data: list, printing_now: bool) -> list[tuple[int, int]]:
    """Delete only linked slots whose empty evidence survives the grace period."""
    trays = {
        (int(unit.get("id", 0)), int(tray.get("id", 0))): tray
        for unit in ams_data
        if isinstance(unit, dict)
        for tray in unit.get("tray", [])
        if isinstance(tray, dict)
    }
    rows = (
        (await db.execute(select(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.printer_id == printer_id)))
        .scalars()
        .all()
    )
    held: set[tuple] = set()
    expired = []
    for row in rows:
        tray = trays.get((row.ams_id, row.tray_id))
        if tray is None or printing_now:
            continue
        if (tray.get("tray_type") or "").strip() and (tray.get("tray_color") or "").strip():
            continue
        key = ("spoolman", row.ams_id, row.tray_id, row.spoolman_spool_id)
        if spool_present(tray) is True:
            continue
        if slot_unlink_grace.removal_confirmed(printer_id, key):
            expired.append((row.ams_id, row.tray_id))
            await db.delete(row)
        else:
            held.add(key)
    slot_unlink_grace.settle(printer_id, "spoolman", held)
    return expired
