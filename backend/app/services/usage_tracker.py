"""Automatic filament consumption tracking.

Captures AMS tray remain% at print start, then computes consumption
deltas at print complete to update spool weight_used and last_used.

Primary tracking uses 3MF slicer estimates (precise per-filament data).
AMS remain% delta is the fallback for trays not covered by 3MF data.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spool_usage_history import SpoolUsageHistory

logger = logging.getLogger(__name__)


def _library_3mf_type_filter(library_file):
    """Match current 3MF types plus legacy sliced rows not yet backfilled."""
    return or_(
        library_file.file_type.ilike("3mf"),
        library_file.file_type.ilike("gcode.3mf"),
        and_(library_file.file_type.ilike("gcode"), library_file.filename.ilike("%.gcode.3mf")),
    )


def _decode_mqtt_mapping(mapping_raw: list | None) -> list[int] | None:
    """Decode MQTT mapping field (snow-encoded) to printops global tray IDs.

    The printer's MQTT mapping field is an array indexed by slicer filament slot
    (0-based). Each value uses snow encoding: ams_hw_id * 256 + local_slot.
    65535 means unmapped.

    Returns a list of printops global tray IDs (or -1 for unmapped), or None if
    no valid mappings found.
    """
    if not isinstance(mapping_raw, list) or not mapping_raw:
        return None

    result = []
    for value in mapping_raw:
        if not isinstance(value, int) or value >= 65535:
            result.append(-1)
            continue

        ams_hw_id = value >> 8
        slot = value & 0xFF

        if 0 <= ams_hw_id <= 3:
            # Regular AMS: sequential global ID
            result.append(ams_hw_id * 4 + (slot & 0x03))
        elif 128 <= ams_hw_id <= 135:
            # AMS-HT: global ID is the hardware ID (one slot per unit)
            result.append(ams_hw_id)
        elif ams_hw_id in (254, 255):
            # External spool
            result.append(254 if slot != 255 else 255)
        else:
            result.append(-1)

    # Only return if at least one valid mapping exists
    if all(v < 0 for v in result):
        return None

    return result


def _spool_color_to_hex(rgba: str | None) -> str | None:
    """Normalise a ``Spool.rgba`` value (``RRGGBBAA`` hex, no ``#``) to the
    ``#RRGGBB`` form archives store in ``filament_color``.

    Alpha is dropped — the archive colour list and the Color Distribution
    graph treat filament colour as opaque. Returns ``None`` for a missing or
    too-short value so the caller can fall back to the 3MF colour.
    """
    if not rgba:
        return None
    h = rgba.strip().lstrip("#")
    if len(h) < 6:
        return None
    return "#" + h[:6].upper()


def _archive_colors_from_spools(filament_usage: list[dict], results: list[dict]) -> list[str] | None:
    """Slot-ordered, de-duplicated hex colours for an archive's ``filament_color``,
    taken from the inventory spools that actually fed the print (#1494).

    The slicer's 3MF carries its own ``filament_colour`` per slot — a value
    picked independently of the colour the user curates on the matched
    inventory spool. So an archive printed from a ``#000000`` inventory spool
    would otherwise show the slicer's near-black ``#161616``. Once usage
    tracking has resolved the used slots to spools, the spool colours are the
    authoritative source and replace the 3MF values.

    Returns ``None`` — leave the 3MF colour untouched — unless *every* slot
    with non-zero usage was matched to a spool that carries a colour. A
    partial rewrite would silently drop the unmatched slots' colours from the
    archive (and the Color Distribution graph), so it is all-or-nothing.
    """
    used_slots = {u["slot_id"] for u in filament_usage if u.get("used_g", 0) > 0 and u.get("slot_id") is not None}
    if not used_slots:
        return None

    slot_color: dict[int, str] = {}
    for r in results:
        slot_id = r.get("slot_id")
        color = r.get("color")
        if slot_id is not None and color:
            slot_color.setdefault(slot_id, color)

    if not used_slots.issubset(slot_color):
        return None

    ordered: list[str] = []
    for slot_id in sorted(used_slots):
        color = slot_color[slot_id]
        if color not in ordered:
            ordered.append(color)
    return ordered


def _apply_archive_colors_from_spools(
    archive, archive_id: int | None, filament_usage: list[dict], results: list[dict]
) -> None:
    """Use fully resolved inventory colours without dropping unmatched slots."""
    if archive is None:
        return
    spool_colors = _archive_colors_from_spools(filament_usage, results)
    if not spool_colors:
        return
    joined = ",".join(spool_colors)
    if joined != archive.filament_color:
        logger.info(
            "[UsageTracker] 3MF: archive %s filament_color %r -> %r (from inventory spools)",
            archive_id,
            archive.filament_color,
            joined,
        )
        archive.filament_color = joined


def _global_tray_to_assignment_key(global_tray_id: int) -> tuple[int, int]:
    if global_tray_id >= 254:
        return (255, global_tray_id - 254)
    if global_tray_id >= 128:
        return (global_tray_id, 0)
    return (global_tray_id // 4, global_tray_id % 4)


def _match_slots_by_color(
    filament_usage: list[dict],
    ams_raw: dict | list | None,
) -> list[int] | None:
    """Match 3MF filament slots to AMS trays by color.

    Fallback mapping for printers that don't provide the MQTT mapping field
    or request topic subscription (e.g. A1, A1 Mini, P1S, P2S).

    Compares the 3MF slicer filament color (per slot) against each AMS tray's
    color to find a unique match. Only returns a mapping if every used slot
    matches exactly one tray (no ambiguity).

    Args:
        filament_usage: List of 3MF slot dicts with 'slot_id', 'color', 'type'
        ams_raw: raw_data["ams"] dict or list from printer state

    Returns:
        List of global tray IDs indexed by slicer slot (0-based), or None.
    """
    if not filament_usage or not ams_raw:
        return None

    ams_data = ams_raw.get("ams", []) if isinstance(ams_raw, dict) else ams_raw if isinstance(ams_raw, list) else []
    if not ams_data:
        return None

    # Build map of normalized color → list of global tray IDs
    color_to_trays: dict[str, list[int]] = {}
    for ams_unit in ams_data:
        ams_id = int(ams_unit.get("id", 0))
        for tray in ams_unit.get("tray", []):
            tray_id = int(tray.get("id", 0))
            tray_color = tray.get("tray_color", "")
            tray_type = tray.get("tray_type", "")
            if not tray_color or not tray_type:
                continue
            # Normalize AMS color: strip alpha (last 2 chars), lowercase
            norm = tray_color[:6].lower() if len(tray_color) >= 6 else tray_color.lower()
            if ams_id >= 128:
                global_id = ams_id  # AMS-HT
            else:
                global_id = ams_id * 4 + tray_id
            color_to_trays.setdefault(norm, []).append(global_id)

    if not color_to_trays:
        return None

    # Find max slot_id to size the result array
    max_slot = max(u.get("slot_id", 0) for u in filament_usage)
    if max_slot <= 0:
        return None

    result = [-1] * max_slot
    used_trays: set[int] = set()

    for usage in filament_usage:
        slot_id = usage.get("slot_id", 0)
        if slot_id <= 0:
            continue
        slot_color = usage.get("color", "").lstrip("#").lower()
        if len(slot_color) < 6:
            return None  # Can't match without a valid color

        slot_color = slot_color[:6]  # Strip alpha if present
        candidates = color_to_trays.get(slot_color, [])
        # Filter out trays already claimed by another slot
        available = [t for t in candidates if t not in used_trays]

        if len(available) != 1:
            # Ambiguous (multiple trays with same color) or no match
            return None

        result[slot_id - 1] = available[0]
        used_trays.add(available[0])

    # Only return if at least one valid mapping exists
    if all(v < 0 for v in result):
        return None

    logger.info("[UsageTracker] Color-matched slot_to_tray: %s", result)
    return result


@dataclass
class PrintSession:
    printer_id: int
    print_name: str
    started_at: datetime
    subtask_id: str | None = None
    tray_remain_start: dict[tuple[int, int], int] = field(default_factory=dict)
    # tray_now at print start (correct value, unlike at completion where it's 255)
    tray_now_at_start: int = -1
    # Snapshot of spool assignments at print start: {(ams_id, tray_id): spool_id}
    # Prevents usage loss when on_ams_change unlinks a spool mid-print
    spool_assignments: dict[tuple[int, int], int] = field(default_factory=dict)
    # AMS mapping from print command (captured at start, needed when auto-archive is off)
    ams_mapping: list[int] | None = None
    # Queue item's plate_id when this print is a multi-plate 3MF dispatched for a
    # single plate (#1697). None for non-queue prints — the file's first/only plate
    # is the default and the 3MF parser already returns the full file in that case.
    plate_id: int | None = None
    # Fixed at print start. None marks legacy rows that predate issue #130.
    spoolman_owns_usage: bool | None = None


# Module-level storage, keyed by printer_id. The same evidence is mirrored to
# ``active_print_sessions`` so completion can recover after a restart.
_active_sessions: dict[int, PrintSession] = {}
_tray_change_locks: dict[int, asyncio.Lock] = {}


def _normalize_subtask_id(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized if normalized not in ("", "0") else None


def _session_matches_completion(session: PrintSession, data: dict) -> bool:
    event_subtask_id = _normalize_subtask_id(data.get("subtask_id"))
    if event_subtask_id and session.subtask_id:
        return event_subtask_id == session.subtask_id
    event_name = (data.get("subtask_name") or data.get("filename") or "").strip()
    return not event_name or not session.print_name or event_name == session.print_name.strip()


def take_active_session_for_completion(printer_id: int, data: dict) -> tuple[PrintSession | None, bool]:
    """Atomically claim the in-memory generation before another start can replace it."""
    session = _active_sessions.get(printer_id)
    if session is None:
        return None, False
    if not _session_matches_completion(session, data):
        return None, True
    return _active_sessions.pop(printer_id), True


def _tray_key_to_str(key: tuple[int, int]) -> str:
    return f"{key[0]}-{key[1]}"


def _tray_key_from_str(key: str) -> tuple[int, int] | None:
    ams_str, separator, tray_str = key.partition("-")
    if not separator:
        return None
    try:
        return int(ams_str), int(tray_str)
    except ValueError:
        return None


def _tray_map_to_json(mapping: dict[tuple[int, int], int]) -> dict[str, int]:
    return {_tray_key_to_str(key): value for key, value in mapping.items()}


def _tray_map_from_json(mapping: dict | None) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for raw_key, value in (mapping or {}).items():
        key = _tray_key_from_str(str(raw_key))
        if key is not None and isinstance(value, int):
            result[key] = value
    return result


async def persist_session(
    db: AsyncSession,
    session: PrintSession,
    tray_change_log: list | None = None,
) -> None:
    """Upsert one printer's active attribution evidence."""
    from backend.app.models.active_print_session import ActivePrintSession

    row = await db.get(ActivePrintSession, session.printer_id)
    if row is None:
        row = ActivePrintSession(printer_id=session.printer_id)
        db.add(row)

    row.print_name = session.print_name or ""
    row.subtask_id = session.subtask_id
    row.started_at = session.started_at.replace(tzinfo=None)
    row.tray_now_at_start = session.tray_now_at_start
    row.plate_id = session.plate_id
    row.ams_mapping = list(session.ams_mapping) if session.ams_mapping else None
    row.spool_assignments = _tray_map_to_json(session.spool_assignments) or None
    row.tray_remain_start = _tray_map_to_json(session.tray_remain_start) or None
    row.tray_change_log = [list(entry) for entry in (tray_change_log or [])] or None
    row.spoolman_owns_usage = session.spoolman_owns_usage
    await db.commit()


async def record_tray_change(db: AsyncSession, printer_id: int, tray_global: int, layer_num: int) -> None:
    """Append an observed tray transition to an active session, if present."""
    from backend.app.models.active_print_session import ActivePrintSession

    async with _tray_change_locks.setdefault(printer_id, asyncio.Lock()):
        row = await db.get(ActivePrintSession, printer_id)
        if row is None:
            return

        log = [list(entry) for entry in (row.tray_change_log or [])]
        entry = [tray_global, layer_num]
        if log and log[-1] == entry:
            return
        log.append(entry)
        row.tray_change_log = log
        await db.commit()


async def get_persisted_print_identity(db: AsyncSession, printer_id: int) -> tuple[str | None, str | None]:
    """Return the persisted name and printer-assigned job identity."""
    from backend.app.models.active_print_session import ActivePrintSession

    row = await db.get(ActivePrintSession, printer_id)
    return (row.print_name, row.subtask_id) if row is not None else (None, None)


async def get_persisted_print_name(db: AsyncSession, printer_id: int) -> str | None:
    """Backward-compatible name-only identity lookup."""
    return (await get_persisted_print_identity(db, printer_id))[0]


def _session_from_row(row) -> PrintSession:
    started_at = row.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return PrintSession(
        printer_id=row.printer_id,
        print_name=row.print_name or "",
        subtask_id=row.subtask_id,
        started_at=started_at,
        tray_remain_start=_tray_map_from_json(row.tray_remain_start),
        tray_now_at_start=row.tray_now_at_start,
        spool_assignments=_tray_map_from_json(row.spool_assignments),
        ams_mapping=list(row.ams_mapping) if row.ams_mapping else None,
        plate_id=row.plate_id,
        spoolman_owns_usage=getattr(row, "spoolman_owns_usage", None),
    )


async def load_persisted_session_for_completion(db: AsyncSession, printer_id: int, data: dict) -> PrintSession | None:
    """Load only the durable generation identified by a completion event."""
    from backend.app.models.active_print_session import ActivePrintSession

    row = await db.get(ActivePrintSession, printer_id)
    if row is None:
        return None
    session = _session_from_row(row)
    return session if _session_matches_completion(session, data) else None


async def update_session_context(
    db: AsyncSession,
    printer_id: int,
    *,
    ams_mapping: list[int] | None,
    plate_id: int | None,
    subtask_id: str | None,
) -> bool:
    """Persist authoritative dispatch context learned after the MQTT start edge."""
    from backend.app.models.active_print_session import ActivePrintSession

    row = await db.get(ActivePrintSession, printer_id)
    active = _active_sessions.get(printer_id)
    changed = False
    normalized_subtask_id = _normalize_subtask_id(subtask_id)
    for target in (row, active):
        if target is None:
            continue
        if ams_mapping and not target.ams_mapping:
            target.ams_mapping = list(ams_mapping)
            changed = True
        if plate_id is not None and target.plate_id is None:
            target.plate_id = plate_id
            changed = True
        if normalized_subtask_id and target.subtask_id != normalized_subtask_id:
            target.subtask_id = normalized_subtask_id
            changed = True
    if row is not None and changed:
        await db.commit()
    return changed


async def restore_session(db: AsyncSession, printer_id: int, register_active: bool = True) -> list[list[int]] | None:
    """Restore a session and return its tray-change log."""
    from backend.app.models.active_print_session import ActivePrintSession

    row = await db.get(ActivePrintSession, printer_id)
    if row is None:
        return None

    session = _session_from_row(row)
    if register_active:
        _active_sessions[printer_id] = session
    log = [list(entry) for entry in (row.tray_change_log or [])]
    logger.info(
        "[UsageTracker] Restored print session for printer %d: plate_id=%s, "
        "ams_mapping=%s, %d assignments, tray_change_log=%s",
        printer_id,
        row.plate_id,
        row.ams_mapping,
        len(row.spool_assignments or {}),
        log,
    )
    return log


async def clear_persisted_session(
    db: AsyncSession, printer_id: int, expected_started_at: datetime | None = None
) -> None:
    """Delete persisted evidence after terminal completion."""
    from sqlalchemy import delete

    from backend.app.models.active_print_session import ActivePrintSession

    statement = delete(ActivePrintSession).where(ActivePrintSession.printer_id == printer_id)
    if expected_started_at is not None:
        statement = statement.where(ActivePrintSession.started_at == expected_started_at.replace(tzinfo=None))
    await db.execute(statement)
    await db.commit()


async def discard_session(db: AsyncSession, printer_id: int, expected_session: PrintSession | None = None) -> None:
    """Clear both in-memory and persisted active-print evidence."""
    active = _active_sessions.get(printer_id)
    if expected_session is None or (
        active is not None and _to_epoch_seconds(active.started_at) == _to_epoch_seconds(expected_session.started_at)
    ):
        _active_sessions.pop(printer_id, None)
        _tray_change_locks.pop(printer_id, None)
    await clear_persisted_session(
        db,
        printer_id,
        expected_started_at=expected_session.started_at if expected_session is not None else None,
    )


def _to_epoch_seconds(value: datetime | None) -> float | None:
    """Convert datetime to epoch seconds, assuming UTC for naive values."""
    if value is None:
        return None
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


async def _resolve_spool_id_for_tray(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    db: AsyncSession,
    spool_assignments_snapshot: dict[tuple[int, int], int] | None = None,
    print_started_at: datetime | None = None,
) -> int | None:
    """Resolve spool ID for a tray with safe support for mid-print reassignment.

    Resolution order:
    1. If snapshot exists and live assignment changed *during this print*, use live spool.
    2. Otherwise use snapshot spool when available.
    3. Fall back to live assignment.
    """
    key = (ams_id, tray_id)
    snapshot_spool_id = spool_assignments_snapshot.get(key) if spool_assignments_snapshot else None

    # Backward-compatible fast path: if we have a snapshot but no print-start
    # timestamp, preserve legacy behavior and avoid extra DB lookups.
    if snapshot_spool_id is not None and print_started_at is None:
        return snapshot_spool_id

    result = await db.execute(
        select(SpoolAssignment).where(
            SpoolAssignment.printer_id == printer_id,
            SpoolAssignment.ams_id == ams_id,
            SpoolAssignment.tray_id == tray_id,
        )
    )
    live_assignment = result.scalar_one_or_none()

    if snapshot_spool_id is not None:
        if live_assignment and live_assignment.spool_id != snapshot_spool_id:
            live_created_ts = _to_epoch_seconds(getattr(live_assignment, "created_at", None))
            started_ts = _to_epoch_seconds(print_started_at)
            if live_created_ts is not None and started_ts is not None and live_created_ts >= started_ts:
                logger.info(
                    "[UsageTracker] Assignment changed during print for printer %d AMS%d-T%d: snapshot spool %d -> live spool %d",
                    printer_id,
                    ams_id,
                    tray_id,
                    snapshot_spool_id,
                    live_assignment.spool_id,
                )
                return live_assignment.spool_id
        return snapshot_spool_id

    if live_assignment:
        return live_assignment.spool_id

    return None


async def on_print_start(
    printer_id: int,
    data: dict,
    printer_manager,
    db: AsyncSession | None = None,
    spoolman_owns_usage: bool = False,
) -> None:
    """Capture and persist attribution evidence at print start.

    Spoolman owns its stock writes when enabled, but it still needs the shared
    tray-change history. In that mode the durable row is written without
    publishing an internal ``_active_sessions`` guard.
    """
    state = printer_manager.get_status(printer_id)
    raw_data = state.raw_data if state and isinstance(state.raw_data, dict) else {}
    if not raw_data:
        logger.debug("[UsageTracker] No tray state for printer %d; persisting ownership only", printer_id)

    ams_raw = raw_data.get("ams", [])
    ams_data = ams_raw.get("ams", []) if isinstance(ams_raw, dict) else ams_raw if isinstance(ams_raw, list) else []

    tray_remain_start: dict[tuple[int, int], int] = {}
    skipped_invalid: list[str] = []

    for ams_unit in ams_data:
        ams_id = int(ams_unit.get("id", 0))
        for tray in ams_unit.get("tray", []):
            tray_id = int(tray.get("id", 0))
            remain = tray.get("remain", -1)
            if isinstance(remain, int) and 0 <= remain <= 100:
                tray_remain_start[(ams_id, tray_id)] = remain
            else:
                skipped_invalid.append(f"AMS{ams_id}-T{tray_id}(remain={remain})")

    # Also capture VT (external) tray remain% — these are separate from AMS units
    vt_tray_raw = raw_data.get("vt_tray") or []
    if isinstance(vt_tray_raw, dict):
        vt_tray_raw = [vt_tray_raw]
    for vt in vt_tray_raw:
        if not isinstance(vt, dict):
            continue
        vt_id = int(vt.get("id", 254))
        # VT tray id 254 → (ams_id=255, tray_id=0), id 255 → (ams_id=255, tray_id=1)
        vt_tray_id = vt_id - 254
        remain = vt.get("remain", -1)
        if isinstance(remain, int) and 0 <= remain <= 100:
            tray_remain_start[(255, vt_tray_id)] = remain
        else:
            skipped_invalid.append(f"VT{vt_id}(remain={remain})")

    if skipped_invalid:
        logger.info(
            "[UsageTracker] Skipped trays with invalid remain%% for printer %d: %s",
            printer_id,
            ", ".join(skipped_invalid),
        )

    if not ams_data and not vt_tray_raw:
        logger.debug("[UsageTracker] No AMS or VT tray data for printer %d; persisting ownership only", printer_id)

    print_name = data.get("subtask_name", "") or data.get("filename", "unknown")

    # Capture tray_now at print start (reliable, unlike at completion where it's 255)
    tray_now_at_start = getattr(state, "tray_now", -1)

    # --- Diagnostic logging: dump mapping-related MQTT fields at print start ---
    # This helps us understand what each printer model reports for slot-to-tray mapping.
    mapping_field = raw_data.get("mapping")
    logger.info(
        "[UsageTracker] PRINT START printer %d: mapping=%s, tray_now=%d, last_loaded_tray=%s",
        printer_id,
        mapping_field,
        tray_now_at_start,
        getattr(state, "last_loaded_tray", "N/A"),
    )
    # Log all raw_data keys containing "map" or "ams" for discovery
    map_keys = {k: raw_data[k] for k in raw_data if "map" in k.lower()}
    if map_keys:
        logger.info("[UsageTracker] PRINT START printer %d: mapping-related keys: %s", printer_id, map_keys)
    # Log per-tray summary: tray_now, tray_tar, tray_type, tray_color for each slot
    for ams_unit in ams_data:
        ams_id = int(ams_unit.get("id", 0))
        tray_summary = []
        for tray in ams_unit.get("tray", []):
            tray_summary.append(
                f"T{tray.get('id', '?')}(type={tray.get('tray_type', '')}, "
                f"color={tray.get('tray_color', '')}, "
                f"now={ams_raw.get('tray_now', '?') if isinstance(ams_raw, dict) else '?'}, "
                f"tar={ams_raw.get('tray_tar', '?') if isinstance(ams_raw, dict) else '?'})"
            )
        logger.info("[UsageTracker] PRINT START printer %d AMS %d: %s", printer_id, ams_id, ", ".join(tray_summary))

    # Snapshot only the ledger that owns this print. Inactive built-in rows may
    # remain after a mode switch and must never become Spoolman attribution.
    spool_assignments: dict[tuple[int, int], int] = {}
    if db and not spoolman_owns_usage:
        assign_result = await db.execute(select(SpoolAssignment).where(SpoolAssignment.printer_id == printer_id))
        for assignment in assign_result.scalars().all():
            spool_assignments[(assignment.ams_id, assignment.tray_id)] = assignment.spool_id
        if spool_assignments:
            logger.info(
                "[UsageTracker] Snapshotted %d spool assignments for printer %d: %s",
                len(spool_assignments),
                printer_id,
                {f"{k[0]}-{k[1]}": v for k, v in spool_assignments.items()},
            )

    # Capture the queue item's plate_id so 3MF parsing at completion is scoped to
    # the plate that actually ran, not the whole multi-plate file (#1697).
    plate_id: int | None = None
    if db:
        from backend.app.models.print_queue import PrintQueueItem

        queue_result = await db.execute(
            select(PrintQueueItem)
            .where(PrintQueueItem.printer_id == printer_id)
            .where(PrintQueueItem.status == "printing")
        )
        queue_item = queue_result.scalars().first()
        if queue_item is not None:
            plate_id = queue_item.plate_id

    # Always create session (even without valid remain data) so print_name
    # is available at completion for 3MF-based tracking
    session = PrintSession(
        printer_id=printer_id,
        print_name=print_name,
        subtask_id=_normalize_subtask_id(data.get("subtask_id") or getattr(state, "subtask_id", None)),
        started_at=datetime.now(timezone.utc),
        tray_remain_start=tray_remain_start,
        tray_now_at_start=tray_now_at_start,
        spool_assignments=spool_assignments,
        ams_mapping=data.get("ams_mapping"),
        plate_id=plate_id,
        spoolman_owns_usage=spoolman_owns_usage,
    )
    if spoolman_owns_usage:
        _active_sessions.pop(printer_id, None)
    else:
        _active_sessions[printer_id] = session

    if db:
        try:
            await persist_session(db, session, getattr(state, "tray_change_log", None))
        except Exception:
            logger.exception("[UsageTracker] Failed to persist print session for printer %d", printer_id)

    if tray_remain_start:
        logger.info(
            "[UsageTracker] Captured start remain%% for printer %d (%d trays): %s",
            printer_id,
            len(tray_remain_start),
            {f"{k[0]}-{k[1]}": v for k, v in tray_remain_start.items()},
        )
    else:
        logger.debug("[UsageTracker] No valid remain%% for printer %d, 3MF fallback available", printer_id)


async def _pop_or_restore_session(db: AsyncSession, printer_id: int) -> PrintSession | None:
    session = _active_sessions.pop(printer_id, None)
    if session is not None:
        return session
    try:
        await restore_session(db, printer_id)
    except Exception:
        logger.exception("[UsageTracker] Failed to restore print session for printer %d", printer_id)
    return _active_sessions.pop(printer_id, None)


async def _completion_3mf_path(printer_id, data, session, ams_mapping, db):
    """Resolve slicer evidence for an archive-less completion."""
    from backend.app.core.config import settings as app_settings

    search_filename = data.get("filename") or data.get("subtask_name") or (session.print_name if session else "")
    if not search_filename:
        return None
    return await _find_3mf_by_filename(
        printer_id,
        search_filename,
        db,
        app_settings.base_dir,
        print_name=session.print_name if session else data.get("subtask_name"),
        plate_id=session.plate_id if session else None,
        ams_mapping=ams_mapping,
    )


async def on_print_complete(
    printer_id: int,
    data: dict,
    printer_manager,
    db: AsyncSession,
    archive_id: int | None = None,
    ams_mapping: list[int] | None = None,
    claimed_session: PrintSession | None = None,
    session_claimed: bool = False,
) -> list[dict]:
    """Compute consumption deltas and update spool weight_used/last_used.

    Uses two tracking strategies in priority order:
    1. 3MF per-filament estimates (primary) — precise slicer data for all spools
    2. AMS remain% delta (fallback) — only for trays not already handled by 3MF

    """
    from sqlalchemy import select

    from backend.app.api.routes.settings import get_setting
    from backend.app.models.spool_usage_history import SpoolUsageHistory

    session = claimed_session if session_claimed else await _pop_or_restore_session(db, printer_id)
    status = data.get("status", "completed")
    results = []
    handled_trays: set[tuple[int, int]] = set()
    unassigned_trays: list[int] = []

    # Fetch default filament cost from settings for fallback
    default_cost_str = await get_setting(db, "default_filament_cost")
    default_filament_cost = float(default_cost_str) if default_cost_str else 0.0

    # Fall back to ams_mapping captured at print start (needed when auto-archive is off
    # and the caller can't retrieve the mapping from _print_ams_mappings without archive_id)
    if not ams_mapping and session and session.ams_mapping:
        ams_mapping = session.ams_mapping

    logger.info(
        "[UsageTracker] on_print_complete: printer=%d, archive=%s, session=%s, ams_mapping=%s",
        printer_id,
        archive_id,
        "yes" if session else "no",
        ams_mapping,
    )

    # --- Diagnostic logging: dump mapping-related MQTT fields at print completion ---
    state = printer_manager.get_status(printer_id)
    if state and state.raw_data:
        logger.info(
            "[UsageTracker] PRINT COMPLETE printer %d: mapping=%s, tray_now=%s, last_loaded_tray=%s",
            printer_id,
            state.raw_data.get("mapping"),
            state.tray_now,
            getattr(state, "last_loaded_tray", "N/A"),
        )

    # --- Path 1 (PRIMARY): 3MF per-filament estimates ---
    print_name = (
        (session.print_name if session else None) or data.get("subtask_name", "") or data.get("filename", "unknown")
    )

    # When auto-archive is disabled (archive_id=None), try to find a 3MF by filename
    # from the library or previous archives so we can still track filament usage.
    threemf_path = None if archive_id else await _completion_3mf_path(printer_id, data, session, ams_mapping, db)

    if archive_id or threemf_path:
        threemf_results = await _track_from_3mf(
            printer_id,
            archive_id,
            status,
            print_name,
            handled_trays,
            printer_manager,
            db,
            ams_mapping=ams_mapping,
            tray_now_at_start=session.tray_now_at_start if session else -1,
            last_progress=data.get("last_progress", 0.0),
            last_layer_num=data.get("last_layer_num", 0),
            default_filament_cost=default_filament_cost,
            spool_assignments=session.spool_assignments if session else None,
            print_started_at=session.started_at if session else None,
            threemf_path=threemf_path,
            plate_id=session.plate_id if session else None,
            unassigned_trays=unassigned_trays,
        )
        results.extend(threemf_results)

    # --- Path 2 (FALLBACK): AMS remain% delta (only for trays not handled by 3MF) ---
    if session and session.tray_remain_start:
        state = printer_manager.get_status(printer_id)
        if state and state.raw_data:
            ams_raw = state.raw_data.get("ams", [])
            ams_data = (
                ams_raw.get("ams", []) if isinstance(ams_raw, dict) else ams_raw if isinstance(ams_raw, list) else []
            )

            # Build set of trays actually involved in this print (#1269).
            # Without this guard, swapping a spool in an UNUSED slot mid-print
            # makes that slot's remain% drop to 0, which the fallback below
            # would otherwise charge to the originally-assigned spool.
            print_used_keys: set[tuple[int, int]] = set()
            if ams_mapping:
                for gid in ams_mapping:
                    if isinstance(gid, int) and gid >= 0:
                        print_used_keys.add(_global_tray_to_assignment_key(gid))
            for change in getattr(state, "tray_change_log", None) or []:
                if isinstance(change, (tuple, list)) and len(change) >= 1:
                    gid = change[0]
                    if isinstance(gid, int) and gid >= 0:
                        print_used_keys.add(_global_tray_to_assignment_key(gid))
            if session.tray_now_at_start is not None and session.tray_now_at_start >= 0:
                print_used_keys.add(_global_tray_to_assignment_key(session.tray_now_at_start))

            # Collect all trays to check: AMS trays + VT (external) trays
            # Each entry: (ams_id_for_assignment, tray_id_for_assignment, current_remain, label)
            trays_to_check: list[tuple[int, int, int, str]] = []

            for ams_unit in ams_data:
                ams_id = int(ams_unit.get("id", 0))
                for tray in ams_unit.get("tray", []):
                    tray_id = int(tray.get("id", 0))
                    remain = tray.get("remain", -1)
                    trays_to_check.append((ams_id, tray_id, remain, f"AMS{ams_id}-T{tray_id}"))

            # VT (external) trays — same remain% delta logic
            vt_tray_raw = state.raw_data.get("vt_tray") or []
            if isinstance(vt_tray_raw, dict):
                vt_tray_raw = [vt_tray_raw]
            for vt in vt_tray_raw:
                if not isinstance(vt, dict):
                    continue
                vt_id = int(vt.get("id", 254))
                vt_tray_id = vt_id - 254  # 254→0, 255→1
                remain = vt.get("remain", -1)
                trays_to_check.append((255, vt_tray_id, remain, f"VT{vt_id}"))

            for assign_ams_id, assign_tray_id, current_remain, tray_label in trays_to_check:
                key = (assign_ams_id, assign_tray_id)

                if key in handled_trays:
                    continue  # Already tracked via 3MF

                if key not in session.tray_remain_start:
                    continue

                # Skip trays the print never touched. Only enforce when we have
                # evidence of which trays the print used; if print_used_keys is
                # empty (no mapping, no change log, no tray_now_at_start) keep
                # the legacy behavior of scanning every tray.
                if print_used_keys and key not in print_used_keys:
                    logger.info(
                        "[UsageTracker] %s: not in print mapping/tray_change_log — skipping fallback for printer %d",
                        tray_label,
                        printer_id,
                    )
                    continue

                if not isinstance(current_remain, int) or current_remain < 0 or current_remain > 100:
                    logger.info(
                        "[UsageTracker] %s: invalid remain%% at completion (%s), skipping fallback for printer %d",
                        tray_label,
                        current_remain,
                        printer_id,
                    )
                    continue

                start_remain = session.tray_remain_start[key]
                delta_pct = start_remain - current_remain

                if delta_pct <= 0:
                    continue  # No consumption or tray was refilled

                spool_id = await _resolve_spool_id_for_tray(
                    printer_id=printer_id,
                    ams_id=assign_ams_id,
                    tray_id=assign_tray_id,
                    db=db,
                    spool_assignments_snapshot=session.spool_assignments,
                    print_started_at=session.started_at,
                )
                if spool_id is None:
                    logger.info(
                        "[UsageTracker] %s: no spool assigned, skipping fallback for printer %d",
                        tray_label,
                        printer_id,
                    )
                    continue

                # Load spool
                spool_result = await db.execute(select(Spool).where(Spool.id == spool_id))
                spool = spool_result.scalar_one_or_none()
                if not spool:
                    continue

                # Compute weight consumed
                weight_grams = (delta_pct / 100.0) * spool.label_weight

                # Update spool
                spool.weight_used = (spool.weight_used or 0) + weight_grams
                spool.last_used = datetime.now(timezone.utc)

                # Calculate cost for this usage
                cost = None
                cost_per_kg = spool.cost_per_kg if spool.cost_per_kg is not None else default_filament_cost
                if cost_per_kg > 0:
                    cost = round((weight_grams / 1000.0) * cost_per_kg, 2)

                # Insert usage history record
                history = SpoolUsageHistory(
                    spool_id=spool.id,
                    printer_id=printer_id,
                    print_name=session.print_name,
                    weight_used=round(weight_grams, 1),
                    percent_used=delta_pct,
                    status=status,
                    cost=cost,
                    archive_id=archive_id,
                )
                db.add(history)

                handled_trays.add(key)
                results.append(
                    {
                        "spool_id": spool.id,
                        "weight_used": round(weight_grams, 1),
                        "percent_used": delta_pct,
                        "ams_id": assign_ams_id,
                        "tray_id": assign_tray_id,
                        "material": spool.material,
                        "cost": cost,
                        # AMS remain%-delta fallback has no 3MF slot — slot_id
                        # stays None so it is excluded from the colour rewrite.
                        "slot_id": None,
                        "color": _spool_color_to_hex(spool.rgba),
                    }
                )

                logger.info(
                    "[UsageTracker] Spool %d consumed %.1fg (%d%%) on printer %d %s (AMS fallback, %s)",
                    spool.id,
                    weight_grams,
                    delta_pct,
                    printer_id,
                    tray_label,
                    status,
                )

    if results:
        await db.commit()

    # --- Update PrintArchive.cost from THIS print session only ---
    #
    # Cover any filament weight that wasn't tracked by an inventory spool with
    # the global default rate (#1344). Without this, a multi-color print where
    # only some AMS trays are mapped to inventory spools would record only the
    # mapped slots' share — e.g. $0.01 for a 110g print when 3 of 4 trays had
    # no spool record. The initial cost set by archive.py (total grams *
    # primary cost_per_kg) is fine on its own, but this block overwrites it,
    # so the overwrite must reconstruct the whole-print cost.

    if archive_id and results:
        from sqlalchemy import func, select

        from backend.app.models.archive import PrintArchive
        from backend.app.models.print_log import PrintLogEntry

        archive_result = await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))
        archive = archive_result.scalar_one_or_none()
        if archive:
            total_cost = sum(r.get("cost", 0) or 0 for r in results)
            tracked_grams = sum(r.get("weight_used", 0) or 0 for r in results)
            archive_grams = archive.filament_used_grams or 0
            untracked_grams = max(0.0, archive_grams - tracked_grams)
            if untracked_grams > 0 and default_filament_cost > 0:
                total_cost += (untracked_grams / 1000.0) * default_filament_cost
            if total_cost > 0:
                # Only overwrite archive.cost on the first run. Reprint actuals
                # live in PrintLogEntry; the archive card keeps the first run's
                # cost so a failed reprint doesn't visually clobber a successful
                # 100 g/$X print with a 10 g/$X/10 partial (#1378).
                _existing_runs_result = await db.execute(
                    select(func.count(PrintLogEntry.id)).where(PrintLogEntry.archive_id == archive_id)
                )
                _existing_runs = _existing_runs_result.scalar()
                if not _existing_runs:
                    archive.cost = round(total_cost, 2)
                    await db.commit()

    await _notify_unassigned_trays(printer_id, unassigned_trays)
    return results


