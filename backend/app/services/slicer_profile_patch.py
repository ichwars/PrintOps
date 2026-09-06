"""Small, defensive patches applied to resolved slicer profiles."""

from __future__ import annotations

import io
import json
import logging
import zipfile

from backend.app.utils.archive_budget import ArchiveBudgetError, read_json_member
from backend.app.utils.threemf_tools import extract_project_filaments_from_3mf, supports_enabled_in_config

logger = logging.getLogger(__name__)

_SUPPORT_KEYS = (
    "enable_support",
    "support_filament",
    "support_interface_filament",
    "support_type",
)


def patch_process_support_settings(process_json: str, source_3mf_bytes: bytes) -> str:
    """Carry an enabled source 3MF support setup onto the chosen process.

    The carry is intentionally one-way: a source can enable supports, but it
    cannot disable supports already enabled by the explicitly chosen process.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(source_3mf_bytes), "r") as archive:
            if "Metadata/project_settings.config" not in archive.namelist():
                return process_json
            source = read_json_member(archive, "Metadata/project_settings.config")
    except (ArchiveBudgetError, zipfile.BadZipFile, ValueError, UnicodeDecodeError, OSError, KeyError):
        return process_json
    if not isinstance(source, dict) or not supports_enabled_in_config(source):
        return process_json

    try:
        process = json.loads(process_json)
    except json.JSONDecodeError:
        return process_json
    if not isinstance(process, dict):
        return process_json

    for key in _SUPPORT_KEYS:
        if key in source:
            process[key] = source[key]
    return json.dumps(process)


def _source_plate_colours(model_bytes: bytes) -> list[str]:
    """Return source-project colours in slot order, or an empty list."""
    try:
        with zipfile.ZipFile(io.BytesIO(model_bytes), "r") as archive:
            return [str(item.get("color") or "") for item in extract_project_filaments_from_3mf(archive)]
    except (ArchiveBudgetError, zipfile.BadZipFile, OSError, ValueError):
        return []


def _preset_default_colour(profile: dict) -> str:
    raw = profile.get("default_filament_colour")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return raw.strip() if isinstance(raw, str) else ""


def patch_filament_colours(filament_jsons: list[str], requested: list[str], model_bytes: bytes) -> list[str]:
    """Write the actual per-slot colour into each resolved filament profile.

    Priority is the caller's explicit colour, then the preset default, then
    the source project's colour. Invalid profile JSON remains untouched so
    the slicer can report the original profile error itself.
    """
    source_colours = _source_plate_colours(model_bytes) if filament_jsons else []
    patched: list[str] = []
    for index, raw in enumerate(filament_jsons):
        try:
            profile = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Filament colour skipped for slot %d: profile is not valid JSON", index + 1)
            patched.append(raw)
            continue
        if not isinstance(profile, dict):
            patched.append(raw)
            continue
        colour = (
            (requested[index].strip() if index < len(requested) and requested[index] else "")
            or _preset_default_colour(profile)
            or (source_colours[index].strip() if index < len(source_colours) and source_colours[index] else "")
        )
        if colour:
            profile["filament_colour"] = [colour]
            patched.append(json.dumps(profile))
        else:
            patched.append(raw)
    return patched
