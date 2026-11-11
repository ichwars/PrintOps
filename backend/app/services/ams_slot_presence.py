"""Is there a spool in this AMS slot?

Three backend decisions turn on the answer -- whether to push
``ams_filament_setting`` when a spool is assigned, whether a pre-assigned slot
has just been filled, and whether an assignment has gone stale -- and all three
used to read it off the tray's ``state`` field. That field cannot carry it.

## Why ``state`` is the wrong source

``state`` is firmware-variant. The A1 Mini BMCU and the P1S Standard AMS report
3 for a loaded slot and never emit 11; the AMS-HT's codes differ again (#2670).
Bambuddy already works around that on the printer card, where
``getEmptySlotKind`` (``PrintersPage.tsx``) reads the presence bit first and
only falls back to the 9/10 heuristic when there is no bit to read.

Worse, ``state`` is partly Bambuddy's own writing. ``apply_tray_exist_bits``
sets ``state = 9`` on every slot whose presence bit is 0 -- and when the bit
comes back it leaves the 9 exactly where it was, because the "slot occupied"
branch only annotates ``exists`` and moves on. So a slot the firmware says is
full can sit in the cache reading ``exists=True, state=9`` indefinitely. That
is #3084: a non-Bambu spool is swapped in, Assign Spool reads the stale 9,
calls the slot empty, sends no MQTT, and the printer keeps showing ``?``. The
deferred-configuration replay could not rescue it either, because its own
"loaded" test was the same 9/10 heuristic -- the exact deadlock #1322 removed
elsewhere. #3100 is the same stale 9 one step further on: the replay does not
fire, the assignment keeps the empty fingerprint it was stored with, and the
first real tray report is read as a spool swap and deleted.

## What this module answers

``tray_exist_bits`` is the firmware's own "which slots have a spool" bitmask --
the one BambuStudio draws its ``?`` from -- and ``apply_tray_exist_bits``
records it per tray as ``exists``. That bit is authoritative where it exists,
and absent otherwise; it is never a guess. Callers that want a decision for a
payload carrying no bit at all keep their own fallback, because the right
fallback differs per caller: the assign path wants to know whether the push is
doomed, the unlink pass wants to know whether a spool was removed, and a state
of 26 ("unloaded", mid-runout) answers those two questions differently.
"""

from collections.abc import Mapping
from typing import Any


def spool_present(tray: Mapping[str, Any] | None) -> bool | None:
    """Does firmware's presence bit say a spool is in this slot?

    ``True`` / ``False`` straight from ``tray_exist_bits``; ``None`` when the
    tray carries no presence annotation, which means the caller has to decide
    on its own terms rather than assume either way.

    Only the internal AMS path annotates ``exists`` (``apply_tray_exist_bits``
    is called with ``annotate_exists=True`` there and False for the VP bridge),
    so the external spool's ``vt_tray`` entries answer ``None`` -- they have no
    bit in the mask.
    """
    if not isinstance(tray, Mapping):
        return None
    exists = tray.get("exists")
    return exists if isinstance(exists, bool) else None


def _find_tray_in_ams_data(ams_data: list, ams_id: int, tray_id: int) -> dict | None:
    """Find a specific tray in the AMS data structure."""
    if not ams_data:
        return None
    for ams_unit in ams_data:
        if int(ams_unit.get("id", -1)) != ams_id:
            continue
        for tray in ams_unit.get("tray", []):
            if int(tray.get("id", -1)) == tray_id:
                return tray
    return None


def tray_for_slot(raw_data: Mapping, ams_id: int, tray_id: int) -> dict:
    """Read one live slot, including the external feeds' sentinel IDs."""
    if ams_id == 255:
        for tray in raw_data.get("vt_tray") or []:
            if isinstance(tray, dict) and int(tray.get("id", 254)) == tray_id + 254:
                return tray
        return {}
    ams = raw_data.get("ams", {})
    units = ams.get("ams", []) if isinstance(ams, dict) else ams if isinstance(ams, list) else []
    return _find_tray_in_ams_data(units, ams_id, tray_id) or {}


def unit_reported_absent(ams_id, ams_list: list, ams_exist_bits) -> bool:
    """Whether a push that doesn't list AMS unit ``ams_id`` says it is unplugged.

    ``ams_exist_bits`` (hex) has bit n set for AMS unit n, measured on an X1C
    (unit 1 -> "2", none -> "0") and an H2C (units 0, 1, 2 and HT 128 -> "17").
    So an AMS unit 0-3 whose bit is clear is gone. An empty unit list with no
    bits set means no unit at all, which is what the X1C sends with its AMS
    unplugged. Anything else is kept, as the merge always did: a partial push
    lists only some units, and the bits of an AMS HT or AMS Lite next to other
    units are not measured well enough to read.
    """
    if ams_exist_bits is None:
        return False
    try:
        bits = int(ams_exist_bits, 16) if isinstance(ams_exist_bits, str) else int(ams_exist_bits)
        unit = int(ams_id)
    except (TypeError, ValueError):
        return False
    if bits == 0 and not ams_list:
        return True
    return 0 <= unit <= 3 and not bits >> unit & 1


def attached_ams_units(existing_by_id: dict, ams_list: list, ams_data: object) -> list:
    """Merge completion: drop only units explicitly reported unplugged."""
    if isinstance(ams_data, dict):
        listed = {str(unit.get("id")) for unit in ams_list if isinstance(unit, dict)}
        for ams_id in list(existing_by_id):
            if str(ams_id) not in listed and unit_reported_absent(ams_id, ams_list, ams_data.get("ams_exist_bits")):
                del existing_by_id[ams_id]
    return sorted(existing_by_id.values(), key=lambda unit: int(unit.get("id", 0)))
