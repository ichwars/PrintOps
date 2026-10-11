"""Resolve calibration references only within a reported nozzle context.

The calibration query is scoped to diameter, not the whole printer. Hotend
and flow are fields of individual entries; a calibration index is not global.
H2 nozzle array ordering is not reliable enough to infer a physical hotend.
"""

import math
from dataclasses import dataclass

from backend.app.utils.calibration_values import diameter, flow_type

_SINGLE_NOZZLE_MODELS = frozenset(
    {
        "X1",
        "X1C",
        "X1E",
        "BLP001",
        "C11",
        "C12",
        "C13",
        "P1P",
        "P1S",
        "P2S",
        "N7",
        "A1",
        "A1MINI",
        "A1M",
        "A2L",
        "N9",
        "N1",
        "N2S",
        "A04",
        "A11",
        "A12",
    }
)


@dataclass(frozen=True)
class CalibrationContext:
    extruder: int
    diameter: str
    flow: str | None


def slot_context(state, model, ams_id, tray_id) -> CalibrationContext | None:
    """Known single nozzle + reported diameter; unknown/multi hotends are gated.

    Existing H2 fields use conflicting left/right and extruder numbering. Do
    not guess that mapping, even if both diameters happen to be equal.
    """
    if state is None or not isinstance(model, str):
        return None
    compact = model.strip().upper().replace(" ", "").replace("-", "")
    if compact not in _SINGLE_NOZZLE_MODELS:
        return None
    nozzles = getattr(state, "nozzles", None)
    if not isinstance(nozzles, (list, tuple)) or not nozzles:
        return None
    if any(diameter(getattr(n, "nozzle_diameter", None)) for n in nozzles[1:]):
        return None
    mapping = getattr(state, "ams_extruder_map", None)
    if isinstance(mapping, dict) and mapping.get(str(ams_id), 0) not in (0, None):
        return None
    rack = getattr(state, "nozzle_rack", None)
    if rack and (
        not isinstance(rack, list) or len(rack) != 1 or not isinstance(rack[0], dict) or rack[0].get("id") != 0
    ):
        return None
    size = diameter(getattr(nozzles[0], "nozzle_diameter", None))
    if size is None:
        return None
    return CalibrationContext(0, size, flow_type(getattr(nozzles[0], "nozzle_type", None)))


def _compatible(profile, context, *, stored=False):
    size = diameter(getattr(profile, "nozzle_diameter", None))
    extruder = getattr(profile, "extruder" if stored else "extruder_id", None)
    flow = flow_type(getattr(profile, "nozzle_type" if stored else "nozzle_id", None))
    # NULL extruder is a legacy single-nozzle row; no physical multi-hotend
    # context ever reaches this resolver. Unknown flow matches unknown only.
    return size == context.diameter and extruder in (context.extruder, None) and flow == context.flow


def cached_profile(state, context, index, filament_id=None):
    """Return a unique compatible entry, never a bare-index fallback."""
    if context is None or not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return None
    entries = getattr(state, "kprofiles", None)
    if not isinstance(entries, (list, tuple)):
        return None
    candidates = [p for p in entries if getattr(p, "slot_id", None) == index and _compatible(p, context)]
    if filament_id and len(candidates) > 1:
        candidates = [p for p in candidates if p.filament_id == filament_id]
    return candidates[0] if len(candidates) == 1 else None


def resolve_spool_calibration(profiles, state, model, printer_id, ams_id, tray_id):
    """Shared manual/RFID/Spoolman rule with a narrowly scoped legacy fallback.

    Legacy references remain usable only on a known single-nozzle machine with
    an explicit diameter, unknown flow on both sides, and exactly one matching
    stored row. Once any live table was received, its contents are authoritative:
    an absent/deleted/ambiguous calibration must never fall back to a stored id.
    """
    context = slot_context(state, model, ams_id, tray_id)
    if context is None:
        return context, None, None
    candidates = [
        p
        for p in profiles
        if p.printer_id == printer_id
        and getattr(p, "cali_idx", None) is not None
        and _compatible(p, context, stored=True)
    ]
    if len(candidates) != 1:
        return context, None, None
    stored = candidates[0]
    live = cached_profile(state, context, stored.cali_idx)
    if live is not None:
        return context, stored, live
    entries = getattr(state, "kprofiles", None)
    scopes = getattr(state, "kprofile_diameters", None)
    if context.flow is None and isinstance(entries, (list, tuple)) and not entries and not scopes:
        return context, stored, None
    return context, None, None


def slot_k_value(state, model, ams_id, tray_id, index, filament_id=None):
    profile = cached_profile(state, slot_context(state, model, ams_id, tray_id), index, filament_id)
    if profile is None:
        return None
    try:
        value = float(profile.k_value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def store_profile_table(state, profiles, response_nozzle):
    """Replace only a response's authoritative diameter scope.

    A diameter response contains all its hotend/flow entries; retain those
    contexts separately in the flat list, and preserve all other diameters.
    An unattributable empty reply cannot clear any table.
    """
    size = diameter(response_nozzle)
    scopes = {size} if size else {diameter(p.nozzle_diameter) for p in profiles}
    scopes.discard(None)
    if not scopes:
        return
    previous = [p for p in state.kprofiles if diameter(p.nozzle_diameter) not in scopes]
    state.kprofiles = previous + [p for p in profiles if diameter(p.nozzle_diameter) in scopes]
    state.kprofile_diameters.update(scopes)


def apply_rfid_calibration(client, profiles, state, model, printer_id, ams_id, tray_id, filament_id, current_index):
    """Apply the same scoped selection on RFID assignment and drift correction."""
    from backend.app.services.kprofile_drift import default_chosen
    from backend.app.utils.filament_ids import normalize_slicer_filament

    if default_chosen(printer_id, ams_id, tray_id):
        return
    context, stored, live = resolve_spool_calibration(profiles, state, model, printer_id, ams_id, tray_id)
    if context is None:
        return
    index = stored.cali_idx if stored is not None else -1
    if current_index == index:
        return
    if live is not None and live.filament_id:
        filament_id = live.filament_id
    elif stored is not None and stored.setting_id:
        filament_id = normalize_slicer_filament(stored.setting_id)[0] or stored.setting_id
    client.extrusion_cali_sel(
        ams_id=ams_id, tray_id=tray_id, cali_idx=index, filament_id=filament_id, nozzle_diameter=context.diameter
    )
