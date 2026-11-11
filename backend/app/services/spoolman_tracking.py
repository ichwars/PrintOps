"""Spoolman per-filament usage tracking for active prints.

Captures AMS tray state and G-code data at print start, then reports
per-filament usage to the correct Spoolman spools at print completion.
Supports accurate partial usage reporting for failed/cancelled prints.
"""

import json
import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select

from backend.app.core.config import settings as app_settings
from backend.app.core.database import async_session
from backend.app.services import spool_swaps
from backend.app.services.spoolman import (
    SpoolmanClientError,
    SpoolmanNotFoundError,
    SpoolmanUnavailableError,
    get_spoolman_client,
    init_spoolman_client,
)
from backend.app.services.spoolman_costs import (
    mark_spoolman_actual_cost,
    positive_finite_number,
    spoolman_usage_cost as _spoolman_usage_cost,
)
from backend.app.services.spoolman_usage_history import (
    SpoolmanUsageCharge,
    claim_spoolman_tracking,
    record_spoolman_usage,
)
from backend.app.services.spoolman_weights import spoolman_net_weight

logger = logging.getLogger(__name__)

# Zero UUID used by Bambu printers for empty/unset tray_uuid
_ZERO_UUID = "00000000000000000000000000000000"
_ZERO_TAG_UID = "0000000000000000"
_MAX_REAL_TRAY_ID = 254

_SpoolmanUsageCost = tuple[float, float | None]


