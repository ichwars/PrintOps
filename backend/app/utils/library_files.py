"""Canonical library-file classification helpers."""

from pathlib import Path

from backend.app.utils.threemf_tools import inspect_3mf_gcode


def classify_file_type(filename: str, file_path: Path | str | None = None) -> str:
    """Classify readable 3MFs by content and fall back to the name otherwise."""
    lower = filename.lower()
    if lower.endswith(".3mf"):
        has_gcode = inspect_3mf_gcode(file_path) if file_path is not None else None
        if has_gcode is None:
            has_gcode = lower.endswith(".gcode.3mf")
        return "gcode.3mf" if has_gcode else "3mf"
    suffix = Path(lower).suffix
    return suffix[1:] if suffix else "unknown"


def is_sliced_file(filename: str, file_type: str | None = None) -> bool:
    """Return whether a library file carries printable G-code.

    The stored 3MF type takes precedence. Rows without a recognized type
    still support the filename convention.
    """
    normalized_type = (file_type or "").lower()
    if normalized_type in ("gcode", "gcode.3mf"):
        return True
    if normalized_type == "3mf":
        return False
    lower = filename.lower()
    return lower.endswith(".gcode") or lower.endswith(".gcode.3mf")