async def _resolve_3mf_fallback(
    archive,
    db: AsyncSession,
    base_dir,
    *,
    plate_id: int | None = None,
    ams_mapping: list | None = None,
):
    """Try to find a 3MF file from library or a previous archive when the current archive has none.

    This handles fallback archives (FTP download failed) where the 3MF may already exist
    locally from a library upload or a previous successful print of the same file.
    """
    from pathlib import Path

    from backend.app.models.archive import PrintArchive
    from backend.app.models.library import LibraryFile
    from backend.app.services.threemf_identity import (
        candidate_3mf_conflict,
        expected_plate_from_paths,
        stem_matches,
        threemf_search_stem,
    )

    print_data = (archive.extra_data or {}).get("_print_data") or {}
    if not isinstance(print_data, dict):
        print_data = {}
    if plate_id is None:
        plate_id = expected_plate_from_paths(print_data.get("filename"), archive.filename)
    if ams_mapping is None:
        ams_mapping = print_data.get("ams_mapping")
    search_base = threemf_search_stem(
        archive.filename,
        archive.print_name,
        (archive.extra_data or {}).get("original_subtask"),
        print_data.get("subtask_name"),
    )
    if search_base is None:
        return None

    # 1. Try library files matching the name (match base name at file boundary)
    try:
        lib_result = await db.execute(
            LibraryFile.active()
            .where(stem_matches(LibraryFile.filename, search_base))
            .where(_library_3mf_type_filter(LibraryFile))
            .order_by(LibraryFile.created_at.desc())
            .limit(3)
        )
        for lib_file in lib_result.scalars().all():
            lib_path = Path(lib_file.file_path)
            candidate = lib_path if lib_path.is_absolute() else base_dir / lib_file.file_path
            if candidate.suffix.casefold() == ".3mf" and not candidate_3mf_conflict(
                candidate,
                expected_plate=plate_id,
                ams_mapping=ams_mapping,
            ):
                logger.info("[UsageTracker] 3MF fallback: found library file %s for archive %s", candidate, archive.id)
                return candidate
    except Exception as e:
        logger.debug("[UsageTracker] 3MF fallback: library lookup failed: %s", e)

    # 2. Try previous archives with the same filename that have a valid file_path
    try:
        prev_result = await db.execute(
            select(PrintArchive)
            .where(PrintArchive.id != archive.id)
            .where(PrintArchive.printer_id == archive.printer_id)
            .where(PrintArchive.file_path != "")
            .where(PrintArchive.file_path.isnot(None))
            .where(
                stem_matches(PrintArchive.filename, search_base),
            )
            .order_by(PrintArchive.created_at.desc())
            .limit(3)
        )
        for prev_archive in prev_result.scalars().all():
            candidate = base_dir / prev_archive.file_path
            if candidate.suffix.casefold() == ".3mf" and not candidate_3mf_conflict(
                candidate,
                expected_plate=plate_id,
                ams_mapping=ams_mapping,
            ):
                logger.info(
                    "[UsageTracker] 3MF fallback: found previous archive %s file for archive %s",
                    prev_archive.id,
                    archive.id,
                )
                return candidate
    except Exception as e:
        logger.debug("[UsageTracker] 3MF fallback: previous archive lookup failed: %s", e)

    return None


