"""Shared, bounded G-code responses after callers enforce ownership."""

import re
import zipfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from backend.app.utils.archive_budget import ArchiveBudgetError, read_zip_member, validate_zip_archive

_PLATE_NAME = re.compile(r"(?:^|/)plate_(\d+)\.gcode$")


def select_preview_member(names: list[str], plate: int | None) -> str | None:
    """Choose the lowest numbered plate by default; explicit choices must exist."""
    gcode_names = sorted(name for name in names if name.endswith(".gcode"))
    numbered = []
    for name in gcode_names:
        match = _PLATE_NAME.search(name)
        if match and (number := int(match.group(1))) > 0:
            numbered.append((number, name))
    if plate is not None:
        return next((name for number, name in numbered if number == plate), None)
    if numbered:
        return min(numbered)[1]
    return gcode_names[0] if gcode_names else None


def gcode_preview_response(path: Path, *, zipped: bool, plate: int | None):
    """Serve one requested plate while preserving ZIP resource limits."""
    if plate is not None and plate < 1:
        raise HTTPException(400, "Plate index must be >= 1")
    if not zipped:
        if plate not in (None, 1):
            raise HTTPException(404, f"Plate {plate} not found in this file")
        return FileResponse(str(path), media_type="text/plain")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            validate_zip_archive(archive)
            selected = select_preview_member(archive.namelist(), plate)
            if selected is None:
                detail = f"Plate {plate} not found in this file" if plate is not None else "No G-code found in 3MF file"
                raise HTTPException(404, detail)
            return Response(content=read_zip_member(archive, selected), media_type="text/plain")
    except (ArchiveBudgetError, zipfile.BadZipFile):
        raise HTTPException(400, "Invalid 3MF file")
