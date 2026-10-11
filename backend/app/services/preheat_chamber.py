"""Resolve chamber preheat targets from the trays a print actually uses."""

import json
import math
from collections.abc import Mapping

from backend.app.core.config import settings
from backend.app.utils.threemf_tools import extract_bed_temperature_from_3mf, extract_filament_usage_from_3mf

_EXTERNAL_TRAY_ID_MIN = 254


def normalize_filament_type(tray_type: str | None) -> str:
    """Return the filament-map key reported by Bambu tray telemetry."""
    parts = tray_type.split() if isinstance(tray_type, str) else []
    return parts[0].upper() if parts else ""


def observed_tray_materials(raw_data: object) -> dict[int, str]:
    """Use the same explicit AMS/HT/external identities for preheat and holds."""
    if not isinstance(raw_data, dict):
        return {}
    entries = raw_data.get("ams", [])
    if isinstance(entries, dict):
        entries = entries.get("ams", [])
    trays = {}
    if not isinstance(entries, list):
        return trays
    for ams in entries:
        if not isinstance(ams, dict):
            continue
        try:
            ams_id = int(ams.get("id", 0))
            for tray in ams.get("tray", []):
                tray_id = int(tray.get("id", 0))
                global_id = ams_id if ams_id >= 128 else ams_id * 4 + tray_id
                trays[global_id] = normalize_filament_type(tray.get("tray_type"))
        except (TypeError, ValueError, AttributeError):
            return {}
    external = raw_data.get("vt_tray", [])
    if isinstance(external, dict):
        external = [external]
    if not isinstance(external, list):
        return {}
    for tray in external:
        if not isinstance(tray, dict):
            return {}
        try:
            identity = int(tray.get("id", 254))
        except (TypeError, ValueError):
            return {}
        if identity >= 254:
            trays[identity] = normalize_filament_type(tray.get("tray_type"))
    return trays


def chamber_target_for_plate(state, targets, item, archive) -> int | None:
    """Refuse ambiguous plates/mappings instead of considering parked material."""
    path_raw = getattr(archive, "file_path", None)
    if not path_raw or state is None:
        return None
    plate_id = getattr(item, "plate_id", None)
    if plate_id is not None and (not isinstance(plate_id, int) or isinstance(plate_id, bool) or plate_id < 1):
        return None
    path = settings.base_dir / path_raw
    if plate_id is None and extract_bed_temperature_from_3mf(path) is None:
        return None  # An implicit plate is safe only when the file proves one plate.
    mapping = getattr(item, "ams_mapping", None)
    if isinstance(mapping, str):
        try:
            mapping = json.loads(mapping)
        except (ValueError, TypeError):
            return None
    if not isinstance(mapping, list):
        return None
    materials = observed_tray_materials(getattr(state, "raw_data", None))
    used = []
    for filament in extract_filament_usage_from_3mf(path, plate_id):
        amount = filament["used_g"]
        if not math.isfinite(amount) or amount < 0:
            return None
        if amount == 0:
            continue
        slot = filament["slot_id"]
        if not 1 <= slot <= len(mapping):
            return None
        mapped = mapping[slot - 1]
        if (
            not isinstance(mapped, int)
            or isinstance(mapped, bool)
            or mapped < 0
            or (not getattr(item, "use_ams", True) and mapped < _EXTERNAL_TRAY_ID_MIN)
            or not materials.get(mapped)
        ):
            return None
        used.append(mapped)
    return derive_chamber_target(state.raw_data, targets, used) if used else None


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

    Missing or unusable mappings skip automatic chamber heating; loaded trays
    alone are not evidence that this print will consume their material.
    """
    if not isinstance(raw_data, dict):
        return 0

    used = _used_global_tray_ids(mapping_raw)
    if used is None:
        return 0
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
