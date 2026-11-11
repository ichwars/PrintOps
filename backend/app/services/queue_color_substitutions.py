"""Describe colour differences in the AMS mapping sent for a print."""

import re
from collections.abc import Callable


def reported_rgb(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
        rgba = value.removeprefix("#").upper()
        if rgba != "00000000":
            return f"#{rgba[:6]}"
    return None


def find_color_substitutions(
    required: list[dict],
    mapping: list[int],
    loaded: list[dict],
    colors_are_similar: Callable[[str, str], bool],
) -> list[dict]:
    by_tray = {entry["global_tray_id"]: entry for entry in loaded}
    substitutions = []
    for requirement in required:
        slot = requirement.get("slot_id")
        if type(slot) is not int or not 1 <= slot <= len(mapping):
            continue
        tray_id = mapping[slot - 1]
        tray = by_tray.get(tray_id) if type(tray_id) is int else None
        if not tray:
            continue
        wanted = reported_rgb(requirement.get("color"))
        actual = tray.get("reported_color")
        if wanted and actual and wanted != actual and not colors_are_similar(wanted, actual):
            substitutions.append(
                {
                    "slot_id": slot,
                    "type": requirement.get("type") or "",
                    "wanted": wanted,
                    "got": actual,
                    "tray": tray_id,
                }
            )
    return substitutions