async def _find_3mf_by_filename(
    printer_id: int,
    filename: str,
    db: AsyncSession,
    base_dir,
    *,
    print_name: str | None = None,
    plate_id: int | None = None,
    ams_mapping: list | None = None,
):
    """Find a 3MF file by filename from library or previous archives.

    Used when auto-archive is disabled and there's no archive_id, but we still
    need the 3MF slicer data for filament usage tracking.
    """
    from pathlib import Path

    from backend.app.models.archive import PrintArchive
    from backend.app.models.library import LibraryFile
    from backend.app.services.threemf_identity import (
        candidate_3mf_conflict,
        expected_plate_from_paths,
        stem_matches,
        threemf_search_stem,
    )

    if plate_id is None:
        plate_id = expected_plate_from_paths(filename)
    search_base = threemf_search_stem(filename, print_name)
    if search_base is None:
        return None

    # 1. Try library files matching the name
    try:
        lib_result = await db.execute(
            LibraryFile.active()
            .where(stem_matches(LibraryFile.filename, search_base))
            .where(_library_3mf_type_filter(LibraryFile))
            .order_by(LibraryFile.created_at.desc())
            .limit(3)
        )
        for lib_file in lib_result.scalars().all():
            lib_path = Path(lib_file.file_path)
            candidate = lib_path if lib_path.is_absolute() else base_dir / lib_file.file_path
            if candidate.suffix.casefold() == ".3mf" and not candidate_3mf_conflict(
                candidate,
                expected_plate=plate_id,
                ams_mapping=ams_mapping,
            ):
                logger.info("[UsageTracker] 3MF (no-archive): found library file %s for '%s'", candidate, filename)
                return candidate
    except Exception as e:
        logger.debug("[UsageTracker] 3MF (no-archive): library lookup failed: %s", e)

    # 2. Try previous archives with a valid 3MF file_path
    try:
        prev_result = await db.execute(
            select(PrintArchive)
            .where(PrintArchive.printer_id == printer_id)
            .where(PrintArchive.file_path != "")
            .where(PrintArchive.file_path.isnot(None))
            .where(
                stem_matches(PrintArchive.filename, search_base),
            )
            .order_by(PrintArchive.created_at.desc())
            .limit(3)
        )
        for prev_archive in prev_result.scalars().all():
            candidate = base_dir / prev_archive.file_path
            if candidate.suffix.casefold() == ".3mf" and not candidate_3mf_conflict(
                candidate,
                expected_plate=plate_id,
                ams_mapping=ams_mapping,
            ):
                logger.info(
                    "[UsageTracker] 3MF (no-archive): found previous archive %s file for '%s'",
                    prev_archive.id,
                    filename,
                )
                return candidate
    except Exception as e:
        logger.debug("[UsageTracker] 3MF (no-archive): previous archive lookup failed: %s", e)

    return None


