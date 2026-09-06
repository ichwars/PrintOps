"""Validate sidecar slice output before PrintOps stores or dispatches it."""

from __future__ import annotations

import io
import json
import logging
import zipfile

from backend.app.utils.archive_budget import ArchiveBudgetError, read_json_member

logger = logging.getLogger(__name__)

_PROJECT_SETTINGS = "Metadata/project_settings.config"
_START_GCODE_MARKER = "gcode_claim_action"
_GCODE_SCAN_BYTES = 4 * 1024 * 1024
_UNDEFINED_VENDOR = "(Undefined)"


def _as_text(value: object) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    return "" if value is None else str(value)


def _project_settings(content: bytes) -> dict | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            settings = read_json_member(archive, _PROJECT_SETTINGS)
    except (
        ArchiveBudgetError,
        KeyError,
        OSError,
        zipfile.BadZipFile,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        logger.debug("Slice output check skipped: cannot read %s (%s)", _PROJECT_SETTINGS, exc)
        return None
    return settings if isinstance(settings, dict) else None


def start_gcode_is_missing(content: bytes, *, export_3mf: bool) -> bool:
    """Return true only when output conclusively lacks Bambu start G-code."""
    if not content:
        return False
    if not export_3mf:
        head = content[:_GCODE_SCAN_BYTES].decode("utf-8", errors="ignore")
        return bool(head) and _START_GCODE_MARKER not in head
    settings = _project_settings(content)
    if settings is None or "machine_start_gcode" not in settings:
        return False
    return _START_GCODE_MARKER not in _as_text(settings["machine_start_gcode"])


def unresolved_filament_slots(content: bytes, *, export_3mf: bool) -> list[int]:
    """Return 1-indexed slots for which the slicer inherited no preset."""
    if not content or not export_3mf:
        return []
    settings = _project_settings(content)
    if settings is None:
        return []
    vendors = settings.get("filament_vendor")
    filament_ids = settings.get("filament_ids")
    if not isinstance(vendors, list) or not isinstance(filament_ids, list):
        return []
    return [
        index + 1
        for index, (vendor, filament_id) in enumerate(zip(vendors, filament_ids, strict=False))
        if _as_text(vendor).strip() == _UNDEFINED_VENDOR and not _as_text(filament_id).strip()
    ]


def missing_start_gcode_message(printer_preset_name: str) -> str:
    return (
        f"The slicer returned a file with no printer start G-code for '{printer_preset_name}'. "
        "Printing it would heat the printer and extrude nothing, so it was not saved. "
        "Update the slicer sidecar image and slice again; older images cannot resolve "
        "the companion profile containing the full start G-code."
    )


def unresolved_filament_message(slots: list[int], preset_names: list[str | None]) -> str:
    parts = []
    for slot in slots:
        name = preset_names[slot - 1] if slot <= len(preset_names) else ""
        parts.append(f"slot {slot} ({name})" if name else f"slot {slot}")
    return (
        f"The slicer could not resolve the filament preset for {', '.join(parts)} and silently "
        "substituted its built-in PLA defaults. The unsafe output was not saved. Install the latest "
        "slicer sidecar image or choose one of its bundled presets, then slice again."
    )


def slicer_output_error(
    content: bytes,
    *,
    export_3mf: bool,
    printer_preset_name: str | None,
    filament_preset_names: list[str | None],
) -> str | None:
    """Return a user-facing reason when a sidecar result is not print-ready."""
    if printer_preset_name and start_gcode_is_missing(content, export_3mf=export_3mf):
        return missing_start_gcode_message(printer_preset_name)
    unresolved = unresolved_filament_slots(content, export_3mf=export_3mf)
    unresolved_standard = [
        slot for slot in unresolved if slot <= len(filament_preset_names) and filament_preset_names[slot - 1]
    ]
    if unresolved_standard:
        return unresolved_filament_message(unresolved_standard, filament_preset_names)
    return None
