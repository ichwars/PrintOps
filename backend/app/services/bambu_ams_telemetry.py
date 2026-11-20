"""Decode AMS telemetry and translate spool identifiers to firmware wire values."""

import logging

from backend.app.utils.tray_ids import (
    RACK_SLOT_COUNT,
    AmsType,
    TrayLayout,
    ams_type_from_info,
    is_ams_ht_id,
    is_external_tray,
    is_rack_ams,
    legacy_tray_index,
    tray_flag_bit,
    unit_ams_type,
)

logger = logging.getLogger(__name__)

AMS3H_MODULE_NAME = "n10a"  # its get_version module (no "/<unit>" suffix)


def _mqtt_int(value: object) -> int | None:
    """An MQTT id / number field as an int (they arrive as int or numeric str), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


# AMS 3H drying (Bambu Studio 02.09, AMSDryControl.cpp): the unit reports
# `zone_info[]` and only a zone with exactly two slots can dry; the others are
# ambient readings. A drying start carries the filament's softening temperature
# as `cooling_temp` (the preset's filament_dev_drying_softening_temperature).
AMS3H_DRY_COOLING_TEMP = {"PLA": 65, "PETG": 75, "ABS": 95, "ASA": 95, "TPU": 70, "PA": 150, "PC": 120}
AMS3H_DRY_COOLING_TEMP_DEFAULT = 50


def ams3h_drying_zone(zone_info: object) -> dict | None:
    """The zone of an AMS 3H's `zone_info` that can dry: the first holding exactly two slots."""
    if not isinstance(zone_info, list):
        return None
    for zone in zone_info:
        if isinstance(zone, dict) and isinstance(zone.get("zone_slots"), list) and len(zone["zone_slots"]) == 2:
            return zone
    return None


def ams3h_drying_cooling_temp(filament: str) -> int:
    """`cooling_temp` for an AMS 3H drying start: the filament's softening temperature."""
    base = (filament or "").upper().split("-")[0].split(" ")[0]
    return AMS3H_DRY_COOLING_TEMP.get(base, AMS3H_DRY_COOLING_TEMP_DEFAULT)


def _ams3h_unit_drying_fields(unit: dict) -> dict:
    """An AMS 3H's drying state, which lives on its drying zone, lifted onto the unit."""
    zone = ams3h_drying_zone(unit.get("zone_info"))
    if zone is None:
        return {}
    fields: dict = {"dry_zone_id": zone.get("zone_id", 0), "dry_zone_slots": list(zone.get("zone_slots") or [])}
    for key in ("dry_time", "dry_setting", "dry_sf_reason"):
        if key in zone:
            fields[key] = zone[key]
    if "info" not in unit and "info" in zone:
        fields["info"] = zone["info"]
    if "humidity_raw" in zone:
        fields["dry_zone_humidity_raw"] = zone["humidity_raw"]
    if "temp" in zone:
        fields["dry_zone_temp"] = zone["temp"]
    return fields


def _ams3h_unit_env_fields(unit: dict) -> dict:
    """An AMS 3H's humidity and temperature (the unit has none) from its first non-drying zone, as Studio shows it."""
    zones = unit.get("zone_info")
    if not isinstance(zones, list):
        return {}
    dry_zone = ams3h_drying_zone(zones)
    ambient = next((z for z in zones if isinstance(z, dict) and z is not dry_zone), None)
    if ambient is None:
        return {}
    return {key: ambient[key] for key in ("humidity_raw", "temp") if key in ambient and key not in unit}


def apply_rack_ams_zone_fields(ams_list: object, known_types: dict[int, AmsType] | None = None) -> None:
    """Lift a rack AMS's per-zone readings and drying state onto the unit, in place (type from `info`, else ``known_types``)."""
    if not isinstance(ams_list, list):
        return
    for unit in ams_list:
        if not isinstance(unit, dict) or not isinstance(unit.get("zone_info"), list):
            continue
        uid = _mqtt_int(unit.get("id"))
        if uid is None:
            continue
        kind = ams_type_from_info(unit.get("info"))
        if kind is None:
            kind = (known_types or {}).get(uid, unit_ams_type(uid))
        if not is_rack_ams(kind):
            continue
        unit.update({**_ams3h_unit_env_fields(unit), **_ams3h_unit_drying_fields(unit)})