async def _load_dispatch_context(db, printer_id, archive_id, archive, plate_id, mapping_needed: bool):
    """Load queue evidence once when plate or tray mapping may need it."""
    from backend.app.models.print_queue import PrintQueueItem

    if plate_id is None and archive is not None and getattr(archive, "plate_id", None) is not None:
        plate_id = archive.plate_id
    if not archive_id or (plate_id is not None and not mapping_needed):
        return None, plate_id
    result = await db.execute(
        select(PrintQueueItem)
        .where(PrintQueueItem.archive_id == archive_id)
        .where(PrintQueueItem.printer_id == printer_id)
        .where(PrintQueueItem.status.in_(["printing", "completed", "failed"]))
        .order_by(PrintQueueItem.started_at.desc(), PrintQueueItem.id.desc())
    )
    queue_item = result.scalars().first()
    if plate_id is None and queue_item is not None:
        plate_id = getattr(queue_item, "plate_id", None)
    return queue_item, plate_id


async def _resolve_archive_3mf(archive_id, db, base_dir, plate_id, ams_mapping):
    """Load an archive and its own or evidence-compatible donor 3MF."""
    from backend.app.models.archive import PrintArchive

    result = await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))
    archive = result.scalar_one_or_none()
    if archive is None:
        logger.info("[UsageTracker] 3MF: archive %s not found, skipping", archive_id)
        return None, None
    file_path = None
    if archive.file_path:
        candidate = base_dir / archive.file_path
        if candidate.exists():
            file_path = candidate
    if file_path is None:
        file_path = await _resolve_3mf_fallback(
            archive,
            db,
            base_dir,
            plate_id=plate_id,
            ams_mapping=ams_mapping,
        )
    return archive, file_path


