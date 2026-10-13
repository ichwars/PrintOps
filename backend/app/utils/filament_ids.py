"""Utility functions for converting between filament_id and setting_id formats, and shared filament constants.

Bambu printers use two ID formats for filament presets:
  - **filament_id** (aka tray_info_idx): e.g. "GFL05", "GFG02", "GFA00"
    Reported by printer firmware (RFID tags, AMS status).
  - **setting_id**: e.g. "GFSL05", "GFSG02", "GFSA00"
    Used by BambuStudio / Bambu Cloud API to resolve presets.

The only difference for official Bambu filaments is an "S" inserted after "GF".
User presets (starting with "P") use the same ID in both contexts.
"""

import re

from backend.app.utils.generic_filament_catalog import GENERIC_FILAMENT_IDS as GENERIC_FILAMENT_IDS

MATERIAL_TEMPS: dict[str, tuple[int, int]] = {
    "PLA": (190, 230),
    "PETG": (220, 260),
    "ABS": (240, 270),
    "ASA": (240, 270),
    "TPU": (200, 240),
    "PA": (260, 290),
    "PC": (250, 280),
    "PVA": (190, 210),
    "PLA-CF": (210, 240),
    "PETG-CF": (240, 270),
    "PA-CF": (270, 300),
}


def filament_id_to_setting_id(filament_id: str) -> str:
    """Convert filament_id → setting_id (e.g. "GFL05" → "GFSL05").

    - Already a setting_id ("GFS…") → returned unchanged.
    - User presets ("P…") → returned unchanged.
    - Empty / unknown → returned unchanged.
    """
    if not filament_id:
        return filament_id

    # User presets start with "P" - leave unchanged
    if filament_id.startswith("P"):
        return filament_id

    # Official Bambu presets: GFx## -> GFSx##
    if filament_id.startswith("GF") and len(filament_id) >= 4:
        # Already a setting_id (has S after GF)
        if re.fullmatch(r"GFS[A-Z]\d+(?:_\d+)?", filament_id):
            return filament_id
        return f"GFS{filament_id[2:]}"

    return filament_id


def setting_id_to_filament_id(setting_id: str) -> str:
    """Convert setting_id → filament_id (e.g. "GFSL05" → "GFL05").

    - Already a filament_id ("GF" without "S") → returned unchanged.
    - User presets ("P…") → returned unchanged.
    - Empty / unknown → returned unchanged.
    """
    if not setting_id:
        return setting_id

    # User presets start with "P" - leave unchanged
    if setting_id.startswith("P"):
        return setting_id

    # Setting_id format: GFSx## -> GFx##  (remove the "S")
    if re.fullmatch(r"GFS[A-Z]\d+(?:_\d+)?", setting_id):
        return f"GF{setting_id[3:]}"

    return setting_id


def normalize_slicer_filament(slicer_filament: str | None) -> tuple[str, str]:
    """Normalize a slicer_filament value into (tray_info_idx, setting_id).

    The slicer_filament field on a spool can be stored in either format:
      - filament_id: "GFL05"  (from RFID tag scan)
      - setting_id:  "GFSL05" or "GFSL05_07"  (from cloud preset picker)

    Returns (tray_info_idx, setting_id) with version suffixes stripped.
    """
    raw = slicer_filament or ""
    if not raw:
        return ("", "")

    # Strip version suffix (e.g. "GFSL05_07" → "GFSL05")
    base = raw.split("_")[0] if "_" in raw else raw

    tray_info_idx = setting_id_to_filament_id(base)
    sid = filament_id_to_setting_id(base)

    return (tray_info_idx, sid)
