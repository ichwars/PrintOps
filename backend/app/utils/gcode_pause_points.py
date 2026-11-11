"""Read scheduled pauses from the active plate of a sliced 3MF."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from backend.app.utils.threemf_tools import (
    MAX_GCODE_LAYER_NUMBER,
    MAX_GCODE_LINE_LENGTH,
    MAX_GCODE_LINES,
    _layer_gcode_member,
    validate_zip_archive,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PausePoint:
    layer: int
    remaining_minutes: int | None


def _parse_pause_points(lines: Iterable[bytes]) -> tuple[PausePoint, ...]:
    points: dict[int, PausePoint] = {}
    layer = 0
    remaining = None
    for number, raw in enumerate(lines, 1):
        if number > MAX_GCODE_LINES or len(raw) > MAX_GCODE_LINE_LENGTH:
            return ()
        line = raw.lstrip()
        if not line.startswith((b"M73", b"M400", b"m73", b"m400")):
            continue
        command, *parameters = line.split(b";", 1)[0].upper().split()
        if command == b"M73":
            for parameter in parameters:
                value = parameter[1:]
                if len(value) > 8 or not value.isdigit():
                    continue
                if parameter.startswith(b"L") and int(value) <= MAX_GCODE_LAYER_NUMBER:
                    layer = int(value)
                elif parameter.startswith(b"R"):
                    remaining = int(value)
        elif command == b"M400" and b"U1" in parameters and layer > 0:
            points.setdefault(layer, PausePoint(layer, remaining))
    return tuple(points[layer] for layer in sorted(points))


def extract_pause_points(path: Path, plate_id: int | None) -> tuple[PausePoint, ...]:
    try:
        with ZipFile(path) as archive:
            validate_zip_archive(archive)
            names = archive.namelist()
            if plate_id is None and sum(name.endswith(".gcode") for name in names) != 1:
                return ()
            member = _layer_gcode_member(names, plate_id)
            if member is None:
                return ()
            with archive.open(member) as gcode:
                return _parse_pause_points(iter(lambda: gcode.readline(MAX_GCODE_LINE_LENGTH + 1), b""))
    except (BadZipFile, OSError, RuntimeError, ValueError, NotImplementedError):
        logger.debug("Could not read scheduled print pauses", exc_info=True)
        return ()