def _extract_plate_usage(file_path, plate_id):
    """Read selected-plate totals, with an explicit whole-file fallback."""
    from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf

    filament_usage = extract_filament_usage_from_3mf(file_path, plate_id)
    if filament_usage or plate_id is None:
        return filament_usage, plate_id
    filament_usage = extract_filament_usage_from_3mf(file_path, None)
    if filament_usage:
        logger.warning("[UsageTracker] 3MF: plate %s not present in %s; using whole-file total", plate_id, file_path)
        return filament_usage, None
    return filament_usage, plate_id


def _unassigned_tray(printer_id: int, ams_id: int, tray_id: int, global_tray_id: int, grams: float) -> int:
    logger.warning(
        "[UsageTracker] 3MF: no spool assignment at printer %d AMS%d-T%d — %.1fg not deducted",
        printer_id,
        ams_id,
        tray_id,
        grams,
    )
    return global_tray_id


async def _notify_unassigned_trays(printer_id: int, missing: list[int]) -> None:
    if not missing:
        return
    from backend.app.core.database import async_session
    from backend.app.services.spool_assignment_notifications import (
        notify_missing_spool_assignments_on_print_complete,
    )

    async with async_session() as notification_db:
        await notify_missing_spool_assignments_on_print_complete(printer_id, missing, notification_db, logger)


