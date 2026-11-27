"""Printer model normalization and model-specific safety utilities.

Converts 3MF printer model names (e.g., "Bambu Lab X1 Carbon") to
normalized short names (e.g., "X1C") that match database storage.
"""

import json

# Map from 3MF printer_model strings to normalized short names
PRINTER_MODEL_MAP = {
    "Bambu Lab X1 Carbon": "X1C",
    "Bambu Lab X1": "X1",
    "Bambu Lab X1E": "X1E",
    "Bambu Lab P1S": "P1S",
    "Bambu Lab P1P": "P1P",
    "Bambu Lab P2S": "P2S",
    "Bambu Lab A1": "A1",
    "Bambu Lab A1 Mini": "A1 Mini",
    "Bambu Lab A1 mini": "A1 Mini",
    # Bambu cloud rolled out a terse model-code rename mid-2026 (#1649);
    # 3MFs prepared with newer cloud presets may carry this short form.
    "Bambu Lab A1M": "A1 Mini",
    "Bambu Lab H2D": "H2D",
    "Bambu Lab H2D Pro": "H2D Pro",
    "Bambu Lab H2C": "H2C",
    "Bambu Lab H2S": "H2S",
    "Bambu Lab X2D": "X2D",
    "Bambu Lab A2L": "A2L",
    "Bambu Lab H3C": "H3C",
    "Bambu Lab P3C": "P3C",
}

# Map from printer_model_id (internal codes in slice_info.config) to short names
# These are the codes Bambu Studio uses internally
PRINTER_MODEL_ID_MAP = {
    # X1 series
    "BL-P001": "X1C",
    "BL-P002": "X1",
    "BL-P003": "X1E",
    "C13": "X1E",
    # P1 series
    "C11": "P1P",
    "C12": "P1S",
    "P1P": "P1P",
    "P1S": "P1S",
    # P2 series
    "P2S": "P2S",
    "N7": "P2S",  # Already recognized by STEEL_ROD_MODELS and MQTT capability gates.
    # X2 series
    "N6": "X2D",
    # A2 series (A2L is single-FDM + integrated cutter/plotter — single nozzle)
    "N9": "A2L",
    # A1 series
    "A11": "A1",
    "A12": "A1 Mini",
    "N1": "A1 Mini",
    "N2S": "A1",
    "A04": "A1 Mini",
    # H2 series (Office/H series)
    "O1D": "H2D",
    "O1E": "H2D Pro",  # Some devices report O1E
    "O2D": "H2D Pro",  # Some devices report O2D
    "O1C": "H2C",
    "O1C2": "H2C",
    "O1S": "H2S",
    # H3 series ("Bambu Lab H3C.json" model_id). One extruder with nine
    # nozzles in Studio's profile, so not in DUAL_NOZZLE_MODELS or
    # NOZZLE_RACK_MODELS: the H2C's rack ids and left/right split don't fit it.
    "N10": "H3C",
    # P3 series (Swaptek 7-tool changer, single extruder — not dual nozzle).
    "N11": "P3C",
}


# Rod/rail type classification for maintenance tasks.
# Carbon rods: X1, P1 series (CoreXY with carbon fiber rods — self-lubricating,
# must never be greased)
# Hollow steel rods: P2S, X2D, H3C, P3C series (steel linear rods/shafts)
# Linear rails: A1, H2 series (X-axis linear rail; the H2 series' Y axis runs
# on steel rods — see the H2-series Y-axis lubrication guide)
# Values must be uppercase with spaces stripped for normalized comparison.
CARBON_ROD_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "X1",
        "X1C",
        "X1E",
        "P1P",
        "P1S",
        # Internal codes
        "C11",  # P1P
        "C12",  # P1S
        "C13",  # X1E
    ]
)

STEEL_ROD_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "P2S",
        "X2D",
        "H3C",
        "P3C",
        # Internal codes
        "N7",  # P2S
        "N6",  # X2D
        "N10",  # H3C
        "N11",  # P3C
    ]
)

LINEAR_RAIL_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "A1",
        "A1MINI",
        "A2L",
        "H2D",
        "H2DPRO",
        "H2C",
        "H2S",
        # Internal codes
        "N1",  # A1 Mini
        "N2S",  # A1
        "N9",  # A2L
        "A04",  # A1 Mini (alternate)
        "A11",  # A1
        "A12",  # A1 Mini
        "O1D",  # H2D
        "O1E",  # H2D Pro
        "O2D",  # H2D Pro (alternate)
        "O1C",  # H2C
        "O1C2",  # H2C (dual nozzle variant)
        "O1S",  # H2S
    ]
)


