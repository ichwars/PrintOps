"""Slice persistence must leave the event loop free while producing thumbnails."""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.api.routes import library
from backend.app.schemas.slicer import SliceRequest
from backend.app.services.slicer_api import SliceResult


@pytest.mark.parametrize("sink", ["library", "archive"])
async def test_thumbnail_renderer_runs_in_worker_thread(sink, monkeypatch, tmp_path):
    loop_thread = threading.get_ident()
    render_thread = None

    class RenderProbe(Exception):
        pass

    def render(_payload):
        nonlocal render_thread
        render_thread = threading.get_ident()
        raise RenderProbe

    monkeypatch.setattr(library, "inject_plate_thumbnails_if_missing", render)
    monkeypatch.setattr(library, "get_library_files_dir", lambda: tmp_path)
    monkeypatch.setattr(library.app_settings, "base_dir", tmp_path)
    monkeypatch.setattr(library.app_settings, "archive_dir", tmp_path / "archive")
    monkeypatch.setattr(
        library,
        "_run_slicer_with_fallback",
        AsyncMock(return_value=(SliceResult(b"result", 0, 0.0, 0.0), False)),
    )
    kwargs = {
        "db": None,
        "model_bytes": b"source",
        "model_filename": "cube.3mf",
        "request": SliceRequest(printer_preset_id=1, process_preset_id=2, filament_preset_id=3),
        "current_user_id": None,
    }
    with pytest.raises(RenderProbe):
        if sink == "library":
            await library.slice_and_persist(**kwargs, folder_id=None, extra_metadata=None)
        else:
            await library.slice_and_persist_as_archive(**kwargs, source_archive=SimpleNamespace(printer_id=None))
    assert render_thread is not None
    assert render_thread != loop_thread