async def _track_from_3mf(
    printer_id: int,
    archive_id: int | None,
    status: str,
    print_name: str,
    handled_trays: set[tuple[int, int]],
    printer_manager,
    db: AsyncSession,
    ams_mapping: list[int] | None = None,
    tray_now_at_start: int = -1,
    last_progress: float = 0.0,
    last_layer_num: int = 0,
    default_filament_cost: float = 0.0,
    spool_assignments: dict[tuple[int, int], int] | None = None,
    print_started_at: datetime | None = None,
    threemf_path=None,
    plate_id: int | None = None,
    unassigned_trays: list[int] | None = None,
) -> list[dict]:
    """Track usage from 3MF per-filament slicer data (primary path).

    Uses slicer-estimated filament weight for all spools (BL and non-BL).
    For partial prints (failed/aborted), tries per-layer gcode data first,
    then falls back to linear scaling by progress.

    When archive_id is None (auto-archive disabled), a pre-resolved threemf_path
    can be provided to still track filament usage from slicer data.

    When ``plate_id`` is set (queue prints of a single plate from a multi-plate
    3MF), only that plate's filaments contribute. Without it the 3MF parser sums
    every plate, which is correct for direct/library Print flows that always
    target the first or only plate (#1697).

    Slot-to-tray mapping priority:
    1. Stored ams_mapping from print command (reprints/direct prints)
    2. Queue item ams_mapping (stable dispatch evidence)
    3. MQTT mapping field from printer state (mutable during AMS backup)
    4. tray_now from printer state (for single-filament non-queue prints)
    5. Position-based default using sorted available tray IDs (handles external spools)
    6. Default mapping: slot_id - 1 = global_tray_id (last resort)
    """
    from pathlib import Path

    from backend.app.core.config import settings as app_settings
    from backend.app.models.archive import PrintArchive

    file_path: Path | None = threemf_path
    archive: PrintArchive | None = None
    if file_path is None and archive_id:
        archive, file_path = await _resolve_archive_3mf(archive_id, db, app_settings.base_dir, plate_id, ams_mapping)
        if archive is None:
            return []

    if file_path is None:
        logger.info("[UsageTracker] 3MF: no file available for archive %s, skipping", archive_id)
        return []

    queue_item, plate_id = await _load_dispatch_context(db, printer_id, archive_id, archive, plate_id, not ams_mapping)
    filament_usage, plate_id = _extract_plate_usage(file_path, plate_id)
    if not filament_usage:
        logger.info("[UsageTracker] 3MF: no filament usage data in %s", file_path)
        return []

    logger.info("[UsageTracker] 3MF: archive %s, plate_id=%s, filament_usage=%s", archive_id, plate_id, filament_usage)

    # --- Resolve slot-to-tray mapping ---
    mapping_source = None

    # 1. Use stored ams_mapping from the print command (reprints/direct prints)
    slot_to_tray = ams_mapping
    if slot_to_tray:
        mapping_source = "print_cmd"

    # 2. Prefer the queue mapping captured at dispatch. The live MQTT mapping
    # can already name the substitute tray after AMS backup switched spools.
    if not slot_to_tray and archive_id:
        if queue_item and queue_item.ams_mapping:
            try:
                slot_to_tray = json.loads(queue_item.ams_mapping)
                mapping_source = "queue"
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. Try MQTT mapping for direct/external prints without queue evidence.
    if not slot_to_tray:
        state = printer_manager.get_status(printer_id)
        raw_data = getattr(state, "raw_data", None) if state else None
        if raw_data:
            mqtt_mapping = raw_data.get("mapping")
            decoded = _decode_mqtt_mapping(mqtt_mapping)
            if decoded:
                slot_to_tray = decoded
                mapping_source = "mqtt"

    # 4. Color-match 3MF filament slots to AMS trays (for printers without mapping field)
    if not slot_to_tray:
        state = printer_manager.get_status(printer_id)
        raw_data = getattr(state, "raw_data", None) if state else None
        if raw_data:
            matched = _match_slots_by_color(filament_usage, raw_data.get("ams"))
            if matched:
                slot_to_tray = matched
                mapping_source = "color_match"

    logger.info(
        "[UsageTracker] 3MF: slot_to_tray=%s (source: %s)",
        slot_to_tray,
        mapping_source or "none",
    )

    # 5. For single-filament non-queue prints, use tray_now from printer state
    #    Priority: tray_change_log (multi-tray split) > tray_now_at_start > current tray_now
    #              > last_loaded_tray > vt_tray check
    #
    # tray_change_log evidence wins over slot_to_tray when present: if the
    # printer fed from multiple trays mid-print (AMS auto-fallback when one
    # spool runs out, #957), the slicer's mapping captured at print start
    # is stale and needs to be replaced with per-layer split attribution.
    nonzero_slots = [u for u in filament_usage if u.get("used_g", 0) > 0]
    tray_now_override: int | None = None
    tray_changes: list[tuple[int, int]] = []  # [(global_tray_id, layer_num), ...]
    state = printer_manager.get_status(printer_id) if len(nonzero_slots) == 1 else None
    if state is not None:
        tray_changes = getattr(state, "tray_change_log", []) or []

    if len(tray_changes) > 1:
        # Multi-tray usage detected — splitting takes over regardless of slot_to_tray.
        logger.info("[UsageTracker] 3MF: tray change log: %s (will split weight)", tray_changes)
    elif not slot_to_tray and len(nonzero_slots) == 1:
        if 0 <= tray_now_at_start <= 254:
            tray_now_override = tray_now_at_start
            logger.info("[UsageTracker] 3MF: using tray_now_at_start=%d (single-filament fallback)", tray_now_at_start)
        elif state and 0 <= state.tray_now <= 254:
            tray_now_override = state.tray_now
            logger.info("[UsageTracker] 3MF: using current tray_now=%d", state.tray_now)
        elif state and 0 <= state.last_loaded_tray <= 253:
            tray_now_override = state.last_loaded_tray
            logger.info("[UsageTracker] 3MF: using last_loaded_tray=%d (post-retract fallback)", state.last_loaded_tray)
        elif state and state.tray_now == 255:
            # 255 = "no filament" on legacy printers, but valid 2nd external spool on H2-series
            vt_tray = state.raw_data.get("vt_tray") or []
            if any(int(vt.get("id", 0)) == 255 for vt in vt_tray if isinstance(vt, dict)):
                tray_now_override = state.tray_now
                logger.info("[UsageTracker] 3MF: using tray_now=255 (H2-series external spool)")
        if tray_now_override is None:
            logger.info(
                "[UsageTracker] 3MF: no valid tray_now (at_start=%d, current=%s, last_loaded=%s)",
                tray_now_at_start,
                state.tray_now if state else "N/A",
                state.last_loaded_tray if state else "N/A",
            )

    # Scale factor for partial prints (failed/aborted)
    if status == "completed":
        scale = 1.0
    else:
        state = printer_manager.get_status(printer_id)
        progress = state.progress if state else 0
        # Firmware resets progress to 0 on cancel — use last valid progress captured during print
        if progress <= 0 and last_progress > 0:
            progress = last_progress
            logger.info("[UsageTracker] 3MF: using last_progress=%.1f (firmware reset current to 0)", last_progress)
        scale = max(0.0, min(progress / 100.0, 1.0))

    # Per-layer gcode accuracy for partial prints
    layer_grams: dict[int, float] | None = None
    if status != "completed":
        state = printer_manager.get_status(printer_id)
        current_layer = state.layer_num if state else 0
        # Firmware resets layer_num to 0 on cancel — use last valid layer captured during print
        if current_layer <= 0 and last_layer_num > 0:
            current_layer = last_layer_num
            logger.info("[UsageTracker] 3MF: using last_layer_num=%d (firmware reset current to 0)", last_layer_num)
        if current_layer > 0:
            try:
                from backend.app.utils.threemf_tools import (
                    extract_filament_properties_from_3mf,
                    extract_layer_filament_usage_from_3mf,
                    get_cumulative_usage_at_layer,
                    mm_to_grams,
                )

                layer_usage = extract_layer_filament_usage_from_3mf(file_path, plate_id)
                if layer_usage:
                    cumulative_mm = get_cumulative_usage_at_layer(layer_usage, current_layer)
                    filament_props = extract_filament_properties_from_3mf(file_path)
                    layer_grams = {}
                    for filament_id, mm_used in cumulative_mm.items():
                        slot_id = filament_id + 1  # 0-based to 1-based
                        props = filament_props.get(slot_id, {})
                        density = props.get("density", 1.24)
                        diameter = props.get("diameter", 1.75)
                        layer_grams[slot_id] = mm_to_grams(mm_used, diameter, density)
            except Exception:
                pass  # Fall back to linear scaling

    results = []
    unassigned_global_trays: list[int] = []

    for usage in filament_usage:
        slot_id = usage.get("slot_id", 0)
        used_g = usage.get("used_g", 0)
        if used_g <= 0:
            continue

        # --- Mid-print tray switch: split weight across trays ---
        # Split math is shared with the Spoolman writer via
        # ``utils.tray_split.compute_tray_split_grams`` (#1793) — both
        # inventory backends must attribute segments identically or a
        # user running dual-mode sees divergent totals.
        if len(tray_changes) > 1:
            # Compute total weight for this slot (same logic as normal path)
            if layer_grams and slot_id in layer_grams:
                total_weight = layer_grams[slot_id]
            else:
                total_weight = used_g * scale

            if total_weight <= 0:
                continue

            # Extract per-layer gcode for segment splitting
            split_layer_usage = None
            split_props: dict = {}
            try:
                from backend.app.utils.threemf_tools import (
                    extract_filament_properties_from_3mf,
                    extract_layer_filament_usage_from_3mf,
                )

                split_layer_usage = extract_layer_filament_usage_from_3mf(file_path, plate_id)
                filament_props = extract_filament_properties_from_3mf(file_path)
                split_props = filament_props.get(slot_id, {})
            except Exception:
                pass  # Fall back to linear splitting

            from backend.app.utils.tray_split import compute_tray_split_grams

            segments = compute_tray_split_grams(
                tray_changes=tray_changes,
                total_weight=total_weight,
                slot_id=slot_id,
                layer_usage=split_layer_usage,
                density=split_props.get("density", 1.24),
                diameter=split_props.get("diameter", 1.75),
                total_layers=(state.total_layers if state else 0) or 0,
                last_layer_num=last_layer_num,
            )

            for seg_idx, tray_global, segment_grams in segments:
                if segment_grams <= 0:
                    continue

                # Convert global tray ID to (ams_id, tray_id)
                if tray_global >= 254:
                    seg_ams_id = 255
                    seg_tray_id = tray_global - 254
                elif tray_global >= 128:
                    seg_ams_id = tray_global
                    seg_tray_id = 0
                else:
                    seg_ams_id = tray_global // 4
                    seg_tray_id = tray_global % 4

                seg_key = (seg_ams_id, seg_tray_id)
                if seg_key in handled_trays:
                    continue

                seg_start_layer = tray_changes[seg_idx][1]
                is_last = seg_idx + 1 >= len(tray_changes)
                logger.info(
                    "[UsageTracker] 3MF split: segment %d tray=%d (AMS%d-T%d) layers %d-%s -> %.1fg",
                    seg_idx,
                    tray_global,
                    seg_ams_id,
                    seg_tray_id,
                    seg_start_layer,
                    tray_changes[seg_idx + 1][1] if not is_last else "end",
                    segment_grams,
                )

                seg_spool_id = await _resolve_spool_id_for_tray(
                    printer_id=printer_id,
                    ams_id=seg_ams_id,
                    tray_id=seg_tray_id,
                    db=db,
                    spool_assignments_snapshot=spool_assignments,
                    print_started_at=print_started_at,
                )
                if seg_spool_id is None:
                    unassigned_global_trays.append(
                        _unassigned_tray(printer_id, seg_ams_id, seg_tray_id, tray_global, segment_grams)
                    )
                    continue

                spool_result = await db.execute(select(Spool).where(Spool.id == seg_spool_id))
                spool = spool_result.scalar_one_or_none()
                if not spool:
                    continue

                spool.weight_used = (spool.weight_used or 0) + segment_grams
                spool.last_used = datetime.now(timezone.utc)

                percent = round(segment_grams / (spool.label_weight or 1000) * 100)

                cost = None
                cost_per_kg = spool.cost_per_kg if spool.cost_per_kg is not None else default_filament_cost
                if cost_per_kg > 0:
                    cost = round((segment_grams / 1000.0) * cost_per_kg, 2)

                history = SpoolUsageHistory(
                    spool_id=spool.id,
                    printer_id=printer_id,
                    print_name=print_name,
                    weight_used=round(segment_grams, 1),
                    percent_used=percent,
                    status=status,
                    cost=cost,
                    archive_id=archive_id,
                )
                db.add(history)

                handled_trays.add(seg_key)
                results.append(
                    {
                        "spool_id": spool.id,
                        "weight_used": round(segment_grams, 1),
                        "percent_used": percent,
                        "ams_id": seg_ams_id,
                        "tray_id": seg_tray_id,
                        "material": spool.material,
                        "cost": cost,
                        "slot_id": slot_id,
                        "color": _spool_color_to_hex(spool.rgba),
                    }
                )

                logger.info(
                    "[UsageTracker] Spool %d consumed %.1fg (3MF split seg%d) on printer %d AMS%d-T%d (%s)",
                    spool.id,
                    segment_grams,
                    seg_idx,
                    printer_id,
                    seg_ams_id,
                    seg_tray_id,
                    status,
                )

            continue  # Skip normal single-tray processing for this slot

        # Map 3MF slot_id to physical (ams_id, tray_id) using resolved mapping
        if tray_now_override is not None:
            # Single-filament non-queue print: use actual tray from printer state
            global_tray_id = tray_now_override
        else:
            # Explicit mapping (print command, MQTT, queue, color match)
            global_tray_id = None
            if slot_to_tray and slot_id <= len(slot_to_tray):
                mapped = slot_to_tray[slot_id - 1]
                if isinstance(mapped, int) and mapped >= 0:
                    global_tray_id = mapped
            # Position-based default: sort available tray IDs so external spools (254/255)
            # naturally follow standard AMS trays, matching slicer slot numbering.
            #
            # Filter out AMS slots that have no spool loaded (empty `tray_type`) —
            # BambuStudio/OrcaSlicer compact the slot list when assigning filaments
            # and don't expose empty AMS slots to the user, so the slicer's 3MF
            # slot N maps to the Nth *loaded* tray, not the Nth physical position.
            # Without this filter a "3 AMS slots loaded + 1 empty + external"
            # layout routes the slicer's 4th filament to the empty AMS slot
            # instead of the external (#1607), and the external's spool usage
            # never gets recorded. vt_tray entries are already filtered the
            # same way inside `build_ams_tray_lookup` (line 174 checks
            # `tray_type`), so this just mirrors that for the AMS side.
            if global_tray_id is None:
                _state = printer_manager.get_status(printer_id)
                _raw = getattr(_state, "raw_data", None) if _state else None
                if _raw:
                    from backend.app.services.spoolman_tracking import build_ams_tray_lookup

                    _lookup = build_ams_tray_lookup(_raw)
                    available_trays = sorted(gid for gid, info in _lookup.items() if info.get("tray_type"))
                    if slot_id <= len(available_trays):
                        global_tray_id = available_trays[slot_id - 1]
            # Final fallback: slot_id - 1 (legacy, works for pure AMS without external spools)
            if global_tray_id is None:
                global_tray_id = slot_id - 1

        if global_tray_id >= 254:
            # External spool: ams_id=255 (sentinel), tray_id=slot index (0 or 1)
            ams_id = 255
            tray_id = global_tray_id - 254
        elif global_tray_id >= 128:
            ams_id = global_tray_id
            tray_id = 0
        else:
            ams_id = global_tray_id // 4
            tray_id = global_tray_id % 4

        logger.info(
            "[UsageTracker] 3MF: slot_id=%d -> global_tray=%d -> AMS%d-T%d (used_g=%.1f, tray_now_override=%s)",
            slot_id,
            global_tray_id,
            ams_id,
            tray_id,
            used_g,
            tray_now_override,
        )

        key = (ams_id, tray_id)
        if key in handled_trays:
            continue

        spool_id = await _resolve_spool_id_for_tray(
            printer_id=printer_id,
            ams_id=ams_id,
            tray_id=tray_id,
            db=db,
            spool_assignments_snapshot=spool_assignments,
            print_started_at=print_started_at,
        )
        if spool_id is None:
            unassigned_global_trays.append(_unassigned_tray(printer_id, ams_id, tray_id, global_tray_id, used_g))
            continue

        # Load spool
        spool_result = await db.execute(select(Spool).where(Spool.id == spool_id))
        spool = spool_result.scalar_one_or_none()
        if not spool:
            continue

        # Use per-layer grams if available, otherwise linear scale
        if layer_grams and slot_id in layer_grams:
            weight_grams = layer_grams[slot_id]
        else:
            weight_grams = used_g * scale

        if weight_grams <= 0:
            continue

        # Update spool
        spool.weight_used = (spool.weight_used or 0) + weight_grams
        spool.last_used = datetime.now(timezone.utc)

        percent = round(weight_grams / (spool.label_weight or 1000) * 100)

        # Calculate cost for this usage
        cost = None
        cost_per_kg = spool.cost_per_kg if spool.cost_per_kg is not None else default_filament_cost
        if cost_per_kg > 0:
            cost = round((weight_grams / 1000.0) * cost_per_kg, 2)

        # Insert usage history record
        history = SpoolUsageHistory(
            spool_id=spool.id,
            printer_id=printer_id,
            print_name=print_name,
            weight_used=round(weight_grams, 1),
            percent_used=percent,
            status=status,
            cost=cost,
            archive_id=archive_id,
        )
        db.add(history)

        handled_trays.add(key)
        results.append(
            {
                "spool_id": spool.id,
                "weight_used": round(weight_grams, 1),
                "percent_used": percent,
                "ams_id": ams_id,
                "tray_id": tray_id,
                "material": spool.material,
                "cost": cost,
                "slot_id": slot_id,
                "color": _spool_color_to_hex(spool.rgba),
            }
        )

        # Determine mapping source for debug logging
        if tray_now_override is not None:
            map_src = ", tray_now"
        elif mapping_source:
            map_src = f", {mapping_source}_map"
        else:
            map_src = ""
        logger.info(
            "[UsageTracker] Spool %d consumed %.1fg (3MF%s%s) on printer %d AMS%d-T%d (%s)",
            spool.id,
            weight_grams,
            " per-layer" if (layer_grams and slot_id in layer_grams) else (f" scaled {scale:.0%}" if scale < 1 else ""),
            map_src,
            printer_id,
            ams_id,
            tray_id,
            status,
        )

    # --- Adopt the matched inventory spools' colours for the archive (#1494) ---
    # The archive's filament_color was set from the slicer's 3MF at creation
    # time; now that every used slot has been resolved to an inventory spool,
    # the curated spool colour is authoritative. Committed by the caller's
    # `if results: await db.commit()`.
    _apply_archive_colors_from_spools(archive, archive_id, filament_usage, results)

    if unassigned_trays is not None:
        unassigned_trays.extend(unassigned_global_trays)
    return results
