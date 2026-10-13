"""Observe and stop legacy humidity-triggered drying without discarding unknown state."""

import logging
import time

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


def init_drying_state(owner, *, reset=False):
    """Initialize passive observations, unconfirmed publications and stop authority."""
    if reset:
        owner._drying_pending.clear()
        owner._ambient_humidity.reset()
        return  # Preserve any existing explicit stop authority across scheduler lifecycle.
    owner._drying_in_progress: dict[int, float] = {}
    owner._drying_owned_ams: dict[int, set[int]] = {}
    owner._drying_pending: dict[tuple[int, int], tuple[float, object]] = {}
    owner._ambient_humidity = AmbientHumidity()


def clear_pending(owner, printer_id):
    for key in list(owner._drying_pending):
        if key[0] == printer_id:
            owner._drying_pending.pop(key)
            owner._ambient_humidity.clear_ams(*key)


def expire_pending(owner, now):
    for key, (sent_at, _) in list(owner._drying_pending.items()):
        if now - sent_at >= max(4 * owner._check_interval, 120):
            owner._drying_pending.pop(key)
            owner._ambient_humidity.clear_ams(*key)


def reconcile_pending(owner, printer_id, state, now):
    """A running report retires uncertainty; it cannot establish cycle ownership."""
    expire_pending(owner, now)
    units = {int(unit.get("id", 0)): unit for unit in state.raw_data.get("ams", [])}
    for key, (_, generation) in list(owner._drying_pending.items()):
        if key[0] != printer_id:
            continue
        unit = units.get(key[1])
        if generation is not state.drying_telemetry or unit is None or (_remaining(unit) or 0) > 0:
            owner._drying_pending.pop(key)
            owner._ambient_humidity.clear_ams(*key, forget=unit is None)


def pending_reserved(owner, manager, printer_id):
    """Keep heating interlocked while a published start has an uncertain outcome."""
    if not any(key[0] == printer_id for key in getattr(owner, "_drying_pending", {})):
        return False
    state = manager.get_status(printer_id)
    if state is None or not manager.is_connected(printer_id):
        clear_pending(owner, printer_id)
        return False
    reconcile_pending(owner, printer_id, state, time.monotonic())
    return any(key[0] == printer_id for key in owner._drying_pending)


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
            clear_pending(owner, printer_id)
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