def resolve_external_spools_in_mapping(
    ams_mapping: object, ams_mapping2: object, is_dual_nozzle: bool, layout: TrayLayout | None = None
) -> object:
    """Put the external spool back into a captured flat ``ams_mapping`` (#3166).

    The firmware rejects 254/255 in the flat list, so BambuStudio and our own
    dispatch both write an external spool there as -1 -- the same value as a
    slot that isn't fed at all -- and carry the real target only in
    ``ams_mapping2`` as ``{ams_id: 254|255, slot_id: 0}``. Capturing the flat
    list alone turns "printed from the external spool" into "unmapped", and
    usage then lands on whatever tray the fallback guesses.

    Each -1 whose ``ams_mapping2`` entry names an external spool becomes the
    global tray the rest of PrintOps uses: the ams_id itself on dual-nozzle
    printers (254 = left/deputy, 255 = right/main), 254 on single-nozzle
    printers, which have one external spool that the wire always calls 255.
    ``{255, 255}`` is the unmapped marker and stays -1.

    An A2L AMS-Lite tray is the local slot 0-3 in the flat list and
    ``{ams_id: 16, slot_id: n}`` in ``ams_mapping2``; it becomes its normalised
    global tray 24+n. Kept local, it read as a regular AMS tray, so usage was
    charged to the wrong spool. A rack AMS slot (``{ams_id: 32, slot_id: k}``)
    becomes its global tray 28+k, and on a rack printer each external input
    247-255 keeps its own id. Every other entry is left exactly as captured.
    Without a usable ``ams_mapping2`` the input is returned unchanged.
    """
    if not isinstance(ams_mapping, list) or not isinstance(ams_mapping2, list):
        return ams_mapping
    if len(ams_mapping2) != len(ams_mapping):
        return ams_mapping
    resolved = list(ams_mapping)
    layout = layout or TrayLayout()
    for i, (flat, detail) in enumerate(zip(ams_mapping, ams_mapping2, strict=True)):
        if not isinstance(detail, dict):
            continue
        ams_id = detail.get("ams_id")
        slot_id = detail.get("slot_id")
        if ams_id == A2L_LITE_PHYSICAL_AMS_ID and slot_id in (0, 1, 2, 3):
            resolved[i] = A2L_LITE_GLOBAL_BASE + slot_id
            continue
        if (
            isinstance(ams_id, int)
            and isinstance(slot_id, int)
            and not is_external_tray(ams_id, layout.rack)
            and is_rack_ams(layout.ams_type(ams_id))
            and 0 <= slot_id < RACK_SLOT_COUNT
        ):
            resolved[i] = layout.global_tray_id(ams_id, slot_id)
            continue
        if flat != -1 or not is_external_tray(ams_id, layout.rack) or slot_id == 255:
            continue
        resolved[i] = ams_id if is_dual_nozzle or layout.rack else 254
    return resolved


def parse_ams_filament_backup_from_cfg(cfg_raw: object) -> bool | None:
    """Extract AMS Filament Backup state from a Bambu push_status ``print.cfg`` value.

    OrcaSlicer reads bit 18 of the hex string via
    ``get_flag_bits(cfg, 18)`` (DeviceManager.cpp:4961). Old-protocol families
    (A1 / A1 Mini) omit ``cfg`` entirely; this returns ``None`` for any input
    that doesn't yield a clean integer so downstream consumers preserve today's
    behaviour rather than treating "absent" as "OFF".
    """
    if not isinstance(cfg_raw, str) or not cfg_raw:
        return None
    try:
        return bool((int(cfg_raw, 16) >> 18) & 1)
    except ValueError:
        return None


A2L_LITE_PHYSICAL_AMS_ID = 16
A2L_LITE_NORMALIZED_AMS_ID = 6
A2L_LITE_GLOBAL_BASE = A2L_LITE_NORMALIZED_AMS_ID * 4


def normalize_am_unit_id(ams_id: int) -> int:
    """Normalize the A2L AMS Lite's physical unit id 16 to id 6."""
    return A2L_LITE_NORMALIZED_AMS_ID if ams_id == A2L_LITE_PHYSICAL_AMS_ID else ams_id


def wire_tray_color(tray_color: str | None) -> str:
    """Return bare uppercase hex, the format AMS firmware parses reliably."""
    return (tray_color or "").strip().lstrip("#").upper()


def a2l_lite_wire_ids(ams_id: int, tray_id: int) -> tuple[int, int, int] | None:
    """Translate a normalized A2L AMS Lite slot back to physical wire ids."""
    if ams_id != A2L_LITE_NORMALIZED_AMS_ID:
        return None
    local_slot = tray_id % 4
    return (
        A2L_LITE_PHYSICAL_AMS_ID,
        local_slot,
        legacy_tray_index(A2L_LITE_PHYSICAL_AMS_ID, local_slot),
    )


def change_filament_wire_ids(tray_id: int, layout: TrayLayout | None = None) -> tuple[int, int, int]:
    """``(ams_id, slot_id, target)`` of ``ams_change_filament`` for an AMS tray.

    As BambuStudio's ``command_ams_change_filament`` builds them: a regular AMS
    is addressed by unit and local slot with the global tray as target; a unit
    id of 16 or more (the A2L AMS-Lite's physical 16, an AMS-HT's 128-135) has
    the unit id itself as target. An AMS-HT holds one tray, so its global tray
    id is its unit id and its slot is 0.
    """
    if is_ams_ht_id(tray_id):
        return tray_id, 0, tray_id
    ams_id, slot_id = (layout or TrayLayout()).slot_key(tray_id)
    if (a2l := a2l_lite_wire_ids(ams_id, tray_id)) is not None:
        return a2l[0], a2l[1], a2l[0]
    return ams_id, slot_id, tray_id


