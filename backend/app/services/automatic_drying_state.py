"""Observe and stop legacy humidity-triggered drying without discarding unknown state."""

import logging

from backend.app.services.ambient_humidity import AmbientHumidity
from backend.app.services.drying_ownership import has_drying_reservation, printer_operation
from backend.app.services.drying_telemetry import invalidate_drying_availability
from backend.app.services.preheat_ownership import preheat_ownership

logger = logging.getLogger(__name__)


def _remaining(unit):
    raw = unit.get("dry_time")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def init_drying_state(owner):
    """Initialize passive observations and successfully started AMS ownership."""
    owner._drying_in_progress: dict[int, float] = {}
    owner._drying_owned_ams: dict[int, set[int]] = {}
    owner._ambient_humidity = AmbientHumidity()


def sync_drying_state(in_progress, manager, *, owner):
    owned_ams = owner._drying_owned_ams
    for printer_id in list(in_progress):
        state = manager.get_status(printer_id)
        if state:
            units = {int(unit.get("id", 0)): _remaining(unit) for unit in state.raw_data.get("ams", [])}
            owned = owned_ams.get(printer_id, set())
            remaining = {ams_id for ams_id in owned if ams_id in units and units[ams_id] != 0}
            owned_ams[printer_id] = remaining
            if remaining:
                continue
        in_progress.pop(printer_id, None)
        owned_ams.pop(printer_id, None)


async def start_drying(db, manager, printer_id, ams_id, temperature, duration, filament):
    async with printer_operation(db, printer_id):
        if (
            await has_drying_reservation(db, printer_id)
            or preheat_ownership.blocks_power_off(printer_id)
            or printer_id in preheat_ownership.power_off_in_progress
        ):
            return False
        try:
            success = manager.send_drying_command(printer_id, ams_id, temperature, duration, mode=1, filament=filament)
        finally:
            invalidate_drying_availability(manager.get_status(printer_id))
        await db.commit()
        return success


async def stop_drying(in_progress, printer_id, manager, session_factory, *, owner=None):
    owned_ams = owner._drying_owned_ams if owner is not None else {}
    async with session_factory() as db, printer_operation(db, printer_id):
        if await has_drying_reservation(db, printer_id):
            return
        _stop_drying(in_progress, printer_id, manager, owned_ams)
        if owner is not None:
            owner._ambient_humidity.clear_printer(printer_id)
        invalidate_drying_availability(manager.get_status(printer_id))
        await db.commit()


def _stop_drying(in_progress, printer_id, manager, owned_ams):
    state = manager.get_status(printer_id)
    if state:
        for unit in state.raw_data.get("ams", []):
            remaining = _remaining(unit)
            if int(unit.get("id", 0)) in owned_ams.get(printer_id, set()) and remaining is not None and remaining > 0:
                ams_id = int(unit.get("id", 0))
                logger.info(
                    "Auto-drying: stopping drying on printer %d AMS %d — print takes priority", printer_id, ams_id
                )
                manager.send_drying_command(printer_id, ams_id, 0, 0, mode=0)
    in_progress.pop(printer_id, None)
    owned_ams.pop(printer_id, None)