# Models without any external storage (MicroSD / SD card slot) — they ship
# with built-in eMMC storage and a USB port instead (per the official spec
# sheets: P2S 8 GB, H2D/H2C/H2S/X2D 8 GB, H2D Pro 32 GB, H3C 64 GB, P3C 64 GB).
# The connection diagnostic's external_storage check (printer_diagnostic.py)
# must skip on these models instead of reporting fail from a 0-valued
# home_flag bit — these printers never surface a "store to external storage"
# toggle because there is no external storage to store to.
# The A1 family and A2L DO have a MicroSD slot (their only storage) — they
# are excluded from the toggle via has_remote_storage_toggle instead.
NO_EXTERNAL_STORAGE_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "P2S",
        "X2D",
        "H2D",
        "H2DPRO",
        "H2C",
        "H2S",
        "H3C",
        "P3C",
        # Internal codes
        "N7",  # P2S
        "N6",  # X2D
        "O1D",  # H2D
        "O1E",  # H2D Pro
        "O2D",  # H2D Pro (alternate)
        "O1C",  # H2C
        "O1C2",  # H2C (dual nozzle variant)
        "O1S",  # H2S
        "N10",  # H3C
        "N11",  # P3C
    ]
)


# Models with an ethernet port. Per the official spec sheets the RJ45 port
# exists only on the X1E (100 Mbps, enterprise) and the H2D Pro — X1, X1C,
# P1P, P1S, P2S, A1, A1 mini, A2L, H2D, H2C, H2S, X2D, H3C and P3C all list
# "Ethernet: Not available" and reach the network over Wi-Fi only.
ETHERNET_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "X1E",
        "H2DPRO",
        # Internal codes
        "C13",  # X1E
        "O1E",  # H2D Pro
        "O2D",  # H2D Pro (alternate)
    ]
)


# Dual-nozzle (dual-extruder) printers. Single source of truth for nozzle
# class — consumed by ``BambuMQTTClient.start_print``, the K-profile routes,
# and the re-slice nozzle-class guard (previously an inline model tuple
# duplicated across all three). Re-slicing a model laid out for a single-nozzle
# printer onto one of these — or vice versa — is not yet supported: the source
# 3MF's embedded single-nozzle filament/extruder layout is not a valid
# dual-nozzle project and BambuStudio's multi-extruder validator rejects it.
DUAL_NOZZLE_MODELS = frozenset(
    [
        # Display names (uppercase, no spaces)
        "H2D",
        "H2DPRO",
        "H2C",
        "X2D",
        # Internal codes
        "O1D",  # H2D
        "O1E",  # H2D Pro
        "O2D",  # H2D Pro (alternate)
        "O1C",  # H2C
        "O1C2",  # H2C (dual nozzle variant)
        "N6",  # X2D
    ]
)


# Deliberately empty until a raw H2C model code and minimum firmware have been
# validated on real hardware against native Bambu Studio dispatches (#126).
# Adding a code here is the explicit release step; display name or nozzle count
# alone must never enable physical rack IDs.
H2C_NOZZLE_MAPPING_MIN_FIRMWARE: dict[str, str] = {}


