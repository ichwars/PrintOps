from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from backend.app.services.ams_slot_presence import spool_present
from backend.app.services.printer_nozzle_evidence import reports_two_nozzles
from backend.app.services.queue_color_substitutions import reported_rgb


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
            extruder_id = (255 - vt_id) if reports_two_nozzles(status) else None
            add_tray(vt, extruder_id)

    return filaments


def build_loaded_filaments(status, normalize_color) -> list[dict]:
    """Build list of loaded filaments from printer status.

    Args:
        status: PrinterState from printer_manager

    Returns:
        List of loaded filament dicts with type, color, ams_id, tray_id, global_tray_id
    """
    filaments = []

    # Get ams_extruder_map for dual-nozzle printers (H2D, H2D Pro)
    ams_extruder_map = status.raw_data.get("ams_extruder_map", {})

    # Parse AMS units from raw_data
    ams_data = status.raw_data.get("ams", [])
    for ams_unit in ams_data:
        ams_id = int(ams_unit.get("id", 0))
        trays = ams_unit.get("tray", [])
        is_ht = 128 <= ams_id <= 135

        for tray in trays:
            tray_type = tray.get("tray_type")
            if tray_type:
                tray_id = int(tray.get("id", 0))
                tray_color = tray.get("tray_color", "")
                # tray_info_idx identifies the specific spool (e.g., "GFA00", "P4d64437")
                tray_info_idx = tray.get("tray_info_idx", "")
                # Normalize color: remove alpha, add hash
                color = normalize_color(tray_color)
                # Calculate global tray ID
                # AMS-HT units have IDs starting at 128 with a single tray
                global_tray_id = ams_id if ams_id >= 128 else ams_id * 4 + tray_id

                filaments.append(
                    {
                        "type": tray_type,
                        "color": color,
                        "reported_color": reported_rgb(tray_color) if spool_present(tray) is not False else None,
                        "tray_info_idx": tray_info_idx,
                        "ams_id": ams_id,
                        "tray_id": tray_id,
                        "is_ht": is_ht,
                        "is_external": False,
                        "global_tray_id": global_tray_id,
                        "extruder_id": ams_extruder_map.get(str(ams_id)),
                        "remain": tray.get("remain", -1),
                    }
                )

    # Check external spool(s) (vt_tray is a list)
    for idx, vt in enumerate(status.raw_data.get("vt_tray") or []):
        if vt.get("tray_type"):
            color = normalize_color(vt.get("tray_color", ""))
            tray_id = int(vt.get("id", 254))
            filaments.append(
                {
                    "type": vt["tray_type"],
                    "color": color,
                    "reported_color": reported_rgb(vt.get("tray_color")),
                    "tray_info_idx": vt.get("tray_info_idx", ""),
                    "ams_id": -1,
                    "tray_id": idx,
                    "is_ht": False,
                    "is_external": True,
                    "global_tray_id": tray_id,
                    "extruder_id": (255 - tray_id) if reports_two_nozzles(status) else None,
                    "remain": vt.get("remain", -1),
                }
            )

    return filaments
