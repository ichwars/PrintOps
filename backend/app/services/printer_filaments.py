from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol


class PrinterLike(Protocol):
    id: int


class PrinterStatusLike(Protocol):
    raw_data: dict[str, Any]


def _tray_color(value: Any) -> tuple[str, str]:
    stripped = str(value or "808080").replace("#", "")
    rgb = stripped[:6].lower() or "808080"
    return f"#{stripped}", rgb


def _filament_entry(
    tray: dict[str, Any],
    *,
    tray_type: str,
    extruder_id: int | None,
) -> dict[str, Any]:
    color, _rgb = _tray_color(tray.get("tray_color", "") or "808080")
    return {
        "type": tray_type,
        "color": color,
        "tray_info_idx": tray.get("tray_info_idx", ""),
        "tray_sub_brands": tray.get("tray_sub_brands", "") or "",
        "extruder_id": extruder_id,
    }


def _dedup_key(tray: dict[str, Any], tray_type: str, extruder_id: int | None) -> tuple[str, str, str, int | None]:
    _color, rgb = _tray_color(tray.get("tray_color", "") or "808080")
    return (
        tray_type.upper(),
        rgb,
        str(tray.get("tray_sub_brands", "") or "").upper(),
        extruder_id,
    )


def collect_available_filaments(
    printers: Iterable[PrinterLike],
    get_status: Callable[[int], PrinterStatusLike | None],
) -> list[dict[str, Any]]:
    """Collect deduplicated loaded filament choices for model-based queue assignment."""
    seen: set[tuple[str, str, str, int | None]] = set()
    filaments: list[dict[str, Any]] = []

    def add_tray(tray: dict[str, Any], extruder_id: int | None) -> None:
        tray_type = tray.get("tray_type")
        if not tray_type:
            return
        key = _dedup_key(tray, str(tray_type), extruder_id)
        if key in seen:
            return
        seen.add(key)
        filaments.append(_filament_entry(tray, tray_type=str(tray_type), extruder_id=extruder_id))

    for printer in printers:
        status = get_status(printer.id)
        if status is None:
            continue
        raw_data = status.raw_data or {}
        ams_extruder_map = raw_data.get("ams_extruder_map", {})

        for ams_unit in raw_data.get("ams", []):
            ams_id = str(ams_unit.get("id", 0))
            extruder_id = ams_extruder_map.get(ams_id)
            for tray in ams_unit.get("tray", []):
                add_tray(tray, extruder_id)

        for vt in raw_data.get("vt_tray") or []:
            vt_id = int(vt.get("id", 254))
            extruder_id = (255 - vt_id) if ams_extruder_map else None
            add_tray(vt, extruder_id)

    return filaments
