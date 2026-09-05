"""Evidence checks for matching a running print to a candidate 3MF."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from backend.app.utils.archive_budget import ArchiveBudgetError, validate_zip_archive

_GENERIC_PLATE_STEM = re.compile(r"^plate_?\d+$", re.IGNORECASE)


def like_escape(value: str) -> str:
    """Escape SQL LIKE metacharacters so model names match literally."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def threemf_search_stem(*candidates: str | None) -> str | None:
    """Return the first candidate that identifies a model rather than a plate."""

    for raw in candidates:
        if not raw:
            continue
        stem = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
        for suffix in (".gcode.3mf", ".gcode", ".3mf"):
            if stem.casefold().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        probe = stem.strip()
        if probe and not _GENERIC_PLATE_STEM.fullmatch(probe):
            return stem
    return None


def normalized_model_name(value: str | None) -> str | None:
    stem = threemf_search_stem(value)
    if stem is None:
        return None
    return re.sub(r"[\s_-]+", "_", stem.strip().casefold())


def stem_matches(column: Any, stem: str):
    """Build a literal, basename- and extension-anchored 3MF match."""

    escaped = like_escape(stem)
    bare = column.ilike(f"{escaped}.3mf", escape="\\") | column.ilike(f"{escaped}.gcode.3mf", escape="\\")
    nested = column.ilike(f"%/{escaped}.3mf", escape="\\") | column.ilike(f"%/{escaped}.gcode.3mf", escape="\\")
    return bare | nested


def expected_plate_from_paths(*paths: str | None) -> int | None:
    from backend.app.services.printer_manager import parse_plate_id

    for path in paths:
        plate = parse_plate_id(path)
        if plate is not None:
            return plate
    return None


def expected_filament_slots(ams_mapping: list | None) -> set[int] | None:
    """Return unambiguous project filament slots named by an AMS mapping."""

    if not isinstance(ams_mapping, list):
        return None
    slots: set[int] = set()
    for index, target in enumerate(ams_mapping):
        if isinstance(target, bool):
            continue
        try:
            target_id = int(target)
        except (TypeError, ValueError):
            continue
        if target_id >= 0 and target_id != 65535:
            slots.add(index + 1)
    return slots or None


def candidate_3mf_conflict(
    candidate: Path,
    *,
    expected_plate: int | None,
    ams_mapping: list | None,
) -> str | None:
    """Explain positive evidence that *candidate* belongs to another print."""

    from backend.app.services.archive import plate_indexes_in_3mf
    from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf

    try:
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            return "the file is not a readable 3MF"
        with zipfile.ZipFile(candidate, "r") as archive:
            names = {info.filename.replace("\\", "/") for info in validate_zip_archive(archive)}
            has_print_data = "Metadata/slice_info.config" in names or any(
                re.fullmatch(r"Metadata/plate_\d+\.gcode", name) for name in names
            )
            if not has_print_data:
                return "the file contains no recognizable 3MF print data"
    except (ArchiveBudgetError, OSError, zipfile.BadZipFile):
        return "the file is not readable"

    plates = plate_indexes_in_3mf(candidate)
    known_plates = [plate for plate in plates if plate is not None]
    if expected_plate is not None and plates and len(known_plates) == len(plates):
        if expected_plate not in known_plates:
            return f"the file has no plate {expected_plate}"

    expected_slots = expected_filament_slots(ams_mapping)
    if expected_slots is not None and expected_plate is not None:
        usage = extract_filament_usage_from_3mf(candidate, expected_plate)
        candidate_slots: set[int] = set()
        for row in usage:
            try:
                if row.get("slot_id") is not None and float(row.get("used_g") or 0) > 0:
                    candidate_slots.add(int(row["slot_id"]))
            except (TypeError, ValueError):
                continue
        if candidate_slots and not candidate_slots.issubset(expected_slots):
            return f"filament slots {sorted(candidate_slots)} contradict the print mapping {sorted(expected_slots)}"
    return None