def _is_real_tray_id(value) -> bool:
    """Return whether a value identifies a loaded tray rather than no tray."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_REAL_TRAY_ID


def _is_non_zero_identifier(value: str) -> bool:
    """Return True when identifier is non-empty and not all zeros."""
    if not value:
        return False
    return set(value) != {"0"}


async def _apply_spoolman_costs_to_archive(
    db,
    archive_id: int,
    usage_costs: list[_SpoolmanUsageCost],
    total_filament_grams: float | None = None,
) -> float | None:
    """Set PrintArchive.cost from Spoolman-priced usage reported for this print."""
    if not usage_costs:
        return None

    from backend.app.api.routes.settings import get_setting
    from backend.app.models.archive import PrintArchive

    archive = (await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))).scalar_one_or_none()
    if archive is None:
        return None

    valid_usage = []
    for grams, cost in usage_costs:
        valid_grams = positive_finite_number(grams)
        valid_cost = positive_finite_number(cost)
        if valid_grams is not None and valid_cost is not None:
            valid_usage.append((valid_grams, valid_cost))
    if not valid_usage:
        return None

    total_cost = sum(cost for _, cost in valid_usage)
    tracked_grams = sum(grams for grams, _ in valid_usage)
    run_grams = positive_finite_number(total_filament_grams)
    if run_grams is None:
        run_grams = positive_finite_number(archive.filament_used_grams) or 0.0
    untracked_grams = max(0.0, run_grams - tracked_grams)
    if untracked_grams > 0:
        default_cost_setting = await get_setting(db, "default_filament_cost")
        default_cost_per_kg = (
            25.0 if default_cost_setting in (None, "") else positive_finite_number(default_cost_setting) or 0.0
        )
        if default_cost_per_kg > 0:
            total_cost += (untracked_grams / 1000.0) * default_cost_per_kg

    finite_total = positive_finite_number(total_cost)
    if finite_total is None:
        return None
    total = Decimal(str(finite_total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    run_cost = float(total)
    from backend.app.services.print_log_run import other_runs_of

    existing_runs = await other_runs_of(db, archive)
    if existing_runs:
        logger.debug(
            "[SPOOLMAN] Leaving archive %s first-run cost unchanged; %d run(s) already exist", archive_id, existing_runs
        )
        return run_cost

    source_changed = mark_spoolman_actual_cost(archive)
    cost_changed = run_cost != archive.cost
    if cost_changed:
        logger.info("[SPOOLMAN] Archive %s cost %r -> %s (from Spoolman spool prices)", archive_id, archive.cost, total)
        archive.cost = run_cost
    if cost_changed or source_changed:
        await db.commit()
    return run_cost


def _to_fixed_hex(value: int, width: int) -> str:
    """Mirror frontend toFixedHex(): uppercase, zero-padded, fixed width."""
    safe = max(0, int(value))
    return format(safe, "X").zfill(width)[-width:]


def _hash_serial_to_hex32(serial: str) -> str:
    """Mirror frontend hashSerialToHex32() exactly (32-bit FNV-1a)."""
    input_str = (serial or "").strip().upper()
    hash_value = 0x811C9DC5
    for char in input_str:
        hash_value ^= ord(char)
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return format(hash_value, "X").zfill(8)


def _global_tray_id_to_ams_slot(global_tray_id: int) -> tuple[int, int]:
    """Convert global tray id to (ams_id, tray_id) tuple for fallback tag generation."""
    # External spool slots use IDs 254/255 and map to ams_id=255 tray_id=0/1.
    if global_tray_id >= 254:
        return 255, max(0, global_tray_id - 254)
    # AMS-HT units are addressed by ams_id directly and have a single tray.
    if global_tray_id >= 128:
        return global_tray_id, 0
    # Standard AMS units: four trays each.
    return global_tray_id // 4, global_tray_id % 4


def _get_fallback_spool_tag(printer_serial: str, global_tray_id: int) -> str:
    """Mirror frontend getFallbackSpoolTag(serial, amsId, trayId) exactly."""
    if not printer_serial:
        return ""
    ams_id, tray_id = _global_tray_id_to_ams_slot(global_tray_id)
    return get_fallback_spool_tag_for_slot(printer_serial, ams_id, tray_id)


def get_fallback_spool_tag_for_slot(printer_serial: str, ams_id: int, tray_id: int) -> str:
    """Public helper matching frontend getFallbackSpoolTag(serial, amsId, trayId).

    Used by stale-tag cleanup (#1457) to detect Spoolman spools still holding
    this slot's deterministic fallback tag in extra.tag.
    """
    if not printer_serial:
        return ""
    return f"{_hash_serial_to_hex32(printer_serial)}{_to_fixed_hex(ams_id, 4)}{_to_fixed_hex(tray_id, 4)}"


def _resolve_spool_tag(tray_info: dict, printer_serial: str = "", global_tray_id: int | None = None) -> str:
    """Get the best spool identifier from tray info (prefer tray_uuid over tag_uid).

    Returns empty string if no usable identifier is found.
    """
    tray_uuid = str(tray_info.get("tray_uuid", "") or "")
    tag_uid = str(tray_info.get("tag_uid", "") or "")

    if tray_uuid and tray_uuid != _ZERO_UUID and _is_non_zero_identifier(tray_uuid):
        return tray_uuid
    if tag_uid and tag_uid != _ZERO_TAG_UID and _is_non_zero_identifier(tag_uid):
        return tag_uid
    if global_tray_id is not None:
        return _get_fallback_spool_tag(printer_serial, global_tray_id)
    return ""


async def _get_printer_serial(printer_id: int) -> str:
    """Get printer serial for deterministic fallback tag generation."""
    from backend.app.models.printer import Printer
    from backend.app.services.printer_manager import printer_manager

    printer_info = printer_manager.get_printer(printer_id)
    if printer_info and printer_info.serial_number:
        return printer_info.serial_number

    async with async_session() as db:
        result = await db.execute(select(Printer.serial_number).where(Printer.id == printer_id))
        serial_number = result.scalar_one_or_none()
        return serial_number or ""


def _resolve_global_tray_id(slot_id: int, slot_to_tray: list | None, ams_trays: dict | None = None) -> int:
    """Map a 1-based slot_id to a global_tray_id using optional custom mapping.

    Custom mapping: slot_to_tray[slot_id - 1] is used when >= 0.
    A value of -1 names an unfed slot. External wire entries are resolved
    from ams_mapping2 at MQTT capture, preserving the correct nozzle.
    Position-based default: uses sorted ams_trays keys so external spools (ID 254/255)
    naturally follow standard AMS trays, matching the slicer's slot numbering.
    Final fallback: slot_id - 1 (legacy, works for pure AMS without external spools).
    """
    if slot_to_tray and 0 < slot_id <= len(slot_to_tray):
        mapped_tray = slot_to_tray[slot_id - 1]
        if mapped_tray >= 0:
            return mapped_tray
        return -1
    # Position-based default: sort available tray IDs so external spools (254/255)
    # come after standard AMS trays, matching the slicer's slot assignment order.
    if ams_trays:
        sorted_tray_ids = sorted(ams_trays.keys())
        if slot_id <= len(sorted_tray_ids):
            return sorted_tray_ids[slot_id - 1]
    return slot_id - 1


def _single_slot_tray_from_state(
    state,
    filament_usage: list[dict],
    tray_now_at_start: int | None = None,
) -> tuple[int, int] | None:
    """The tray a single-slot print actually drew from, read off the printer.

    A1, A1 mini, P1S and P2S publish no ``mapping`` field and drop the MQTT
    connection when we subscribe to their request topic, so neither of the
    other two fallbacks can answer for them. What they do report is which tray
    the extruder is fed from, and for a print that uses exactly one filament
    slot that is the same question: the one slot came from the one tray.

    The ladder mirrors ``usage_tracker.on_print_complete`` step 5, which has
    consulted these same fields since it started resolving mappings at
    completion. Spoolman users were the only ones not getting them (#2953).

    Gated on exactly one slot with usage, like the internal writer: on a
    multi-colour print every filament change moves ``tray_now``, so a single
    tray reading says nothing about which slot it belongs to.

    More than one tray-change entry means the print switched trays mid-run
    (AMS backup on runout, #957). ``report_usage`` splits those per segment
    and must not be handed a single-tray mapping instead, so this declines.

    Returns ``(slot_id, global_tray_id)``, or None when the printer offered no
    usable reading and the positional default stands.
    """
    nonzero = [u for u in filament_usage or [] if u.get("used_g", 0) > 0]
    if len(nonzero) != 1:
        return None
    slot_id = nonzero[0].get("slot_id", 0)
    if slot_id <= 0:
        return None

    changes = list(getattr(state, "tray_change_log", None) or [])
    if len(changes) > 1:
        return None
    if len(changes) == 1:
        entry = changes[0]
        if isinstance(entry, (tuple, list)) and entry and _is_real_tray_id(entry[0]):
            # Strongest evidence there is: the printer announced this switch
            # while the job was running, so it describes this print and no
            # other. On the reporter's A1 it read (3, 0) -- tray 3 at layer 0
            # -- while the positional default was charging tray 0.
            return slot_id, entry[0]

    # No mid-print switch recorded. Fall back to the standing tray readings,
    # newest evidence first. ``tray_now`` is 255 both at rest and while
    # nothing is loaded, which is why _MAX_REAL_TRAY_ID excludes it; A1
    # firmware parks there the moment a print ends, leaving last_loaded_tray
    # as the only survivor.
    for candidate in (tray_now_at_start, getattr(state, "tray_now", None)):
        if _is_real_tray_id(candidate):
            return slot_id, candidate
    # On a printer with two external holders (H2D, X2D) tray_now 255 is the
    # right-hand one. Ahead of last_loaded_tray: a print from that holder never
    # updates it, so it still names the tray an earlier print used (#3405).
    from backend.app.services.usage_tracker import has_second_external_holder

    if getattr(state, "tray_now", None) == 255 and has_second_external_holder(getattr(state, "raw_data", None)):
        return slot_id, 255
    # 254 is no survivor of an unload: the same cap as the built-in inventory.
    last_loaded = getattr(state, "last_loaded_tray", None)
    if isinstance(last_loaded, int) and _is_real_tray_id(last_loaded) and last_loaded < 254:
        return slot_id, last_loaded
    return None


def _mapping_names_no_used_tray(slot_to_tray: list | None, filament_usage: list[dict] | None) -> bool:
    """The built-in inventory's rule for a mapping that is no evidence (#3405)."""
    from backend.app.services.usage_tracker import mapping_names_no_used_tray

    return mapping_names_no_used_tray(slot_to_tray, filament_usage)


def _resolve_slot_to_tray_fallback(
    printer_id: int,
    filament_usage: list[dict],
    tray_now_at_start: int | None = None,
    tray_state_only: bool = False,
) -> tuple[list[int] | None, str]:
    """Resolve an absent start mapping from completion-time evidence."""
    from backend.app.services.printer_manager import printer_manager
    from backend.app.services.usage_tracker import _decode_mqtt_mapping, _match_slots_by_color

    state = printer_manager.get_status(printer_id)
    raw_data = getattr(state, "raw_data", None) if state else None
    if raw_data and not tray_state_only:
        decoded = _decode_mqtt_mapping(raw_data.get("mapping"))
        if decoded:
            return decoded, "mqtt"
        matched = _match_slots_by_color(filament_usage, raw_data.get("ams"))
        if matched:
            return matched, "color_match"

    single = _single_slot_tray_from_state(state, filament_usage, tray_now_at_start)
    if single is None:
        return None, "none"
    slot_id, global_tray_id = single
    mapping = [-1] * slot_id
    mapping[slot_id - 1] = global_tray_id
    return mapping, "tray_state"


def build_ams_tray_lookup(raw_data: dict) -> dict[int, dict]:
    """Build lookup of global_tray_id -> tray info from printer state.

    Returns: {0: {"tray_uuid": "...", "tag_uid": "...", "tray_type": "..."}, ...}
    """
    lookup = {}
    ams_data = raw_data.get("ams", [])
    for ams_unit in ams_data:
        ams_id = int(ams_unit.get("id", 0))
        for tray in ams_unit.get("tray", []):
            tray_id = int(tray.get("id", 0))
            # AMS-HT units have IDs starting at 128 with a single tray
            global_tray_id = ams_id if ams_id >= 128 else ams_id * 4 + tray_id
            lookup[global_tray_id] = {
                "tray_uuid": tray.get("tray_uuid", ""),
                "tag_uid": tray.get("tag_uid", ""),
                "tray_type": tray.get("tray_type", ""),
            }

    # External spool(s) (vt_tray is a list, global_tray_id from each entry's "id")
    for vt in raw_data.get("vt_tray") or []:
        if vt.get("tray_type"):
            tray_id = int(vt.get("id", 254))
            lookup[tray_id] = {
                "tray_uuid": vt.get("tray_uuid", ""),
                "tag_uid": vt.get("tag_uid", ""),
                "tray_type": vt.get("tray_type", ""),
            }

    return lookup


def _snapshot_tray_remain(raw_data: dict) -> dict[str, dict]:
    """Capture per-slot ``remain%`` + ``tray_uuid`` at print start so the
    completion path can compute a remain-delta when 3MF data doesn't cover
    the slot (or there's no 3MF at all — #1820).

    Returns ``{"<ams_id>-<tray_id>": {"remain": int, "tray_uuid": str}}``.
    Only slots whose ``remain`` is a valid 0..100 int are included; invalid
    values mean the AMS hasn't read the spool yet and a delta would be
    meaningless. Mirrors the gate in
    ``usage_tracker.on_print_start:309``.
    """
    snapshot: dict[str, dict] = {}
    ams_raw = raw_data.get("ams", [])
    ams_data = ams_raw.get("ams", []) if isinstance(ams_raw, dict) else ams_raw if isinstance(ams_raw, list) else []
    for ams_unit in ams_data:
        if not isinstance(ams_unit, dict):
            continue
        ams_id = int(ams_unit.get("id", 0))
        for tray in ams_unit.get("tray", []):
            if not isinstance(tray, dict):
                continue
            tray_id = int(tray.get("id", 0))
            remain = tray.get("remain", -1)
            if isinstance(remain, int) and 0 <= remain <= 100:
                snapshot[f"{ams_id}-{tray_id}"] = {
                    "remain": remain,
                    "tray_uuid": tray.get("tray_uuid", "") or "",
                }
    vt_tray_raw = raw_data.get("vt_tray") or []
    if isinstance(vt_tray_raw, dict):
        vt_tray_raw = [vt_tray_raw]
    for vt in vt_tray_raw:
        if not isinstance(vt, dict):
            continue
        vt_id = int(vt.get("id", 254))
        # 254 → (255, 0), 255 → (255, 1) — matches usage_tracker's encoding.
        vt_tray_id = vt_id - 254
        remain = vt.get("remain", -1)
        if isinstance(remain, int) and 0 <= remain <= 100:
            snapshot[f"255-{vt_tray_id}"] = {
                "remain": remain,
                "tray_uuid": vt.get("tray_uuid", "") or "",
            }
    return snapshot


async def store_print_data(
    printer_id: int,
    archive_id: int,
    file_path: str,
    db,
    printer_manager,
    ams_mapping: list[int] | None = None,
    plate_id: int | None = None,
    spoolman_owns_usage: bool | None = None,
):
    """Store Spoolman tracking data at print start (persisted to database).

    Per-print tracking is the primary weight-update path for Spoolman, mirroring
    how the internal Filament Inventory works. The legacy AMS-remain%-based sync
    is no longer used as a weight writer (#1119), so this runs whenever Spoolman
    is enabled regardless of the deprecated `spoolman_disable_weight_sync` flag.

    ``plate_id``, when set, scopes the 3MF filament extract to a single plate so
    queue / direct-Print dispatch of plate N of a multi-plate file doesn't
    attribute every plate's filament to the printed spool (#1697). When unset,
    the queue item's plate_id (if any) is used; otherwise the whole-file sum is
    extracted, which is correct for direct prints that target the first/only
    plate of a single-plate file.
    """
    from backend.app.api.routes.settings import get_setting
    from backend.app.models.active_print_spoolman import ActivePrintSpoolman
    from backend.app.models.print_queue import PrintQueueItem
    from backend.app.utils.threemf_tools import (
        extract_filament_properties_from_3mf,
        extract_filament_usage_from_3mf,
        extract_layer_filament_usage_from_3mf,
    )

    # Check if Spoolman is enabled
    if spoolman_owns_usage is None:
        spoolman_enabled = await get_setting(db, "spoolman_enabled")
        spoolman_owns_usage = bool(spoolman_enabled) and spoolman_enabled.lower() == "true"
    if not spoolman_owns_usage:
        return

    # Get current AMS tray state up front — needed both for the 3MF path's
    # ams_trays field and for the remain%-delta snapshot (#1820 fallback for
    # no-3MF "Untitled" prints, mirroring usage_tracker.on_print_start).
    state = printer_manager.get_status(printer_id)
    ams_trays: dict[int, dict] = {}
    tray_remain_start: dict[str, dict] = {}
    if state and state.raw_data:
        ams_trays = build_ams_tray_lookup(state.raw_data)
        tray_remain_start = _snapshot_tray_remain(state.raw_data)

    # Try to read per-slot filament estimates from the 3MF. Two paths can
    # leave ``filament_usage`` empty: (1) fallback archive (no .gcode.3mf
    # was downloadable from the printer — "Untitled" prints, see #1820),
    # (2) 3MF present but slice_info missing per-filament estimates.
    # Both fall through to the remain%-delta path at completion.
    filament_usage: list | None = None
    layer_usage_json: dict | None = None
    filament_properties: dict | None = None
    full_path = (
        app_settings.base_dir / file_path
    )  # SEC-PATH-OK: file_path is archive.file_path / library_file.file_path — DB-stored, internally generated
    threemf_available = bool(file_path) and full_path.exists()
    queue_item = None
    if threemf_available:
        # Resolve the queue item once — used both for the plate-scoped 3MF parsing
        # fallback (#1697: multi-plate file dispatched for one plate must only count
        # that plate's filament) and for the ams_mapping fallback below.
        queue_result = await db.execute(
            select(PrintQueueItem)
            .where(PrintQueueItem.archive_id == archive_id)
            .where(PrintQueueItem.printer_id == printer_id)
            .where(PrintQueueItem.status == "printing")
            .order_by(PrintQueueItem.id.desc())
        )
        queue_item = queue_result.scalars().first()
        # Caller-supplied plate_id wins (direct-Print path); fall back to the queue
        # item's plate_id (queue dispatch path).
        effective_plate_id = (
            plate_id if plate_id is not None else (queue_item.plate_id if queue_item is not None else None)
        )
        filament_usage = extract_filament_usage_from_3mf(full_path, effective_plate_id) or None

        layer_usage = extract_layer_filament_usage_from_3mf(full_path, effective_plate_id)
        if layer_usage:
            # Convert int keys to string for JSON serialization
            layer_usage_json = {str(k): v for k, v in layer_usage.items()}
            logger.debug("[SPOOLMAN] Parsed %s layers from G-code", len(layer_usage))

        filament_properties = extract_filament_properties_from_3mf(full_path)
    else:
        # No 3MF on disk — common for "Untitled" prints whose .gcode.3mf
        # was never on the printer's FTP. Logged at debug since the
        # fallback path below picks up the slack when remain% is available.
        logger.debug("[SPOOLMAN] 3MF file not available: %s", full_path)

    # If neither path has anything useful, there's nothing to track.
    if not filament_usage and not tray_remain_start:
        if threemf_available:
            logger.debug("[SPOOLMAN] No filament usage data in 3MF for archive %s", archive_id)
        return

    # Prefer the explicit mapping captured from the print command, then fall back
    # to any queue mapping stored for scheduled/reprint jobs.
    slot_to_tray = ams_mapping if ams_mapping is not None else None
    if not slot_to_tray and queue_item and queue_item.ams_mapping:
        try:
            slot_to_tray = json.loads(queue_item.ams_mapping)
        except json.JSONDecodeError:
            pass  # Ignore malformed AMS mapping; fall back to default slot assignment

    from backend.app.core.printer_lifecycle import lock_existing_printer

    if not await lock_existing_printer(db, printer_id):
        return

    # Delete any existing row for this printer/archive (shouldn't exist, but just in case)
    await db.execute(
        delete(ActivePrintSpoolman)
        .where(ActivePrintSpoolman.printer_id == printer_id)
        .where(ActivePrintSpoolman.archive_id == archive_id)
    )

    # Insert new tracking data. ``filament_usage`` may be None for the
    # no-3MF case; report_usage falls back to ``tray_remain_start``.
    tracking = ActivePrintSpoolman(
        printer_id=printer_id,
        archive_id=archive_id,
        filament_usage=filament_usage,
        ams_trays=ams_trays,
        slot_to_tray=slot_to_tray,
        layer_usage=layer_usage_json,
        filament_properties=filament_properties,
        tray_remain_start=tray_remain_start or None,
        tray_now_at_start=getattr(state, "tray_now", None) if state else None,
    )
    db.add(tracking)
    await db.commit()

    logger.info(
        "[SPOOLMAN] Stored tracking data for print: printer=%s, archive=%s (3mf=%s, remain_snapshot=%d slot(s))",
        printer_id,
        archive_id,
        "yes" if filament_usage else "no",
        len(tray_remain_start),
    )
    logger.debug("[SPOOLMAN] Filament usage: %s", filament_usage)
    logger.debug("[SPOOLMAN] AMS trays: %s", list(ams_trays.keys()))
    if slot_to_tray:
        logger.debug("[SPOOLMAN] Custom slot mapping: %s", slot_to_tray)
    if layer_usage_json:
        logger.debug("[SPOOLMAN] Layer usage data available for partial tracking")


async def cleanup_tracking(
    printer_id: int,
    archive_id: int,
    db,
    last_layer_num: int | None = None,
    last_progress: int | None = None,
    spool_change_log: list[dict] | None = None,
    status: str = "failed",
):
    """Report partial usage and clean up Spoolman tracking data for failed/aborted prints."""
    tracking = await claim_spoolman_tracking(db, printer_id, archive_id)
    if not tracking:
        logger.debug("[SPOOLMAN] No tracking data to clean up for printer=%s, archive=%s", printer_id, archive_id)
        return

    usage_costs: list[SpoolmanUsageCharge] = []
    # Try to report partial usage before cleanup
    try:
        await _report_partial_usage(
            printer_id,
            tracking,
            last_layer_num=last_layer_num,
            last_progress=last_progress,
            spool_change_log=spool_change_log,
            usage_costs_out=usage_costs,
        )
    except Exception as e:
        logger.warning("[SPOOLMAN] Partial usage report failed: %s", e)

    await record_spoolman_usage(db, printer_id, archive_id, status, usage_costs)

    from backend.app.services.print_cost_estimate import default_cost_per_kg

    if not usage_costs:
        return None
    default_rate = await default_cost_per_kg(db) / 1000.0
    return round(
        sum(charge.cost if charge.cost is not None else charge.grams * default_rate for charge in usage_costs), 2
    )


async def _get_spoolman_client_with_fallback():
    """Get Spoolman client, initializing from settings if needed.

    Returns (client, is_healthy) tuple. Client may be None.
    """
    client = await get_spoolman_client()
    if not client:
        async with async_session() as db:
            from backend.app.api.routes.settings import get_setting

            spoolman_url = await get_setting(db, "spoolman_url")
            if spoolman_url:
                try:
                    client = await init_spoolman_client(spoolman_url)
                except ValueError as exc:
                    logger.warning("Spoolman URL %r rejected by SSRF guard: %s", spoolman_url, exc)
                    return None

    if not client:
        return None
    if not await client.health_check():
        logger.warning("Spoolman health check failed; skipping usage reporting")
        return None

    return client


async def _resolve_spool_id_via_slot_assignment(printer_id: int, ams_id: int, tray_id: int) -> int | None:
    """Look up the Spoolman spool ID locally bound to (printer, ams, tray).

    Fallback path for #1459: when a tag-less spool was assigned via the
    PrintOps UI, the user's deterministic fallback tag is intentionally NOT
    written to Spoolman's extra.tag (kept clean per #1457), so
    find_spool_by_tag misses. The local spoolman_slot_assignments table is
    the authoritative binding for those spools.
    """
    from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment

    async with async_session() as db:
        result = await db.execute(
            select(SpoolmanSlotAssignment.spoolman_spool_id).where(
                SpoolmanSlotAssignment.printer_id == printer_id,
                SpoolmanSlotAssignment.ams_id == ams_id,
                SpoolmanSlotAssignment.tray_id == tray_id,
            )
        )
        return result.scalar_one_or_none()


async def _report_spool_usage_for_slots(
    client,
    filament_usage_items: list[tuple[int, float]],
    ams_trays: dict[int, dict],
    slot_to_tray: list | None,
    method_label: str,
    printer_serial: str = "",
    printer_id: int | None = None,
    slot_colors_out: dict[int, str] | None = None,
    usage_costs_out: list[SpoolmanUsageCharge] | None = None,
    swaps: spool_swaps.Splitter | None = None,
) -> int:
    """Report usage to Spoolman for a list of (slot_id, grams) pairs.

    Resolution order per slot: (1) Spoolman extra.tag match against the
    tray's RFID or deterministic fallback tag, (2) #1459 fallback —
    local spoolman_slot_assignments table keyed by (printer_id, ams_id,
    tray_id). Without (2), tag-less spools assigned via the PrintOps UI
    never get their weight decremented because their extra.tag is empty
    on the Spoolman side.

    When ``slot_colors_out`` is provided it is populated with
    ``{slot_id: color_hex}`` for every resolved spool — used by
    :func:`report_usage` to stamp the archive's filament colour from the
    Spoolman spool rather than the slicer's 3MF value (#1494).

    Returns number of spools successfully updated.
    """
    spools_updated = 0
    for slot_id, grams_used in filament_usage_items:
        if grams_used <= 0:
            continue

        global_tray_id = _resolve_global_tray_id(slot_id, slot_to_tray, ams_trays)
        tray_info = ams_trays.get(global_tray_id)
        if not tray_info:
            logger.debug("[SPOOLMAN] Slot %s: no tray at global_tray_id %s", slot_id, global_tray_id)
            continue

        is_external = global_tray_id >= 254
        tray_type = tray_info.get("tray_type", "")
        logger.debug(
            "[SPOOLMAN] Slot %s resolved to global_tray_id %s (tray_type=%s, external=%s)",
            slot_id,
            global_tray_id,
            tray_type or "unknown",
            is_external,
        )

        spool_id_to_use: int | None = None
        resolution_path = ""
        # color_hex of the resolved spool's filament, for the #1494 archive
        # colour rewrite. The tag path already has the full spool object;
        # the slot-assignment path only yields an id and is fetched below.
        spool_color_hex: str | None = None
        resolved_spool: dict | None = None

        spool_tag = _resolve_spool_tag(tray_info, printer_serial, global_tray_id)
        if spool_tag:
            spool = await client.find_spool_by_tag(spool_tag)
            if spool:
                spool_id_to_use = spool["id"]
                resolution_path = "tag"
                resolved_spool = spool
                spool_color_hex = (spool.get("filament") or {}).get("color_hex")

        if spool_id_to_use is None and printer_id is not None:
            ams_id, tray_id = _global_tray_id_to_ams_slot(global_tray_id)
            spool_id_to_use = await _resolve_spool_id_via_slot_assignment(printer_id, ams_id, tray_id)
            if spool_id_to_use is not None:
                resolution_path = "slot-assignment"

        shares = swaps.shares(*_global_tray_id_to_ams_slot(global_tray_id), slot_id, grams_used) if swaps else None
        if shares and shares[0][0] != spool_id_to_use:
            spool_id_to_use = shares[0][0]
            resolved_spool = spool_color_hex = None
            resolution_path = "swap log"

        if spool_id_to_use is None:
            logger.debug(
                "[SPOOLMAN] Slot %s: no spool resolved (tag=%s, no slot-assignment)",
                slot_id,
                spool_tag[:16] if spool_tag else "none",
            )
            continue

        # Record the spool's filament colour for the archive rewrite (#1494).
        # The slot-assignment path resolved only an id, so fetch the spool.
        # Strictly best-effort: a colour-fetch failure must never abort the
        # weight reporting for the remaining slots, so the catch is broad.
        if (slot_colors_out is not None or usage_costs_out is not None) and resolved_spool is None:
            try:
                resolved_spool = await client.get_spool(spool_id_to_use)
                spool_color_hex = (resolved_spool.get("filament") or {}).get("color_hex")
            except Exception as exc:  # noqa: BLE001 — colour/cost is non-critical
                logger.debug("[SPOOLMAN] Slot %s: could not fetch full spool metadata: %s", slot_id, exc)
        if slot_colors_out is not None:
            if spool_color_hex:
                slot_colors_out[slot_id] = spool_color_hex

        spools_updated += await _charge_shares(
            client,
            shares or [(spool_id_to_use, grams_used)],
            spool_id_to_use,
            resolved_spool,
            usage_costs_out,
            f"{method_label} ({resolution_path})",
        )

    return spools_updated


async def _report_spool_usage_split_by_tray_changes(
    client,
    filament_usage: list[dict],
    tray_changes: list[tuple[int, int]],
    ams_trays: dict[int, dict],
    layer_usage: dict[int, dict[int, float]] | None,
    filament_properties: dict | None,
    total_layers: int,
    last_layer_num: int,
    method_label: str,
    printer_serial: str,
    printer_id: int,
    slot_colors_out: dict[int, str] | None = None,
    usage_costs_out: list[SpoolmanUsageCharge] | None = None,
    swaps: spool_swaps.Splitter | None = None,
) -> tuple[int, set[int]]:
    """Split each slot's grams across ``tray_changes`` and charge per-segment.

    Mirrors ``usage_tracker`` Path 1's tray-switch branch so Spoolman and
    the internal Spool inventory attribute mid-print AMS-backup switches
    identically (#1793 — reporter's origin spool was over-charged the
    whole print because this path didn't exist). ``compute_tray_split_grams``
    holds the shared segment-math; this function wraps the per-segment
    spool resolution + ``use_spool`` sink for the Spoolman side.

    Returns ``(spools_updated, handled_global_tray_ids)`` — the caller
    passes ``handled_global_tray_ids`` into the remain-delta fallback so
    a tray attributed here is not double-charged there.
    """
    from backend.app.utils.tray_split import compute_tray_split_grams

    spools_updated = 0
    handled_global_tray_ids: set[int] = set()

    for usage in filament_usage:
        slot_id = usage.get("slot_id", 0)
        total_weight = usage.get("used_g", 0)
        if total_weight <= 0 or slot_id <= 0:
            continue

        props = (filament_properties or {}).get(str(slot_id)) or (filament_properties or {}).get(slot_id) or {}
        segments = compute_tray_split_grams(
            tray_changes=tray_changes,
            total_weight=float(total_weight),
            slot_id=slot_id,
            layer_usage=layer_usage,
            density=float(props.get("density", 1.24)),
            diameter=float(props.get("diameter", 1.75)),
            total_layers=total_layers,
            last_layer_num=last_layer_num,
        )

        for seg_idx, tray_global, segment_grams in segments:
            if segment_grams <= 0:
                continue

            # Mark this tray as handled BEFORE the resolution attempt so
            # remain-delta doesn't double-charge it, even if we fail to
            # find a spool below. Matches usage_tracker behaviour: the
            # tray was physically fed from during this print, whether or
            # not Spoolman happens to have a matching row.
            handled_global_tray_ids.add(tray_global)

            tray_info = ams_trays.get(tray_global) or {}
            spool_id_to_use: int | None = None
            resolution_path = ""
            spool_color_hex: str | None = None
            resolved_spool: dict | None = None

            spool_tag = _resolve_spool_tag(tray_info, printer_serial, tray_global) if tray_info else ""
            if spool_tag:
                spool = await client.find_spool_by_tag(spool_tag)
                if spool:
                    spool_id_to_use = spool["id"]
                    resolution_path = "tag"
                    resolved_spool = spool
                    spool_color_hex = (spool.get("filament") or {}).get("color_hex")

            if spool_id_to_use is None:
                seg_ams_id, seg_tray_id = _global_tray_id_to_ams_slot(tray_global)
                spool_id_to_use = await _resolve_spool_id_via_slot_assignment(printer_id, seg_ams_id, seg_tray_id)
                if spool_id_to_use is not None:
                    resolution_path = "slot-assignment"

            shares = None
            if swaps:
                shares = swaps.shares(
                    *_global_tray_id_to_ams_slot(tray_global),
                    slot_id,
                    segment_grams,
                    tray_changes[seg_idx][1],
                    None if seg_idx + 1 >= len(tray_changes) else tray_changes[seg_idx + 1][1],
                )
                if shares and shares[0][0] != spool_id_to_use:
                    spool_id_to_use = shares[0][0]
                    resolved_spool = spool_color_hex = None
                    resolution_path = "swap log"

            if spool_id_to_use is None:
                logger.info(
                    "[SPOOLMAN] Split slot %s seg %s tray=%d: no spool resolved — %.2fg lost from split accounting",
                    slot_id,
                    seg_idx,
                    tray_global,
                    segment_grams,
                )
                continue

            # Colour rewrite (#1494) — first segment for a slot wins. The
            # UI displays a single colour per slot, so later segments on the
            # same slot don't overwrite (a backup swap can be a different
            # colour but the archive card stays consistent with the origin).
            if (usage_costs_out is not None or (slot_colors_out is not None and slot_id not in slot_colors_out)) and (
                resolved_spool is None
            ):
                try:
                    resolved_spool = await client.get_spool(spool_id_to_use)
                    spool_color_hex = (resolved_spool.get("filament") or {}).get("color_hex")
                except Exception as exc:  # noqa: BLE001 — colour/cost is non-critical
                    logger.debug("[SPOOLMAN] Split slot %s: could not fetch full spool metadata: %s", slot_id, exc)
            if slot_colors_out is not None and slot_id not in slot_colors_out:
                if spool_color_hex:
                    slot_colors_out[slot_id] = spool_color_hex

            spools_updated += await _charge_shares(
                client,
                shares or [(spool_id_to_use, segment_grams)],
                spool_id_to_use,
                resolved_spool,
                usage_costs_out,
                f"{method_label} ({resolution_path})",
            )

    return spools_updated, handled_global_tray_ids


async def _report_partial_usage(
    printer_id: int,
    tracking,
    last_layer_num: int | None = None,
    last_progress: int | None = None,
    spool_change_log: list[dict] | None = None,
    usage_costs_out: list[SpoolmanUsageCharge] | None = None,
):
    """Report partial filament usage based on actual G-code layer data.

    Uses per-layer cumulative extrusion from G-code parsing for accurate
    multi-material tracking. Falls back to linear interpolation if G-code
    data is unavailable.
    """
    from backend.app.services.printer_manager import printer_manager
    from backend.app.utils.threemf_tools import get_cumulative_usage_at_layer, mm_to_grams, slicer_grams_at_layer

    async with async_session() as db:
        from backend.app.api.routes.settings import get_setting

        # Check if partial usage reporting is enabled (default: true)
        report_partial = await get_setting(db, "spoolman_report_partial_usage")
        if report_partial and report_partial.lower() == "false":
            logger.debug("[SPOOLMAN] Partial usage reporting disabled by setting")
            return

    # Get current printer state for layer progress.
    # On failed/aborted prints the firmware may already reset to IDLE with layer=0,
    # so we fall back to completion-time hints captured from MQTT.
    state = printer_manager.get_status(printer_id)
    current_layer = last_layer_num if last_layer_num and last_layer_num > 0 else (state.layer_num if state else None)
    total_layers = state.total_layers if state else None

    if (not current_layer or current_layer <= 0) and last_layer_num and last_layer_num > 0:
        current_layer = last_layer_num
        logger.debug("[SPOOLMAN] Using captured last_layer_num=%s for partial usage", current_layer)

    progress_ratio_from_event = None
    if last_progress is not None:
        try:
            progress_ratio_from_event = min(max(float(last_progress), 0.0), 100.0) / 100.0
        except (TypeError, ValueError):
            progress_ratio_from_event = None

    if (not current_layer or current_layer <= 0) and progress_ratio_from_event and total_layers and total_layers > 0:
        current_layer = max(1, int(round(total_layers * progress_ratio_from_event)))
        logger.debug(
            "[SPOOLMAN] Estimated layer from last_progress=%s%% and total_layers=%s -> %s",
            last_progress,
            total_layers,
            current_layer,
        )

    if not current_layer or current_layer <= 0:
        logger.debug(
            "[SPOOLMAN] No progress to report (layer 0/unknown, last_layer_num=%s, last_progress=%s)",
            last_layer_num,
            last_progress,
        )
        return

    logger.info("[SPOOLMAN] Reporting partial usage at layer %s/%s", current_layer, total_layers or "?")

    # Get tracking data
    layer_usage = tracking.layer_usage
    filament_properties = tracking.filament_properties or {}
    filament_usage = tracking.filament_usage or []
    ams_trays = {int(k): v for k, v in (tracking.ams_trays or {}).items()}
    slot_to_tray = tracking.slot_to_tray
    tray_remain_start = tracking.tray_remain_start or {}
    unmapped = _mapping_names_no_used_tray(slot_to_tray, filament_usage)
    if unmapped:
        slot_to_tray = None
    elif slot_to_tray and all(tray == -1 for tray in slot_to_tray):
        return
    if filament_usage and not slot_to_tray:
        slot_to_tray, mapping_source = _resolve_slot_to_tray_fallback(
            printer_id,
            filament_usage,
            getattr(tracking, "tray_now_at_start", None),
            tray_state_only=unmapped,
        )
        logger.info(
            "[SPOOLMAN] Partial usage: slot_to_tray=%s (source: %s)",
            slot_to_tray,
            mapping_source,
        )
    if unmapped and not slot_to_tray:
        return
    printer_serial = await _get_printer_serial(printer_id)

    client = await _get_spoolman_client_with_fallback()
    if not client:
        logger.warning("[SPOOLMAN] Not reachable for partial usage reporting")
        return

    # No-3MF aborted print (#1820 mirror of the completion path): nothing in
    # filament_usage or layer_usage to base partial estimates on, but the
    # remain%-delta snapshot we captured at start still describes consumption
    # up to the abort moment. Write it the same way report_usage's fallback
    # does, then return — there's no 3MF-derived partial to layer on top.
    # ``state`` was already fetched at the top of the function for current_layer.
    if not filament_usage and not layer_usage and tray_remain_start:
        current_lookup = _snapshot_tray_remain(state.raw_data) if state and state.raw_data else {}
        await _report_remain_delta_for_slots(
            client,
            printer_id=printer_id,
            tray_remain_start=tray_remain_start,
            current_lookup=current_lookup,
            handled_global_tray_ids=set(),
            archive_id=getattr(tracking, "archive_id", -1),
            usage_costs_out=usage_costs_out,
            print_used_keys=_print_used_tray_keys(
                slot_to_tray,
                getattr(tracking, "tray_now_at_start", None),
                state,
            ),
        )
        return

    tray_changes = list(getattr(state, "tray_change_log", None) or []) if state else []

    swaps = _swap_splitter(printer_id, state, layer_usage, current_layer, completed=False)
    if spool_change_log is not None:
        swaps.log = list(spool_change_log)

    async def charge(usage_items, method_label):
        usage_items = [(slot, grams) for slot, grams in usage_items if not _slot_is_unfed(slot, slot_to_tray)]
        used = [(slot, grams) for slot, grams in usage_items if grams > 0]
        if len(used) == 1 and len(tray_changes) > 1:
            split_layers = max([current_layer] + [layer for _, layer in tray_changes])
            updated, _ = await _report_spool_usage_split_by_tray_changes(
                client,
                [{"slot_id": used[0][0], "used_g": used[0][1]}],
                tray_changes,
                ams_trays,
                None,
                filament_properties,
                split_layers,
                split_layers,
                f"{method_label} split",
                printer_serial,
                printer_id=printer_id,
                usage_costs_out=usage_costs_out,
                swaps=swaps,
            )
            return updated
        return await _report_spool_usage_for_slots(
            client,
            usage_items,
            ams_trays,
            slot_to_tray,
            method_label,
            printer_serial,
            printer_id=printer_id,
            usage_costs_out=usage_costs_out,
            swaps=swaps,
        )

    # Try to use accurate G-code parsed data
    if layer_usage:
        layer_usage_int = {
            int(layer): {int(fid): mm for fid, mm in filaments.items()} for layer, filaments in layer_usage.items()
        }
        usage_mm = get_cumulative_usage_at_layer(layer_usage_int, current_layer)

        if usage_mm:
            logger.info("[SPOOLMAN] Using G-code parsed data for layer %s", current_layer)

            # Build (slot_id, grams) list using Spoolman densities with 3MF fallback
            scaled = slicer_grams_at_layer(layer_usage_int, current_layer, filament_usage)
            weighed = {u.get("slot_id") for u in filament_usage if (u.get("used_g") or 0) > 0}
            usage_items = []
            for filament_id, mm_used in usage_mm.items():
                slot_id = filament_id + 1  # filament_id is 0-based, slot_id is 1-based
                if filament_usage and slot_id not in weighed:
                    continue
                if slot_id in scaled:
                    usage_items.append((slot_id, round(scaled[slot_id], 2)))
                    continue

                # Get density from Spoolman (most accurate), fall back to 3MF, then PLA default
                global_tray_id = _resolve_global_tray_id(slot_id, slot_to_tray, ams_trays)
                tray_info = ams_trays.get(global_tray_id)
                density = None
                diameter = 1.75

                if tray_info:
                    spool_tag = _resolve_spool_tag(tray_info, printer_serial, global_tray_id)
                    if spool_tag:
                        spool = await client.find_spool_by_tag(spool_tag)
                        if spool:
                            filament_data = spool.get("filament", {})
                            density = filament_data.get("density")
                            diameter = filament_data.get("diameter", 1.75)

                if not density:
                    props = filament_properties.get(str(slot_id), filament_properties.get(slot_id, {}))
                    density = props.get("density", 1.24)
                    logger.debug("[SPOOLMAN] Using fallback density %s for slot %s", density, slot_id)

                grams_used = round(mm_to_grams(mm_used, diameter, density), 2)
                usage_items.append((slot_id, grams_used))

            spools_updated = await charge(usage_items, "Partial (G-code)")
            if spools_updated > 0:
                logger.info("[SPOOLMAN] Reported partial usage to %s spool(s) using G-code data", spools_updated)
            return

    # Fallback: linear interpolation (if no G-code data available)
    progress_ratio = None
    if total_layers and total_layers > 0:
        progress_ratio = min(current_layer / total_layers, 1.0)
    elif progress_ratio_from_event is not None:
        progress_ratio = progress_ratio_from_event

    if progress_ratio is None:
        logger.debug(
            "[SPOOLMAN] Cannot use linear fallback: total_layers=%s, last_progress=%s",
            total_layers,
            last_progress,
        )
        return

    logger.info("[SPOOLMAN] Falling back to linear interpolation (%s)", progress_ratio)

    usage_items = []
    for usage in filament_usage:
        slot_id = usage.get("slot_id", 0)
        total_used_g = usage.get("used_g", 0)
        if total_used_g > 0:
            partial_used_g = round(total_used_g * progress_ratio, 2)
            usage_items.append((slot_id, partial_used_g))

    spools_updated = await charge(usage_items, "Partial (linear)")
    if spools_updated > 0:
        logger.info("[SPOOLMAN] Reported partial usage to %s spool(s) using linear interpolation", spools_updated)


async def report_usage(printer_id: int, archive_id: int, spool_change_log: list[dict] | None = None):
    """Report filament usage to Spoolman after print completion.

    Two writers, mirroring the internal-inventory split in usage_tracker:

    1. **3MF path (primary)** — per-filament slice estimates captured at
       print start drive a precise per-slot ``use_spool`` call.
    2. **AMS remain%-delta (fallback)** — for slots the 3MF path didn't
       handle (including the no-3MF "Untitled" case from #1820): compute
       ``start_remain - current_remain``, multiply by the resolved
       Spoolman filament's reference weight, and write the delta. Mirrors
       ``usage_tracker.on_print_complete`` Path 2 (line 517).
    """
    async with async_session() as db:
        tracking = await claim_spoolman_tracking(db, printer_id, archive_id)
        if not tracking:
            logger.info("[SPOOLMAN] No tracking data for print (printer=%s, archive=%s)", printer_id, archive_id)
            return

        filament_usage = tracking.filament_usage or []
        ams_trays = {int(k): v for k, v in (tracking.ams_trays or {}).items()}
        slot_to_tray = tracking.slot_to_tray
        tray_remain_start = tracking.tray_remain_start or {}
        # ``layer_usage`` and ``filament_properties`` were added later than
        # the base tracking fields; use ``getattr`` so tests that stub
        # ``tracking`` as a lightweight SimpleNamespace stay valid, and
        # historic ORM rows loaded without these columns can't AttributeError
        # on read.
        layer_usage_raw = getattr(tracking, "layer_usage", None) or {}
        filament_properties = getattr(tracking, "filament_properties", None) or {}
        tray_now_at_start = getattr(tracking, "tray_now_at_start", None)
        printer_serial = await _get_printer_serial(printer_id)

        if not filament_usage and not tray_remain_start:
            logger.debug("[SPOOLMAN] No usage data or remain-snapshot for archive %s", archive_id)
            return

        client = await _get_spoolman_client_with_fallback()
        if not client:
            logger.warning("[SPOOLMAN] Not reachable for usage reporting")
            return

        # Consult the live printer state for the tray-change log written by
        # ``bambu_mqtt.py`` on every mid-print ``tray_now`` change (#957).
        # When there's more than one entry, the print traversed >1 AMS tray
        # and the split path attributes each segment to the tray that was
        # loaded at the time — matches the internal Spool inventory writer
        # in ``usage_tracker.py``. Without this, an AMS-backup runout switch
        # charges the whole slot to the origin spool and pushes it past
        # ``initial_weight`` (#1793).
        #
        # Split only for SINGLE-slot prints — same gate as
        # ``usage_tracker.py:1002``. Multi-slot (multi-colour) prints
        # naturally cycle trays for every colour change, so splitting each
        # slot's grams across ALL tray_change_log entries would attribute
        # slot 1's grams to the segments where slot 2's tray was loaded and
        # vice versa. Multi-slot prints fall through to the existing
        # single-tray path (which uses the stable ``slot_to_tray`` mapping).
        unmapped = _mapping_names_no_used_tray(slot_to_tray, filament_usage)
        if unmapped:
            slot_to_tray = None
        filament_usage = [
            u
            for u in filament_usage
            if not (
                slot_to_tray and 0 < u.get("slot_id", 0) <= len(slot_to_tray) and slot_to_tray[u["slot_id"] - 1] == -1
            )
        ]
        nonzero_slots = [u for u in filament_usage if u.get("used_g", 0) > 0]
        tray_changes: list[tuple[int, int]] = []
        _state = None
        if len(nonzero_slots) == 1:
            from backend.app.services.printer_manager import printer_manager as _pm

            _state = _pm.get_status(printer_id)
            if _state is not None:
                tray_changes = list(getattr(_state, "tray_change_log", []) or [])
        _total_layers = int(getattr(_state, "total_layers", 0) or 0) if _state else 0
        _current_layer = int(getattr(_state, "layer_num", 0) or 0) if _state else 0
        # For the linear-fallback denominator when total_layers is 0 (P1S
        # firmware resets it at print end). At completion the current layer
        # is the print's last valid layer.
        _layer_denom_hint = _total_layers or _current_layer

        mapping_source = "stored" if slot_to_tray else "none"
        if filament_usage and not slot_to_tray:
            slot_to_tray, mapping_source = _resolve_slot_to_tray_fallback(
                printer_id,
                filament_usage,
                tray_now_at_start,
                tray_state_only=unmapped,
            )
        logger.info(
            "[SPOOLMAN] Archive %s: slot_to_tray=%s (source: %s)",
            archive_id,
            slot_to_tray,
            mapping_source,
        )
        filament_usage = [u for u in filament_usage if not _slot_is_unfed(u.get("slot_id", 0), slot_to_tray)]
        mapping_is_guess = bool(filament_usage) and mapping_source == "none" and len(tray_changes) <= 1
        if mapping_is_guess:
            logger.warning(
                "[SPOOLMAN] Archive %s: no slot-to-tray mapping from any source; "
                "charging by tray position and preserving sliced archive provenance.",
                archive_id,
            )

        slot_colors: dict[int, str] = {}
        usage_costs: list[SpoolmanUsageCharge] = []
        swaps = _swap_splitter(printer_id, _state, layer_usage_raw, _layer_denom_hint, completed=True)
        if spool_change_log is not None:
            swaps.log = list(spool_change_log)
        handled_global_tray_ids: set[int] = set()
        spools_updated = 0

        # --- Path 1: 3MF per-slot estimates -----------------------------
        if filament_usage:
            if len(tray_changes) > 1:
                # Tray-split path — attribute per-segment to the tray that
                # was loaded at that time.
                logger.info(
                    "[SPOOLMAN] Reporting per-filament usage for archive %s with tray-split "
                    "(tray_change_log=%s, denom_layers=%d)",
                    archive_id,
                    tray_changes,
                    _layer_denom_hint,
                )
                # ``tracking.layer_usage`` was serialized to JSON so int keys
                # come back as strings. Restore them for the split math.
                layer_usage = None
                if layer_usage_raw:
                    try:
                        layer_usage = {
                            int(layer): {int(fid): mm for fid, mm in filaments.items()}
                            for layer, filaments in layer_usage_raw.items()
                        }
                    except (TypeError, ValueError, AttributeError):
                        # AttributeError catches ``inner.items()`` when the
                        # inner value isn't dict-shaped (corrupt JSON row).
                        # Missing gcode falls through to the linear-ratio
                        # branch inside ``compute_tray_split_grams`` — still
                        # gives a correct split, just less precise.
                        layer_usage = None
                split_updated, split_handled = await _report_spool_usage_split_by_tray_changes(
                    client,
                    filament_usage,
                    tray_changes,
                    ams_trays,
                    layer_usage,
                    filament_properties,
                    _total_layers,
                    _layer_denom_hint,
                    f"Archive {archive_id}",
                    printer_serial,
                    printer_id=printer_id,
                    slot_colors_out=slot_colors,
                    usage_costs_out=usage_costs,
                    swaps=swaps,
                )
                spools_updated += split_updated
                handled_global_tray_ids |= split_handled
            else:
                logger.info("[SPOOLMAN] Reporting per-filament usage for archive %s", archive_id)
                usage_items = [(u.get("slot_id", 0), u.get("used_g", 0)) for u in filament_usage]
                spools_updated = await _report_spool_usage_for_slots(
                    client,
                    usage_items,
                    ams_trays,
                    slot_to_tray,
                    f"Archive {archive_id}",
                    printer_serial,
                    printer_id=printer_id,
                    slot_colors_out=slot_colors,
                    usage_costs_out=usage_costs,
                    swaps=swaps,
                )
                # Track which physical slots the 3MF path already covered so
                # Path 2 doesn't double-charge them.
                for u in filament_usage:
                    if u.get("used_g", 0) <= 0:
                        continue
                    slot_id = u.get("slot_id", 0)
                    handled_global_tray_ids.add(_resolve_global_tray_id(slot_id, slot_to_tray, ams_trays))

        # --- Path 2: AMS remain%-delta for slots 3MF didn't cover -------
        # Triggered for no-3MF "Untitled" prints (#1820) AND for partial
        # 3MF coverage (slots whose filament_id wasn't in slice_info).
        if tray_remain_start and not (slot_to_tray and all(tray == -1 for tray in slot_to_tray)):
            from backend.app.services.printer_manager import printer_manager

            current = printer_manager.get_status(printer_id)
            current_lookup = _snapshot_tray_remain(current.raw_data) if current and current.raw_data else {}
            fallback_updates = await _report_remain_delta_for_slots(
                client,
                printer_id=printer_id,
                tray_remain_start=tray_remain_start,
                current_lookup=current_lookup,
                handled_global_tray_ids=handled_global_tray_ids,
                archive_id=archive_id,
                print_used_keys=_print_used_tray_keys(slot_to_tray, tray_now_at_start, current),
                slot_colors_out=slot_colors,
                usage_costs_out=usage_costs,
            )
            spools_updated += fallback_updates

        if spools_updated == 0:
            logger.info("[SPOOLMAN] Archive %s: no spools updated", archive_id)
        else:
            logger.info("[SPOOLMAN] Archive %s: updated %s spool(s)", archive_id, spools_updated)

        await record_spoolman_usage(db, printer_id, archive_id, "completed", usage_costs)

        # Stamp the archive's filament colour from the matched Spoolman spools
        # so it reflects the curated inventory colour, not the slicer's 3MF
        # value (#1494) — mirrors the built-in inventory path in usage_tracker.
        if mapping_is_guess:
            if slot_colors:
                logger.info(
                    "[SPOOLMAN] Archive %s: leaving filament colour as sliced because tray position was a guess",
                    archive_id,
                )
        else:
            await _apply_spool_colors_to_archive(db, archive_id, filament_usage, slot_colors)
        scoped_filament_grams = sum(positive_finite_number(item.get("used_g")) or 0.0 for item in filament_usage)
        return await _apply_spoolman_costs_to_archive(
            db,
            archive_id,
            [(charge.grams, charge.cost) for charge in usage_costs],
            total_filament_grams=scoped_filament_grams or None,
        )


def _print_used_tray_keys(
    slot_to_tray: list | None,
    tray_now_at_start: int | None,
    state,
) -> set[tuple[int, int]]:
    """Return the physical slots this print is known to have used."""
    keys: set[tuple[int, int]] = set()
    for global_tray_id in list(slot_to_tray or []):
        if isinstance(global_tray_id, int) and not isinstance(global_tray_id, bool) and global_tray_id >= 0:
            keys.add(_global_tray_id_to_ams_slot(global_tray_id))
    for change in getattr(state, "tray_change_log", None) or []:
        if isinstance(change, (tuple, list)) and change:
            global_tray_id = change[0]
            if isinstance(global_tray_id, int) and not isinstance(global_tray_id, bool) and global_tray_id >= 0:
                keys.add(_global_tray_id_to_ams_slot(global_tray_id))
    if _is_real_tray_id(tray_now_at_start):
        keys.add(_global_tray_id_to_ams_slot(tray_now_at_start))
    return keys


async def _report_remain_delta_for_slots(
    client,
    *,
    printer_id: int,
    tray_remain_start: dict[str, dict],
    current_lookup: dict[str, dict],
    handled_global_tray_ids: set[int],
    archive_id: int,
    print_used_keys: set[tuple[int, int]] | None = None,
    slot_colors_out: dict[int, str] | None = None,
    usage_costs_out: list[SpoolmanUsageCharge] | None = None,
) -> int:
    """AMS remain%-delta path: write ``(start - current) * filament.weight``
    grams to Spoolman for slots the 3MF path didn't cover.

    Mirrors ``usage_tracker.on_print_complete`` Path 2: per-slot, gated on a
    valid current ``remain%``, skipped on spool swap (``tray_uuid`` changed),
    using the resolved spool's filament reference weight rather than MQTT's
    unreliable ``tray_weight`` (which is the failure mode #1119 documented).
    """
    spools_updated = 0
    for slot_key, start in tray_remain_start.items():
        try:
            ams_id_str, tray_id_str = slot_key.split("-", 1)
            ams_id, tray_id = int(ams_id_str), int(tray_id_str)
        except (ValueError, AttributeError):
            continue

        # Skip slots already handled by the 3MF path. Encoding mirrors
        # build_ams_tray_lookup: VT trays land at 254/255, AMS-HT keeps
        # its native id (>=128), regular AMS slots are ams_id*4+tray_id.
        if ams_id == 255:
            global_tray_id = 254 + tray_id
        elif ams_id >= 128:
            global_tray_id = ams_id
        else:
            global_tray_id = ams_id * 4 + tray_id
        if global_tray_id in handled_global_tray_ids:
            continue

        if print_used_keys and (ams_id, tray_id) not in print_used_keys:
            continue

        current = current_lookup.get(slot_key)
        if not current:
            logger.debug("[SPOOLMAN] AMS%d-T%d: no current remain%% at completion, skipping fallback", ams_id, tray_id)
            continue

        # Spool swap mid-print — tray_uuid changed. We don't know how much
        # of the print went to which spool; skip rather than mis-attribute.
        start_uuid = (start.get("tray_uuid") or "").lower()
        cur_uuid = (current.get("tray_uuid") or "").lower()
        if start_uuid and cur_uuid and start_uuid != cur_uuid:
            logger.info(
                "[SPOOLMAN] AMS%d-T%d: spool swapped mid-print (uuid changed), skipping remain-delta", ams_id, tray_id
            )
            continue

        delta_pct = start["remain"] - current["remain"]
        if delta_pct <= 0:
            continue  # No consumption captured at AMS granularity, or refilled

        spool_id = await _resolve_spool_id_via_slot_assignment(printer_id, ams_id, tray_id)
        if spool_id is None:
            logger.debug("[SPOOLMAN] AMS%d-T%d: no Spoolman slot assignment, skipping fallback", ams_id, tray_id)
            continue

        # Look up the spool's filament reference weight. Use a fresh GET so
        # we don't depend on a stale cached_spools list. Failure here is
        # silent-skip rather than fatal — other slots can still be written.
        try:
            spool = await client.get_spool(spool_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[SPOOLMAN] AMS%d-T%d: get_spool(%s) failed: %s", ams_id, tray_id, spool_id, exc)
            continue

        ref_weight = spoolman_net_weight(spool)
        filament = spool.get("filament") or {}
        if not ref_weight or ref_weight <= 0:
            logger.debug(
                "[SPOOLMAN] AMS%d-T%d: spool %s has no filament.weight, skipping remain-delta",
                ams_id,
                tray_id,
                spool_id,
            )
            continue

        grams_used = round((delta_pct / 100.0) * ref_weight, 2)
        if grams_used <= 0:
            continue
        try:
            await client.use_spool(spool_id, grams_used)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[SPOOLMAN] AMS%d-T%d: use_spool(%s, %.2fg) failed: %s", ams_id, tray_id, spool_id, grams_used, exc
            )
            continue

        cost = _spoolman_usage_cost(spool, grams_used)
        if usage_costs_out is not None:
            usage_costs_out.append(SpoolmanUsageCharge(spool_id, grams_used, cost, ref_weight))

        spools_updated += 1
        if slot_colors_out is not None:
            color = filament.get("color_hex")
            if color:
                # No 3MF slot_id for this path — use the AMS slot key so the
                # colour map can still be inspected by callers if needed.
                # The archive-colour rewrite (#1494) keys on 3MF slot_ids so
                # remain-delta-only prints intentionally don't participate
                # in that rewrite (matches usage_tracker's slot_id=None).
                slot_colors_out[-(global_tray_id + 1)] = color
        logger.info(
            "[SPOOLMAN] Archive %s AMS%d-T%d: %.2fg via remain-delta (%d%% of %.0fg) -> spool %s",
            archive_id,
            ams_id,
            tray_id,
            grams_used,
            delta_pct,
            ref_weight,
            spool_id,
        )
    return spools_updated


async def _apply_spool_colors_to_archive(
    db,
    archive_id: int,
    filament_usage: list[dict],
    slot_colors: dict[int, str],
) -> None:
    """Overwrite an archive's ``filament_color`` with the colours of the
    Spoolman spools that fed the print (#1494).

    All-or-nothing, exactly like the built-in inventory path: the colour is
    only rewritten when every used slot resolved to a spool that carries a
    colour, so a partial match never drops slots from the archive.
    """
    if not slot_colors:
        return

    from backend.app.models.archive import PrintArchive
    from backend.app.services.usage_tracker import (
        _archive_colors_from_spools,
        _spool_color_to_hex,
    )

    results = [{"slot_id": sid, "color": _spool_color_to_hex(hex_)} for sid, hex_ in slot_colors.items()]
    colors = _archive_colors_from_spools(filament_usage, results)
    if not colors:
        return

    archive = (await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))).scalar_one_or_none()
    if archive is None:
        return

    joined = ",".join(colors)
    if joined != archive.filament_color:
        logger.info(
            "[SPOOLMAN] Archive %s filament_color %r -> %r (from Spoolman spools)",
            archive_id,
            archive.filament_color,
            joined,
        )
        archive.filament_color = joined
        await db.commit()


def _swap_splitter(printer_id: int, state, layer_usage_raw, end_layer: int, completed: bool) -> spool_swaps.Splitter:
    """The print's spool swaps (services.spool_swaps) for the Spoolman charges.

    ``layer_usage_raw`` is the tracking row's JSON, keys as strings; parsed only
    when a tray was actually swapped.
    """
    if state is None:
        from backend.app.services.printer_manager import printer_manager

        state = printer_manager.get_status(printer_id)
    if not isinstance(end_layer, int) or end_layer <= 0:
        # The caller reads the printer's layers for single-slot prints only;
        # a multi-colour print's swap needs them as much.
        total = getattr(state, "total_layers", 0)
        current = getattr(state, "layer_num", 0)
        end_layer = max(total if isinstance(total, int) else 0, current if isinstance(current, int) else 0)

    def layer_usage():
        if not layer_usage_raw:
            return None
        return {int(layer): {int(fid): mm for fid, mm in f.items()} for layer, f in layer_usage_raw.items()}

    return spool_swaps.Splitter(
        getattr(state, "spool_change_log", None) if state is not None else None,
        spool_swaps.SPOOLMAN,
        layer_usage,
        end_layer,
        completed=completed,
    )


async def _fetch_spool_for_price(client, spool_id: int) -> dict | None:
    """The spool row a swapped-in spool's share is priced from; None if it can't be read."""
    try:
        return await client.get_spool(spool_id)
    except Exception as exc:  # noqa: BLE001 -- pricing is best-effort, the charge is not
        logger.debug("[SPOOLMAN] Could not fetch spool %s for its price: %s", spool_id, exc)
        return None


async def _charge_shares(client, shares, resolved_id, resolved_spool, usage_costs_out, method_label) -> int:
    updated = 0
    for spool_id, grams in shares:
        grams = round(grams, 2)
        if grams <= 0:
            continue
        spool = resolved_spool
        if spool_id != resolved_id:
            spool = await _fetch_spool_for_price(client, spool_id) if usage_costs_out is not None else None
        try:
            await client.use_spool(spool_id, grams)
            if usage_costs_out is not None:
                usage_costs_out.append(
                    SpoolmanUsageCharge(
                        spool_id,
                        grams,
                        _spoolman_usage_cost(spool, grams),
                        spoolman_net_weight(spool) if spool else None,
                    )
                )
            logger.info("[SPOOLMAN] %s: %.2fg -> spool %s", method_label, grams, spool_id)
            updated += 1
        except (SpoolmanNotFoundError, SpoolmanClientError, SpoolmanUnavailableError) as exc:
            logger.warning("[SPOOLMAN] Failed to record usage for spool %s: %s", spool_id, exc)
    return updated


def _extract_3mf_tracking(full_path, plate_id: int | None) -> tuple[list | None, dict | None, dict | None]:
    """What Spoolman's tracking reads from a print's 3MF: the per-filament
    grams, the per-layer usage (JSON keys) and the filament properties."""
    from backend.app.utils.threemf_tools import (
        extract_filament_properties_from_3mf,
        extract_filament_usage_from_3mf,
        extract_layer_filament_usage_from_3mf,
    )

    filament_usage = extract_filament_usage_from_3mf(full_path, plate_id) or None
    layer_usage_json: dict | None = None
    layer_usage = extract_layer_filament_usage_from_3mf(full_path, plate_id)
    if layer_usage:
        # Convert int keys to string for JSON serialization
        layer_usage_json = {str(k): v for k, v in layer_usage.items()}
        logger.debug("[SPOOLMAN] Parsed %s layers from G-code", len(layer_usage))
    return filament_usage, layer_usage_json, extract_filament_properties_from_3mf(full_path)


async def attach_recovered_3mf(
    printer_id: int,
    archive_id: int,
    file_path: str,
    db,
    printer_manager,
    *,
    plate_id: int | None = None,
    may_start: bool = True,
) -> None:
    """Add a fallback archive's recovered 3MF to Spoolman's tracking of its print.

    Print start found no 3MF, so it stored only the AMS remain% snapshot and
    completion would charge the remain% change. Only the 3MF's own data is
    added: the snapshot was taken at print start, and replacing it from the
    mid-print state now would charge the wrong change for a slot the 3MF does
    not cover. Usage already tracked is left alone.

    When print start stored nothing (no slot had a remain%), the 3MF is
    tracked on its own if ``may_start``: from the recovery inside the print's
    close-out, which runs before the charge, or from any other while the print
    runs and is not being closed. During a close-out another recovery's row
    could follow the charge that already deleted the print's tracking, and be
    left behind.
    """
    from backend.app.api.routes.settings import get_setting
    from backend.app.models.active_print_spoolman import ActivePrintSpoolman

    full_path = (
        app_settings.base_dir / file_path
    )  # SEC-PATH-OK: file_path is archive.file_path — DB-stored, internally generated
    if not file_path or not full_path.exists():
        return

    row = (
        await db.execute(
            select(ActivePrintSpoolman)
            .where(ActivePrintSpoolman.printer_id == printer_id)
            .where(ActivePrintSpoolman.archive_id == archive_id)
        )
    ).scalar_one_or_none()
    from backend.app.models.active_print_session import ActivePrintSession

    session = await db.get(ActivePrintSession, printer_id)
    owner = getattr(session, "spoolman_owns_usage", None) if session is not None else None
    if owner is False:
        return
    if row is None and owner is None:
        enabled = (await get_setting(db, "spoolman_enabled") or "").lower() == "true"
        if not enabled:
            return
    if row is not None and row.filament_usage:
        return
    if row is None and not may_start:
        return

    filament_usage, layer_usage_json, filament_properties = _extract_3mf_tracking(full_path, plate_id)
    if not filament_usage:
        return
    from backend.app.core.printer_lifecycle import lock_existing_printer

    if not await lock_existing_printer(db, printer_id):
        return
    if row is None:
        state = printer_manager.get_status(printer_id)
        row = ActivePrintSpoolman(
            printer_id=printer_id,
            archive_id=archive_id,
            ams_trays=build_ams_tray_lookup(state.raw_data) if state and state.raw_data else {},
        )
        db.add(row)
    row.filament_usage = filament_usage
    row.layer_usage = layer_usage_json
    row.filament_properties = filament_properties
    await db.commit()
    logger.info(
        "[SPOOLMAN] Archive %s: tracking now has the recovered 3MF's usage (%d filament(s))",
        archive_id,
        len(filament_usage),
    )


def _slot_is_unfed(slot_id, mapping) -> bool:
    return bool(mapping and 0 < slot_id <= len(mapping) and mapping[slot_id - 1] < 0)


async def release_archived_slot_rows(printer_id: int) -> None:
    """Unassign the printer's slots whose Spoolman spool is archived or gone.

    Archiving a spool through Bambuddy keeps the slot of a printer whose print
    it may be feeding: usage is charged at completion by the slot's spool, and
    only the slot row knows it for a spool without a tag. Run once that print's
    usage is reported. Also catches spools archived or deleted in Spoolman.
    Best-effort: a failure leaves the rows for the next print to try again.
    """
    from typing import cast

    from sqlalchemy.engine import CursorResult

    from backend.app.api.routes.settings import get_setting
    from backend.app.models.active_print_spoolman import ActivePrintSpoolman
    from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
    from backend.app.services.ams_assignment_lock import get_ams_assignment_lock
    from backend.app.services.spool_slot_release import announce_freed_slots

    try:
        async with async_session() as db:
            enabled = await get_setting(db, "spoolman_enabled")
            if not enabled or enabled.lower() != "true":
                return
            rows = (
                (
                    await db.execute(
                        select(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.printer_id == printer_id)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                return
            client = await _get_spoolman_client_with_fallback()
            if not client:
                return
            live = {
                spool["id"]
                for spool in await client.get_all_spools(allow_archived=True)
                if spool.get("id") is not None and not spool.get("archived")
            }
            freed: list[tuple[int, int, int]] = []
            async with get_ams_assignment_lock(printer_id):
                if await db.scalar(
                    select(ActivePrintSpoolman.id).where(ActivePrintSpoolman.printer_id == printer_id).limit(1)
                ):
                    return
                for row in rows:
                    if row.spoolman_spool_id in live:
                        continue
                    # Keyed on the spool too: the slot may have been given another
                    # spool since the rows were read.
                    result = cast(
                        CursorResult,
                        await db.execute(
                            delete(SpoolmanSlotAssignment).where(
                                SpoolmanSlotAssignment.id == row.id,
                                SpoolmanSlotAssignment.spoolman_spool_id == row.spoolman_spool_id,
                            )
                        ),
                    )
                    if result.rowcount:
                        freed.append((printer_id, row.ams_id, row.tray_id))
                if not freed:
                    return
                await db.commit()
        await announce_freed_slots(freed)
    except Exception as e:  # noqa: BLE001 — best-effort cleanup after completion
        logger.warning("[SPOOLMAN] Could not release archived spools' slots on printer %s: %s", printer_id, e)
