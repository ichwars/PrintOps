"""Canonical library-file classification helpers."""

from pathlib import Path

from backend.app.utils.threemf_tools import carries_gcode


def classify_file_type(filename: str, file_path: Path | str | None = None) -> str:
    """Return the canonical library type, inspecting ambiguous 3MF files.

    Explicit ``.gcode.3mf`` names remain a compatibility signal. A plain
    ``.3mf`` is classified from its ZIP contents when a path is available so
    sliced exports remain printable regardless of their outer name (#132).
    """
    lower = filename.lower()
    if lower.endswith(".gcode.3mf"):
        return "gcode.3mf"
    suffix = Path(lower).suffix
    file_type = suffix[1:] if suffix else "unknown"
    if file_type == "3mf" and file_path is not None and carries_gcode(file_path):
        return "gcode.3mf"
    return file_type


def is_sliced_file(filename: str, file_type: str | None = None) -> bool:
    """Return whether a library file carries printable G-code.

    Content-derived ``file_type`` is authoritative for ambiguous ``.3mf``
    names. The filename remains a compatibility signal for legacy rows.
    """
    normalized_type = (file_type or "").lower()
    if normalized_type in ("gcode", "gcode.3mf"):
        return True
    lower = filename.lower()
    return lower.endswith(".gcode") or lower.endswith(".gcode.3mf")
