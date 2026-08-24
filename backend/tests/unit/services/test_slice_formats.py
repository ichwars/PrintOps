"""Format boundary for server-side slicing (#92).

STEP/STP stay uploadable and manageable in the library, but the slicer
sidecar cannot import them — so the slice capability check must reject them.
"""

from __future__ import annotations

import pytest

from backend.app.services.slice_formats import (
    is_server_sliceable_filename,
    is_unsliceable_cad_filename,
    unsliceable_detail,
)


@pytest.mark.unit
@pytest.mark.parametrize("filename", ["bracket.stl", "Bracket.STL", "plate.3mf", "benchy.gcode.3mf"])
def test_sliceable_formats_accepted(filename):
    assert is_server_sliceable_filename(filename) is True


@pytest.mark.unit
@pytest.mark.parametrize("filename", ["flange.step", "flange.STEP", "flange.stp", "flange.Stp"])
def test_step_rejected(filename):
    assert is_server_sliceable_filename(filename) is False
    assert is_unsliceable_cad_filename(filename) is True


@pytest.mark.unit
@pytest.mark.parametrize("filename", ["notes.txt", "part.obj", "", None])
def test_other_formats_rejected(filename):
    assert is_server_sliceable_filename(filename) is False
    assert is_unsliceable_cad_filename(filename) is False


@pytest.mark.unit
def test_detail_explains_step_limitation():
    detail = unsliceable_detail("flange.step")
    assert "STEP/STP" in detail
    assert "STL or 3MF" in detail


@pytest.mark.unit
def test_detail_falls_back_to_generic_message():
    detail = unsliceable_detail("notes.txt", subject="Archive's source file")
    assert detail == "Archive's source file must be STL or 3MF to slice"
