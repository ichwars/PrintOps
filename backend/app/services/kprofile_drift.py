"""Request a lost slot calibration without guessing another nozzle's profile.

K-only pushes do not trigger on_ams_change. Check every idle status and again
before queue dispatch, retaining the scoped calibration resolver's authority.
A published selection is a request; only a later firmware report confirms it.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.ams_slot_presence import spool_present
from backend.app.services.calibration_context import resolve_spool_calibration
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.printer_manager import printer_manager
from backend.app.utils.color_utils import colors_similar
from backend.app.utils.filament_ids import normalize_slicer_filament

logger = logging.getLogger(__name__)
IDLE_STATES = frozenset({"IDLE", "FINISH", "FAILED"})
RETRY_INTERVAL_S = 30.0
NO_PROFILE_RECHECK_S = 600.0
MAX_ATTEMPTS = 3
SlotKey = tuple[int, int, int]


@dataclass
class _SlotWatch:
    next_check: float = 0.0
    attempts: int = 0
    gave_up_logged: bool = False


_watches: dict[SlotKey, _SlotWatch] = {}
_default_chosen: set[SlotKey] = set()
_running: set[int] = set()
_locks: dict[int, asyncio.Lock] = {}


def _now() -> float:
    return time.monotonic()


def reset() -> None:
    _watches.clear()
    _default_chosen.clear()
    _running.clear()
    _locks.clear()


def note_slot_configured(printer_id: int, ams_id: int, tray_id: int, cali_idx: int) -> None:
    key = (printer_id, ams_id, tray_id)
    _watches.pop(key, None)
    if cali_idx < 0:
        _default_chosen.add(key)
    else:
        _default_chosen.discard(key)


def default_chosen(printer_id: int, ams_id: int, tray_id: int) -> bool:
    return (printer_id, ams_id, tray_id) in _default_chosen


def forget_printer(printer_id: int) -> None:
    """Reconnect starts a fresh retry budget, preserving deliberate Default."""
    for key in [key for key in _watches if key[0] == printer_id]:
        _watches.pop(key, None)


def dispatch_trays(mapping: list[int] | None, use_ams: bool) -> set[int] | None:
    """Use the final dispatch mapping, preserving an explicit all-unmapped list."""
    if isinstance(mapping, list) and mapping:
        used = {tray for tray in mapping if isinstance(tray, int) and not isinstance(tray, bool) and tray >= 0}
        # The own single-nozzle command builder makes a resolved real tray
        # authoritative even when an older queue row carries use_ams=False.
        return used
    return None if use_ams else {254, 255}


def _loaded_trays(state):
    raw = getattr(state, "raw_data", None) or {}
    ams = raw.get("ams")
    units = ams.get("ams", []) if isinstance(ams, dict) else ams if isinstance(ams, list) else []
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("tray"), list):
            continue
        try:
            ams_id = int(unit["id"])
        except (KeyError, TypeError, ValueError):
            continue
        for tray in unit["tray"]:
            if not isinstance(tray, dict):
                continue
            try:
                tray_id = int(tray["id"])
            except (KeyError, TypeError, ValueError):
                continue
            yield ams_id, tray_id, ams_id if ams_id >= 128 else ams_id * 4 + tray_id, tray
    external = raw.get("vt_tray")
    external = [external] if isinstance(external, dict) else external
    for tray in external if isinstance(external, list) else []:
        if not isinstance(tray, dict):
            continue
        try:
            global_id = int(tray.get("id", 254))
        except (TypeError, ValueError):
            continue
        if global_id in (254, 255):
            yield 255, global_id - 254, global_id, tray


def _selection_lost(tray: dict) -> bool:
    index = tray.get("cali_idx")
    if index is None:
        return True
    if isinstance(index, bool):
        return False
    try:
        return int(index) < 0
    except (TypeError, ValueError, OverflowError):
        return False


def _settle(key: SlotKey, tray: dict) -> bool:
    present = spool_present(tray)
    if present is False or not tray.get("tray_type"):
        _watches.pop(key, None)
        # An occupied blank push cannot erase an intentional Default choice.
        if present is not True:
            _default_chosen.discard(key)
        return False
    if not _selection_lost(tray):
        _watches.pop(key, None)
        return False
    return key not in _default_chosen


def _due(key: SlotKey, now: float) -> bool:
    watch = _watches.get(key)
    if watch is None:
        return True
    if now < watch.next_check:
        return False
    if watch.attempts < MAX_ATTEMPTS:
        return True
    if not watch.gave_up_logged:
        watch.gave_up_logged = True
        logger.warning(
            "Slot %s still has no K-profile after %d requests; giving up until it changes", key, MAX_ATTEMPTS
        )
    return False


def _idle(state) -> bool:
    return bool(
        state is not None
        and getattr(state, "connected", False)
        and (getattr(state, "state", "") or "").upper() in IDLE_STATES
    )


def needs_check(printer_id: int, state) -> bool:
    if printer_id in _running or not _idle(state):
        return False
    now = _now()
    found = False
    for ams_id, tray_id, _, tray in _loaded_trays(state):
        key = (printer_id, ams_id, tray_id)
        if _settle(key, tray) and _due(key, now):
            found = True
    return found


def _tray_identity(tray: dict) -> tuple[str, ...]:
    """Snapshot identity before awaits, including firmware dictionaries updated in place."""
    return tuple(
        str(tray.get(field) or "").strip().upper()
        for field in ("tray_type", "tray_color", "tag_uid", "tray_uuid", "tray_info_idx")
    )


async def _assignment_identity(db, printer_id, ams_id, tray_id, spoolman_mode):
    table = SpoolmanSlotAssignment if spoolman_mode else SpoolAssignment
    spool_id = table.spoolman_spool_id if spoolman_mode else table.spool_id
    result = await db.execute(select(table.id, spool_id).where(
        table.printer_id == printer_id, table.ams_id == ams_id, table.tray_id == tray_id,
    ))
    return result.one_or_none()


async def _slot_profiles(db, printer_id, ams_id, tray_id, tray, spoolman_mode):
    if spoolman_mode:
        assignment = await db.scalar(
            select(SpoolmanSlotAssignment).where(
                SpoolmanSlotAssignment.printer_id == printer_id,
                SpoolmanSlotAssignment.ams_id == ams_id,
                SpoolmanSlotAssignment.tray_id == tray_id,
            )
        )
        if assignment is None:
            return []
        profiles = await db.scalars(
            select(SpoolmanKProfile).where(SpoolmanKProfile.spoolman_spool_id == assignment.spoolman_spool_id)
        )
        return list(profiles.all())
    assignment = await db.scalar(
        select(SpoolAssignment)
        .where(
            SpoolAssignment.printer_id == printer_id,
            SpoolAssignment.ams_id == ams_id,
            SpoolAssignment.tray_id == tray_id,
        )
        .options(selectinload(SpoolAssignment.spool).selectinload(Spool.k_profiles))
    )
    # Empty fingerprints are the own deferred preset's pending_config marker.
    if assignment is None or assignment.spool is None or not (assignment.fingerprint_type or "").strip():
        return []
    if assignment.fingerprint_type.upper() != tray.get("tray_type", "").upper():
        return []
    if (
        assignment.fingerprint_color
        and tray.get("tray_color")
        and not colors_similar(assignment.fingerprint_color, tray["tray_color"])
    ):
        return []
    for field in ("tag_uid", "tray_uuid"):
        stored, reported = getattr(assignment.spool, field, None), tray.get(field)
        if stored and reported and reported.strip("0") and stored.upper() != reported.upper():
            return []
    return assignment.spool.k_profiles


async def reapply_lost_kprofiles(
    printer_id: int, global_trays: set[int] | None = None, *, throttle: bool = True
) -> int:
    """Return the number of selection requests, never a count of confirmed writes.

    Dispatch bypasses retry intervals but serializes with an idle pass. It is
    best effort: unavailable/ambiguous contexts and unconfirmed requests are
    explicitly logged, and the existing dispatch policy continues unchanged.
    """
    from backend.app.core.database import async_session

    if throttle and printer_id in _running:
        return 0
    requested = 0
    async with _locks.setdefault(printer_id, asyncio.Lock()):
        state = printer_manager.get_status(printer_id)
        client = printer_manager.get_client(printer_id)
        if not _idle(state) or client is None:
            return 0
        _running.add(printer_id)
        try:
            async with async_session() as db:
                mode = await spoolman_owns_assignments(db)
                for ams_id, tray_id, global_id, tray in _loaded_trays(state):
                    key = (printer_id, ams_id, tray_id)
                    if not _settle(key, tray) or (global_trays is not None and global_id not in global_trays):
                        continue
                    now = _now()
                    if throttle and not _due(key, now):
                        continue
                    watch = _watches.setdefault(key, _SlotWatch())
                    watch.next_check = now + RETRY_INTERVAL_S
                    identity = _tray_identity(tray)
                    assignment = await _assignment_identity(db, printer_id, ams_id, tray_id, mode)
                    profiles = await _slot_profiles(db, printer_id, ams_id, tray_id, tray, mode)
                    if assignment is None or assignment != await _assignment_identity(db, printer_id, ams_id, tray_id, mode):
                        continue
                    context, stored, live = resolve_spool_calibration(
                        profiles, state, printer_manager.get_model(printer_id), printer_id, ams_id, tray_id
                    )
                    if stored is None or stored.cali_idx is None or stored.cali_idx < 0:
                        # A reconnect may not have reported the nozzle/table
                        # yet. Existing profiles get the normal retry interval;
                        # only a genuinely unconfigured slot uses the long TTL.
                        if not any(profile.printer_id == printer_id for profile in profiles):
                            watch.next_check = now + NO_PROFILE_RECHECK_S
                        if not throttle:
                            logger.warning(
                                "Slot %s lost its K-profile; no safe stored calibration is available before dispatch",
                                key,
                            )
                        continue
                    # Recheck after database awaits: a print or deliberate real
                    # selection may have arrived while the profile was loaded.
                    latest = printer_manager.get_status(printer_id)
                    latest_tray = next((t for a, s, _, t in _loaded_trays(latest) if (a, s) == (ams_id, tray_id)), None)
                    if (
                        not _idle(latest)
                        or latest_tray is None
                        or _tray_identity(latest_tray) != identity
                        or not _settle(key, latest_tray)
                    ):
                        continue
                    current_context, current_stored, current_live = resolve_spool_calibration(
                        profiles, latest, printer_manager.get_model(printer_id), printer_id, ams_id, tray_id
                    )
                    if (
                        context != current_context
                        or current_stored is None
                        or current_stored.cali_idx != stored.cali_idx
                    ):
                        continue
                    live = current_live
                    filament_id = live.filament_id if live is not None else ""
                    if not filament_id and stored.setting_id:
                        filament_id = normalize_slicer_filament(stored.setting_id)[0] or stored.setting_id
                    filament_id = filament_id or latest_tray.get("tray_info_idx", "")
                    watch.attempts += 1
                    sent = client.extrusion_cali_sel(
                        ams_id=ams_id,
                        tray_id=tray_id,
                        cali_idx=stored.cali_idx,
                        filament_id=filament_id,
                        nozzle_diameter=context.diameter,
                    )
                    if sent:
                        requested += 1
                        logger.info(
                            "Slot %s lost its K-profile: requested stored cali_idx=%d, attempt %d",
                            key,
                            stored.cali_idx,
                            watch.attempts,
                        )
                    if not throttle and latest_tray.get("cali_idx") != stored.cali_idx:
                        logger.warning(
                            "Slot %s K-profile recovery before dispatch is unconfirmed (requested=%s, cali_idx=%d); firmware still reports %s",
                            key,
                            bool(sent),
                            stored.cali_idx,
                            latest_tray.get("cali_idx"),
                        )
        except Exception:
            logger.exception("Printer %d K-profile recovery failed", printer_id)
        finally:
            _running.discard(printer_id)
    return requested
