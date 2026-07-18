from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

import defusedxml.ElementTree as ET

from backend.app.services.calculation_estimator import BoundsMm, PlateGeometry
from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf, extract_print_time_from_3mf

MAX_METADATA_BYTES = 24 * 1024 * 1024


class InvalidProjectFile(ValueError):
    pass


@dataclass(frozen=True)
class PlateAnalysis:
    plate_index: int
    stable_key: str
    name: str
    geometry: PlateGeometry
    detected_materials: tuple[dict[str, object], ...]
    detected_grams: Decimal | None
    detected_hours: Decimal | None
    thumbnail_bytes: bytes | None

    @property
    def object_count(self) -> int:
        return self.geometry.object_count


@dataclass(frozen=True)
class ProjectFileAnalysis:
    printer_metadata: dict[str, object]
    plates: tuple[PlateAnalysis, ...]


def _safe_members(archive: ZipFile) -> set[str]:
    names: set[str] = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise InvalidProjectFile("3MF archive contains an unsafe path")
        if info.filename.startswith("Metadata/") and info.file_size > MAX_METADATA_BYTES:
            raise InvalidProjectFile("3MF metadata file exceeds the safety limit")
        names.add(info.filename)
    return names


def _metadata(element, key: str) -> str | None:
    for item in element.findall("metadata"):
        if item.get("key") == key:
            return item.get("value")
    return None


def analyze_project_file(path: Path) -> ProjectFileAnalysis:
    try:
        with ZipFile(path, "r") as archive:
            names = _safe_members(archive)
            if "Metadata/slice_info.config" not in names:
                raise InvalidProjectFile("3MF has no plate metadata")
            raw_slice_info = archive.read("Metadata/slice_info.config")
            if len(raw_slice_info) > MAX_METADATA_BYTES:
                raise InvalidProjectFile("3MF plate metadata exceeds the safety limit")
            root = ET.fromstring(raw_slice_info)
            printer_metadata: dict[str, object] = {}
            if "Metadata/project_settings.config" in names:
                try:
                    settings = json.loads(archive.read("Metadata/project_settings.config"))
                    if isinstance(settings, dict):
                        printer_metadata = {
                            key: settings[key]
                            for key in ("printer_model", "printer_settings_id", "print_settings_id")
                            if key in settings
                        }
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

            plates: list[PlateAnalysis] = []
            for ordinal, plate_element in enumerate(root.findall(".//plate"), start=1):
                try:
                    plate_index = int(_metadata(plate_element, "index") or ordinal)
                except ValueError:
                    plate_index = ordinal
                name = _metadata(plate_element, "name") or f"Platte {plate_index}"
                object_ids = sorted(
                    {
                        value
                        for obj in plate_element.findall(".//object")
                        if (value := (obj.get("identify_id") or obj.get("id") or obj.get("object_id")))
                    }
                )
                materials = tuple(extract_filament_usage_from_3mf(path, plate_index))
                grams = sum((Decimal(str(item.get("used_g", 0))) for item in materials), Decimal("0"))
                seconds = extract_print_time_from_3mf(path, plate_index)
                stable_payload = json.dumps(
                    {"plate_index": plate_index, "object_ids": object_ids, "name": name.strip()},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                thumbnail_name = f"Metadata/plate_{plate_index}.png"
                thumbnail = archive.read(thumbnail_name) if thumbnail_name in names else None
                geometry = PlateGeometry(
                    object_count=len(object_ids),
                    triangle_count=0,
                    volume_cm3=Decimal("0"),
                    bounds_mm=BoundsMm(Decimal("0"), Decimal("0"), Decimal("0")),
                )
                plates.append(
                    PlateAnalysis(
                        plate_index=plate_index,
                        stable_key=hashlib.sha256(stable_payload.encode()).hexdigest(),
                        name=name,
                        geometry=geometry,
                        detected_materials=materials,
                        detected_grams=grams if materials else None,
                        detected_hours=Decimal(seconds) / Decimal("3600") if seconds is not None else None,
                        thumbnail_bytes=thumbnail,
                    )
                )
            if not plates:
                raise InvalidProjectFile("3MF contains no project plates")
            return ProjectFileAnalysis(printer_metadata=printer_metadata, plates=tuple(plates))
    except BadZipFile as exc:
        raise InvalidProjectFile("File is not a valid 3MF archive") from exc