def validate_h2c_nozzle_mapping(raw: object) -> tuple[list[int] | None, str | None]:
    """Parse only unambiguous physical H2C nozzle mappings.

    Native payloads observed by the project use flat 8- or 32-element arrays.
    ``-1`` means unused, ``1`` is the fixed carriage and ``16..21`` are rack
    positions. Compact logical maps, nested/multi-group data and unknown IDs
    are rejected so they cannot be mistaken for physical wire identifiers.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, "unparseable_json"
    if not isinstance(raw, list):
        return None, "not_a_flat_list"
    if len(raw) not in {8, 32}:
        return None, "unsupported_length"
    if any(isinstance(value, bool) or not isinstance(value, int) for value in raw):
        return None, "non_integer_or_grouped_value"
    allowed_ids = {-1, 1, *range(16, 22)}
    if any(value not in allowed_ids for value in raw):
        return None, "logical_or_unknown_physical_id"
    if all(value == -1 for value in raw):
        return None, "empty_mapping"
    return list(raw), None


def h2c_nozzle_mapping_capability(
    display_model: str | None,
    raw_model_code: str | None,
    firmware_version: str | None,
) -> tuple[bool, str]:
    """Return whether physical H2C rack IDs have explicit hardware evidence."""
    normalized_display = (display_model or "").strip().upper().replace(" ", "")
    normalized_code = (raw_model_code or "").strip().upper()
    if normalized_display != "H2C":
        return False, "not_h2c"
    if normalized_code not in {"O1C", "O1C2"}:
        return False, "missing_or_unknown_raw_model_code"
    minimum = H2C_NOZZLE_MAPPING_MIN_FIRMWARE.get(normalized_code)
    if minimum is None:
        return False, "raw_model_code_not_hardware_validated"
    if not firmware_version:
        return False, "firmware_unknown"

    def _version_tuple(value: str) -> tuple[int, ...] | None:
        try:
            return tuple(int(part) for part in value.split("."))
        except ValueError:
            return None

    current = _version_tuple(firmware_version)
    required = _version_tuple(minimum)
    if current is None or required is None:
        return False, "firmware_unparseable"
    if current < required:
        return False, "firmware_below_validated_boundary"
    return True, "validated"


SINGLE_NOZZLE_FLOW_MODELS = frozenset(
    [
        "A1",
        "A1MINI",
        "A2L",
        "P3C",
        "N1",
        "N2S",
        "N9",
        "A04",
        "A11",
        "A12",
        "N11",
    ]
)


def has_ethernet(model: str | None) -> bool:
    """Return True if the printer model has an ethernet port."""
    if not model:
        return False
    normalized = (normalize_printer_model_id(model.strip().upper()) or model).upper().replace(" ", "").replace("-", "")
    return normalized in ETHERNET_MODELS


def has_remote_storage_toggle(model: str | None) -> bool:
    """Whether the printer or slicer exposes the remote-storage option.

    False for models whose only storage IS the card (P1P/P1S, A1 family,
    A2L): sent files land on the MicroSD unconditionally, the option never
    surfaces, and home_flag bit 11 is never set (#1703, #3499).
    """
    normalized = (model or "").strip().upper().replace(" ", "").replace("-", "")
    return normalized not in {
        "P1S",
        "P1P",
        "C11",
        "C12",
        "A2L",
        "N9",
        "A1",
        "A1MINI",
        "N1",
        "N2S",
        "A04",
        "A11",
        "A12",
    }


def has_external_storage(model: str | None) -> bool:
    """Return True if the printer model can have a MicroSD / external storage slot.

    Defaults to True when the model is unknown — the diagnostic only flips
    its check on for the explicit no-storage list. New models added to the
    Bambu lineup without a slot must be added to ``NO_EXTERNAL_STORAGE_MODELS``
    or the diagnostic will continue to evaluate ``store_to_sdcard`` against
    a hardware feature the printer doesn't have.
    """
    if not model:
        return True
    normalized = (normalize_printer_model_id(model.strip().upper()) or model).upper().replace(" ", "").replace("-", "")
    return normalized not in NO_EXTERNAL_STORAGE_MODELS


# Chamber heater / airduct coupling: the H3C's heater lives inside the
# adaptive-airflow unit and only heats with the damper in heating mode (in
# cooling mode the H3C acks M141 and stays off). The H2 series follows the
# same coupling policy — its firmware auto-switches the damper to heating
# mode whenever a chamber target is set (support_chamber_temp_switch_heating
# is 40 on N10/O1D/O1S/O1C/N6 alike) — so on stock firmware neither heats in
# cooling mode; the H3C just needs the explicit flip at dispatch.
CHAMBER_HEATER_NEEDS_HEATING_MODE_MODELS = frozenset(["H3C", "N10"])

# `mc_percent` counts the start sequence (an H3C is at ~20% on layer 0), so a
# stopped print is charged by layers instead (usage_progress).
PROGRESS_INCLUDES_START_SEQUENCE_MODELS = frozenset(["H3C", "N10"])

AMS3H_MODELS = frozenset(["H3C", "N10"])


def _model_key(model: str | None) -> str:
    return model.strip().upper().replace(" ", "").replace("-", "") if isinstance(model, str) else ""


def progress_includes_start_sequence(model: str | None) -> bool:
    """True when the printer's progress percent counts its start sequence (H3C)."""
    return _model_key(model) in PROGRESS_INCLUDES_START_SEQUENCE_MODELS


def has_ams3h(model: str | None) -> bool:
    """True for a model that comes with an AMS 3H (H3C)."""
    return _model_key(model) in AMS3H_MODELS


def usage_progress(
    model: str | None,
    progress: float | int | None,
    layer_num: int | None,
    total_layers: int | None,
) -> float | int:
    """How much of a stopped print was printed, in percent, for charging its filament.

    The printer's own progress, except on a model whose progress counts the
    start sequence: there the share of layers printed (0 before layer 1).
    """
    if not progress_includes_start_sequence(model):
        return progress if progress is not None else 0.0
    if layer_num and layer_num > 0 and total_layers and total_layers > 0:
        return min(100.0, 100.0 * layer_num / total_layers)
    return 0.0


def chamber_heater_needs_heating_mode(model: str | None) -> bool:
    """True when a chamber target only takes effect with the airduct in heating mode (H3C)."""
    return _model_key(model) in CHAMBER_HEATER_NEEDS_HEATING_MODE_MODELS


def is_dual_nozzle_model(model: str | None) -> bool:
    """Return True if the printer model has two nozzles (H2D family / X2D)."""
    if not model:
        return False
    normalized = (normalize_printer_model_id(model.strip().upper()) or model).upper().replace(" ", "").replace("-", "")
    return normalized in DUAL_NOZZLE_MODELS


def supports_nozzle_flow_type(model: str | None) -> bool:
    """Return whether the model offers Standard and High Flow nozzles."""
    if not model:
        return True
    normalized = (normalize_printer_model_id(model.strip().upper()) or model).upper().replace(" ", "").replace("-", "")
    return normalized not in SINGLE_NOZZLE_FLOW_MODELS


GCODE_COMPAT_FAMILIES = (frozenset(["X1", "X1C", "X1E", "P1P", "P1S"]),)


def is_gcode_compatible(sliced_for_model: str | None, target_model: str | None) -> bool:
    """Return True when sliced G-code may be dispatched to the target model.

    Missing metadata stays compatible for legacy/unknown files. Known mismatches
    are exact-match only, except the proven X1/P1 CoreXY single-nozzle family.
    """
    if not sliced_for_model or not target_model:
        return True

    def _norm(model: str) -> str:
        resolved = normalize_printer_model(model) or model
        resolved = normalize_printer_model_id(resolved) or resolved
        return resolved.strip().upper().replace(" ", "").replace("-", "")

    sliced = _norm(sliced_for_model)
    target = _norm(target_model)
    if sliced == target:
        return True
    return any(sliced in family and target in family for family in GCODE_COMPAT_FAMILIES)


def get_rod_type(model: str | None) -> str | None:
    """Return the rod/rail type for a printer model.

    Returns:
        "carbon" for X1/P1 series (carbon fiber rods),
        "steel_rod" for P2S/X2D/H3C/P3C series (steel linear rods),
        "linear_rail" for A1/H2 series (X-axis linear rail),
        None for unknown models.
    """
    if not model:
        return None
    normalized = (normalize_printer_model_id(model.strip().upper()) or model).upper().replace(" ", "").replace("-", "")
    if normalized in CARBON_ROD_MODELS:
        return "carbon"
    if normalized in STEEL_ROD_MODELS:
        return "steel_rod"
    if normalized in LINEAR_RAIL_MODELS:
        return "linear_rail"
    return None


def normalize_printer_model_id(model_id: str | None) -> str | None:
    """Convert printer_model_id (internal code) to normalized short name.

    Args:
        model_id: The printer_model_id from slice_info.config (e.g., "C11", "O1D")

    Returns:
        Normalized short name (e.g., "P1P", "H2D") or the original ID if unknown.
    """
    if not model_id:
        return None

    # Codes are shared by 3MF metadata and SSDP discovery.
    resolved = PRINTER_MODEL_ID_MAP.get(model_id.strip().upper())
    if resolved:
        return resolved

    # Return original if unknown (might already be a short name)
    return model_id


def normalize_printer_model(raw_model: str | None) -> str | None:
    """Convert 3MF printer_model to normalized short name.

    Args:
        raw_model: The printer_model string from 3MF metadata
            (e.g., "Bambu Lab X1 Carbon")

    Returns:
        Normalized short name (e.g., "X1C") or None if input is empty.
        Unknown models have "Bambu Lab " prefix stripped.
    """
    if not raw_model:
        return None

    # Check known mappings first
    if raw_model in PRINTER_MODEL_MAP:
        return PRINTER_MODEL_MAP[raw_model]

    # Strip "Bambu Lab " prefix for unknown models
    stripped = raw_model.replace("Bambu Lab ", "").strip()
    return stripped or None


LEGACY_RFID_REFRESH_MODELS = frozenset(["X1", "X1C", "X1E", "P1P", "P1S", "A1", "A1MINI"])


def uses_legacy_rfid_refresh(model: str | None) -> bool:
    """Only known old-protocol models support the M620 R RFID fallback."""
    if not model:
        return False
    short = normalize_printer_model_id(model) or model
    return short.strip().upper().replace(" ", "") in LEGACY_RFID_REFRESH_MODELS


def aux_fan_sides(model: str | None) -> tuple[str, str]:
    """Part 2 is left on X2D; part 10 is left on P2S."""
    normalized = (model or "").strip().upper().replace(" ", "").replace("-", "")
    return ("left", "right") if normalized in {"X2D", "N6"} else ("right", "left")


def uses_exhaust_fan_label(model: str | None) -> bool:
    """Whether fan 3 is labeled "Exhaust" rather than "Chamber".

    BambuStudio's machine profiles rename fan 3 to "Chamber" only on the
    X1, X1C, X1E and P1S; every other model (P1P, P2S, X2D, H2 series, H3C,
    P3C) ships with the default "Exhaust" label.
    """
    normalized = (model or "").strip().upper().replace(" ", "").replace("-", "")
    return normalized not in {"X1", "X1C", "X1E", "P1S", "BLP001", "BLP002", "C12", "C13"}