def apply_tray_exist_bits(
    units: list,
    tray_exist_bits_str: str | int | None,
    *,
    power_on_flag: bool = True,
    log_label: str | None = None,
    annotate_exists: bool = False,
) -> int:
    """Wipe stale per-tray filament fields on slots whose `tray_exist_bits` bit is 0.

    `tray_exist_bits` is firmware's canonical "which slots have a spool" bitmask
    (BambuStudio uses it too). For every slot whose bit is 0, promote the tray
    `state` to 9 (firmware's "no spool" code) and clear `tray_type` / `tray_color`
    / `tray_info_idx` / `tag_uid` / `tray_uuid` / `remain` etc so downstream
    readers (PrintOps's AMS card, the VP slicer-facing cache, inventory short-
    circuits keyed on `state in {9, 10}`) all see one canonical empty-slot signal
    instead of guessing from payload shape (#1322, #147).

    Two callers share this helper to keep their views consistent:

    1. ``_handle_ams_data`` for PrintOps's internal AMS state (printer card).
    2. ``virtual_printer.mqtt_bridge._on_printer_raw`` for the cached slicer-
       facing push_status (#1726 — without this the VP would forward stale
       per-tray fields for empty slots, and BambuStudio's Sync would render
       phantom loaded slots).

    Skipped only on the printer-shutdown pattern: all-zero bits paired with
    ``power_on_flag=False`` (#765). Non-zero bits with ``power_on_flag=False``
    is valid idle-printer state (#1365 — X1C between prints) and MUST be applied
    so spool removal is detected without requiring a manual reconnect.

    AMS-HT units (``id`` 128-135) are single-tray dry boxes whose presence bit
    is packed at ``16 + (ams_id - 128)`` instead of ``ams_id * 4`` (#2670).

    `tray_exist_bits_str` is expected as a hex string (firmware sends it that
    way). Ints are tolerated for defensive symmetry but typically not seen
    on the wire. ``None`` / empty / unparseable → no-op.

    ``annotate_exists`` writes each processed slot's physical presence bit. The
    printer-card path uses it to distinguish a present unconfigured spool from
    a genuinely empty slot.

    Mutates ``units`` in place. Returns the number of slots cleared.
    """
    if not tray_exist_bits_str:
        return 0
    try:
        if isinstance(tray_exist_bits_str, int):
            tray_exist_bits = tray_exist_bits_str
        else:
            tray_exist_bits = int(tray_exist_bits_str, 16)
    except (ValueError, TypeError):
        return 0
    if tray_exist_bits == 0 and not power_on_flag:
        return 0
    if not isinstance(units, list):
        return 0

    cleared = 0
    for ams_unit in units:
        if not isinstance(ams_unit, dict):
            continue
        ams_id_raw = ams_unit.get("id")
        if ams_id_raw is None:
            continue
        try:
            ams_id = int(ams_id_raw) if isinstance(ams_id_raw, str) else ams_id_raw
        except (ValueError, TypeError):
            continue
        if not isinstance(ams_id, int):
            continue
        kind = unit_ams_type(ams_id, ams_unit.get("info"))
        for tray in ams_unit.get("tray", []):
            if not isinstance(tray, dict):
                continue
            tray_id_raw = tray.get("id")
            if tray_id_raw is None:
                continue
            try:
                tray_id = int(tray_id_raw) if isinstance(tray_id_raw, str) else tray_id_raw
            except (ValueError, TypeError):
                continue
            if not isinstance(tray_id, int):
                continue
            global_bit = tray_flag_bit(ams_id, tray_id, kind)
            if global_bit is None or global_bit < 0:
                continue
            slot_exists = (tray_exist_bits >> global_bit) & 1
            if annotate_exists:
                tray["exists"] = bool(slot_exists)
            if slot_exists:
                continue
            tray["state"] = 9
            if tray.get("tray_type"):
                if log_label:
                    logger.debug(
                        f"[{log_label}] Clearing empty slot: AMS {ams_id} slot {tray_id} "
                        f"(tray_exist_bits bit {global_bit} = 0)"
                    )
                tray["tray_type"] = ""
                tray["tray_sub_brands"] = ""
                tray["tray_color"] = ""
                tray["tray_id_name"] = ""
                tray["tag_uid"] = "0000000000000000"
                tray["tray_uuid"] = "00000000000000000000000000000000"
                tray["tray_info_idx"] = ""
                tray["remain"] = 0
                cleared += 1
    return cleared


def _external_slot_to_merge(pushed: object, existing: object) -> dict | None:
    """The one cached external slot a pushed ``vt_tray`` dict updates, or None (#3513).

    It updates the slot when it names no slot or the cached one's. A push that
    empties the slot (``tray_type`` ``""``) replaces it, so a removed spool
    keeps no preset, K value or temperatures, as does one naming another slot.
    """
    if not isinstance(pushed, dict) or not isinstance(existing, list) or len(existing) != 1:
        return None
    cached = existing[0]
    if not isinstance(cached, dict) or pushed.get("tray_type") == "":
        return None
    if "id" in pushed and str(pushed["id"]) != str(cached.get("id")):
        return None
    return cached
