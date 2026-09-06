"""Resolve chamber preheat targets from the trays a print actually uses."""

import json
from collections.abc import Mapping

_EXTERNAL_TRAY_ID_MIN = 254


def normalize_filament_type(tray_type: str | None) -> str:
    """Return the filament-map key reported by Bambu tray telemetry."""
    return tray_type.split()[0].upper() if tray_type else ""


def _int_or(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _global_tray_id(ams_id: int, tray_id: int) -> int:
    """Mirror the global IDs produced by scheduler AMS mapping."""
    return ams_id if ams_id >= 128 else ams_id * 4 + tray_id


def _used_global_tray_ids(mapping_raw: object) -> set[int] | None:
    """Return mapped tray IDs, or ``None`` when the mapping is unusable."""
    if not mapping_raw:
        return None
    if isinstance(mapping_raw, str):
        try:
            mapping = json.loads(mapping_raw)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        mapping = mapping_raw
    if not isinstance(mapping, list):
        return None
    used = {tray for tray in mapping if isinstance(tray, int) and not isinstance(tray, bool) and tray >= 0}
    return used or None


def _target_for_type(tray_type: object, targets: Mapping[str, int]) -> int:
    normalized = normalize_filament_type(tray_type if isinstance(tray_type, str) else None)
    if not normalized:
        return 0
    return targets.get(normalized, targets.get("DEFAULT", targets.get("default", 0)))


def derive_chamber_target(
    raw_data: object,
    targets: Mapping[str, int],
    mapping_raw: object = None,
) -> int:
    """Find the maximum target among the mapped AMS or external trays.

    Missing or unusable mappings conservatively retain the previous behavior:
    all loaded AMS trays are considered, while external trays are considered
    only when the print mapping names them explicitly.
    """
    if not isinstance(raw_data, dict):
        return 0

    used = _used_global_tray_ids(mapping_raw)
    ams_entries = raw_data.get("ams")
    if isinstance(ams_entries, dict):
        ams_entries = ams_entries.get("ams") or []
    if not isinstance(ams_entries, list):
        ams_entries = []

    best = 0
    for ams in ams_entries:
        if not isinstance(ams, dict):
            continue
        ams_id = _int_or(ams.get("id"), 0)
        trays = ams.get("tray") or []
        if not isinstance(trays, list):
            continue
        for tray in trays:
            if not isinstance(tray, dict):
                continue
            tray_id = _global_tray_id(ams_id, _int_or(tray.get("id"), 0))
            if used is not None and tray_id not in used:
                continue
            best = max(best, _target_for_type(tray.get("tray_type"), targets))

    if used is None or not any(tray_id >= _EXTERNAL_TRAY_ID_MIN for tray_id in used):
        return best

    virtual_trays = raw_data.get("vt_tray") or []
    if isinstance(virtual_trays, dict):
        virtual_trays = [virtual_trays]
    if not isinstance(virtual_trays, list):
        return best
    for tray in virtual_trays:
        if not isinstance(tray, dict):
            continue
        if _int_or(tray.get("id"), _EXTERNAL_TRAY_ID_MIN) not in used:
            continue
        best = max(best, _target_for_type(tray.get("tray_type"), targets))
    return best
