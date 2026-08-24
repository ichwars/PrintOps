"""Single source of truth for which model formats the slicer sidecar accepts.

STEP/STP are deliberately absent: the OrcaSlicer/BambuStudio CLI behind the
sidecar cannot import them reliably, so offering a server-side slice for a
STEP file only produces a job that fails minutes later. Uploading, storing and
previewing STEP files stays supported — see issue #92.
"""

from __future__ import annotations

# Model geometry inputs the sidecar can slice. `.gcode.3mf` also matches here
# on purpose: re-slicing an already-sliced 3MF is a supported flow.
SERVER_SLICEABLE_EXTENSIONS: tuple[str, ...] = (".stl", ".3mf")

# Formats we accept for upload/library management but cannot slice server-side.
UNSLICEABLE_CAD_EXTENSIONS: tuple[str, ...] = (".step", ".stp")

SLICEABLE_FORMATS_LABEL = "STL or 3MF"


def is_server_sliceable_filename(filename: str | None) -> bool:
    """Return True when ``filename`` can be fed to the slicer sidecar."""
    return (filename or "").lower().endswith(SERVER_SLICEABLE_EXTENSIONS)


def is_unsliceable_cad_filename(filename: str | None) -> bool:
    """Return True for CAD formats we store but cannot slice (STEP/STP)."""
    return (filename or "").lower().endswith(UNSLICEABLE_CAD_EXTENSIONS)


def unsliceable_detail(filename: str | None, *, subject: str = "Source file") -> str:
    """Human-readable 400 detail explaining why a slice was refused."""
    if is_unsliceable_cad_filename(filename):
        return (
            f"{subject} is a STEP/STP file, which the slicer sidecar cannot "
            "process. Convert it to STL or 3MF and slice that instead."
        )
    return f"{subject} must be {SLICEABLE_FORMATS_LABEL} to slice"
