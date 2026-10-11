"""Observe and stop legacy humidity-triggered drying without discarding unknown state."""

import logging

from backend.app.services.drying_ownership import has_drying_reservation, printer_operation
from backend.app.services.drying_telemetry import invalidate_drying_availability

logger = logging.getLogger(__name__)


def _remaining(unit):
    raw = unit.get("dry_time")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def sync_drying_state(in_progress, manager):
    for printer_id in list(in_progress):
        state = manager.get_status(printer_id)
        if not state:
            in_progress.pop(printer_id, None)
            continue
        values = [_remaining(unit) for unit in state.raw_data.get("ams", [])]
        if values and all(value == 0 for value in values):
            in_progress.pop(printer_id, None)


async def start_drying(db, manager, printer_id, ams_id, temperature, duration, filament):
    async with printer_operation(db, printer_id):
        if await has_drying_reservation(db, printer_id):
            return False
        try:
            success = manager.send_drying_command(printer_id, ams_id, temperature, duration, mode=1, filament=filament)
        finally:
            invalidate_drying_availability(manager.get_status(printer_id))
        await db.commit()
        return success


async def stop_drying(in_progress, printer_id, manager, session_factory):
    async with session_factory() as db, printer_operation(db, printer_id):
        if await has_drying_reservation(db, printer_id):
            return
        _stop_drying(in_progress, printer_id, manager)
        invalidate_drying_availability(manager.get_status(printer_id))
        await db.commit()


def _stop_drying(in_progress, printer_id, manager):
    state = manager.get_status(printer_id)
    if state:
        for unit in state.raw_data.get("ams", []):
            remaining = _remaining(unit)
            if remaining is not None and remaining > 0:
                ams_id = int(unit.get("id", 0))
                logger.info(
                    "Auto-drying: stopping drying on printer %d AMS %d — print takes priority", printer_id, ams_id
                )
                manager.send_drying_command(printer_id, ams_id, 0, 0, mode=0)
    in_progress.pop(printer_id, None)
