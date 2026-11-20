"""Summarize manufacturer faults for print history and notifications."""

# Earlier code matched on `module` alone (e.g. "any module 0x0C HMS → Layer shift"),
# which is wrong on two counts:
#   1. Real layer-shift codes live in module 0x03 (see Bambu wiki), not 0x0C.
#   2. Module 0x0C is "Motion Controller" — broad category that also covers cameras
#      and visual markers, AND the H2D firmware emits a 0x0C HMS (0C00_001B, not in
#      the public wiki) as part of its user-cancel sequence. Matching on the module
#      alone caused user-cancellations to be archived as "Layer shift" failures.
# We now match by full short code only — anything not in this map leaves
# failure_reason=None rather than guessing.
_HMS_FAILURE_REASONS: dict[str, str] = {
    # Layer shift / step loss
    "0300_4057": "Layer shift",
    "0300_4068": "Layer shift",
    "0300_800C": "Layer shift",
    # Filament runout (printer-side & per-AMS-slot)
    "0300_8004": "Filament runout",
    "0700_8011": "Filament runout",
    "0701_8011": "Filament runout",
    "0702_8011": "Filament runout",
    "0703_8011": "Filament runout",
    "0704_8011": "Filament runout",
    "0705_8011": "Filament runout",
    "0706_8011": "Filament runout",
    "0707_8011": "Filament runout",
    "07FF_8011": "Filament runout",
    # Clogged nozzle / extruder
    "0300_4006": "Clogged nozzle",
    "0300_8016": "Clogged nozzle",
    "0300_801C": "Clogged nozzle",
    "0700_8003": "Clogged nozzle",
    "0700_8007": "Clogged nozzle",
    "0700_8013": "Clogged nozzle",
    "0701_8003": "Clogged nozzle",
    "0701_8007": "Clogged nozzle",
    "0701_8013": "Clogged nozzle",
    "0702_8003": "Clogged nozzle",
}


def _hms_short_code(attr: int, code: int | str) -> str:
    """Build the canonical "MMMM_CCCC" HMS short code from raw attr/code values."""
    if isinstance(code, str):
        code_int = int(code.replace("0x", ""), 16) if code else 0
    else:
        code_int = int(code or 0)
    attr_int = int(attr or 0)
    return f"{(attr_int >> 16) & 0xFFFF:04X}_{code_int & 0xFFFF:04X}"


def derive_failure_reason(status: str, hms_errors: list[dict] | None) -> str | None:
    """Derive a human-readable failure_reason for an archived print.

    Returns "User cancelled" for cancelled/aborted prints; for failed prints,
    returns the first matching reason from _HMS_FAILURE_REASONS, or None when
    no HMS code matches (don't guess — null is honest).
    """
    if status in ("aborted", "cancelled"):
        return "User cancelled"
    if status != "failed":
        return None
    for err in hms_errors or []:
        short_code = _hms_short_code(err.get("attr", 0), err.get("code", 0))
        if short_code in _HMS_FAILURE_REASONS:
            return _HMS_FAILURE_REASONS[short_code]
    return None


_HMS_MODULE_NAMES = {
    0x03: "Print/Task",  # bed, nozzle temperatures, motors, the print itself
    0x05: "System",  # USB/SD, network, firmware, files, AMS communication
    0x07: "AMS/Filament",
    0x08: "Toolhead",
    0x0C: "Camera",  # cameras, lidar, first-layer and AI inspection
    0x12: "AMS Lite",
    0x18: "AMS-HT",
    0x1A: "Tool Changer",
    0x29: "Air Filter",
    0x2A: "AMS 3H",
}


def _hms_error_title(module: int) -> str:
    """The notification title for a fault of *module*."""
    name = _HMS_MODULE_NAMES.get(module)
    return f"{name} Error" if name else "Printer Error"


def _format_hms_error_summary(hms_errors: list[dict]) -> str | None:
    """Build a human-readable failure reason from MQTT hms_errors for PrintQueueItem.error_message.

    Current payloads carry the resolved manufacturer description and full code.
    Historical payloads without those fields keep their print_error short-code
    lookup. A 64-bit HMS code never borrows text from the 32-bit keyspace.
    Unknown faults retain their code; an empty list returns None.
    """
    if not hms_errors:
        return None
    from backend.app.services.hms_errors import describe_fault, get_error_description

    parts: list[str] = []
    for err in hms_errors:
        try:
            code_str = str(err.get("code", "")).replace("0x", "")
            error_num = int(code_str, 16) if code_str else 0
            module_num = (int(err.get("attr", 0)) >> 16) & 0xFFFF
            short_code = f"{module_num:04X}_{error_num:04X}"
        except (TypeError, ValueError):
            continue
        full_code = err.get("full_code") or ""
        if "description" in err:
            description = err["description"]
        elif full_code:
            description = describe_fault(full_code)
        else:
            description = get_error_description(short_code)
        display_code = (
            "-".join(full_code[index : index + 4] for index in range(0, 16, 4)) if len(full_code) == 16 else short_code
        )
        parts.append(f"[{display_code}] {description}" if description else f"[{display_code}]")
    return "; ".join(parts) if parts else None
