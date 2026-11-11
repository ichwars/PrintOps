"""Resolve the source plate and printer-specific reprint metadata before queueing."""

import json
import re
import zipfile
from pathlib import Path

from sqlalchemy import func, select

from backend.app.models.printer import Printer
from backend.app.utils.threemf_tools import default_plate_number


def store_slicer_ams_mapping(archive, printer_id: int, mapping: list[int], plate_ids: list[int]) -> None:
    archive.extra_data = {
        **(archive.extra_data or {}),
        "slicer_ams_mapping": {"printer_id": printer_id, "mapping": mapping, "plate_ids": plate_ids},
    }


def saved_slicer_ams_mapping(archive, printer_id: int | None, plate_id: int | None = None) -> str | None:
    if archive is None or not archive.extra_data or printer_id is None:
        return None
    saved = archive.extra_data.get("slicer_ams_mapping")
    if (
        isinstance(saved, dict)
        and saved.get("printer_id") == printer_id
        and isinstance(saved.get("mapping"), list)
        and saved["mapping"]
    ):
        plates = saved.get("plate_ids")
        if plates is None or (isinstance(plates, list) and (plate_id or archive.plate_id or 1) in plates):
            return json.dumps(saved["mapping"])
    return None


def printed_plate_of_multi_plate_file(file_path: Path | None) -> int | None:
    if file_path is None or not file_path.name.lower().endswith(".3mf") or not file_path.is_file():
        return None
    try:
        with zipfile.ZipFile(file_path) as zf:
            plates = [name for name in zf.namelist() if re.fullmatch(r"Metadata/plate_[1-9]\d*\.gcode", name)]
            return default_plate_number(plates) if len(plates) > 1 else None
    except (OSError, zipfile.BadZipFile):
        return None


async def active_printer_model(db, model: str, printer_ids: set[int] | None = None) -> str | None:
    query = select(Printer.model).where(func.lower(Printer.model) == model.lower(), Printer.is_active.is_(True))
    if printer_ids is not None:
        query = query.where(Printer.id.in_(printer_ids))
    return await db.scalar(query.order_by(Printer.id).limit(1))
