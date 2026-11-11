"""Printer removal preserves history while discarding that printer's live state."""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.api.routes import camera, printers
from backend.app.core.config import settings
from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.archive import PrintArchive
from backend.app.models.pipeline_run import PipelineJob, PipelineRun
from backend.app.models.slicer_pipeline import SlicerPipeline
from backend.app.services import kprofile_drift, usage_tracker
from backend.app.services.print_scheduler import scheduler

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_delete_printer_releases_only_its_live_state_and_keeps_archives(
    async_client, db_session, printer_factory, monkeypatch, tmp_path
):
    from backend.app import main

    removed = await printer_factory()
    other = await printer_factory()
    archive = PrintArchive(printer_id=removed.id, filename="fixture.3mf", file_path="/unused", file_size=1)
    db_session.add(archive)
    await db_session.flush()
    pipeline = SlicerPipeline(
        name="Targeted pipeline",
        printer_preset_source="local",
        printer_preset_id="printer",
        process_preset_source="local",
        process_preset_id="process",
        filament_presets_json="[]",
        target_kind="specific_printer",
        target_printer_id=removed.id,
    )
    db_session.add(pipeline)
    await db_session.flush()
    run = PipelineRun(pipeline_id=pipeline.id, status="completed")
    db_session.add(run)
    await db_session.flush()
    job = PipelineJob(pipeline_run_id=run.id, assigned_printer_id=removed.id, status="completed")
    db_session.add_all(
        [
            ActivePrintSession(printer_id=removed.id, started_at=datetime.now(timezone.utc).replace(tzinfo=None)),
            ActivePrintSession(printer_id=other.id, started_at=datetime.now(timezone.utc).replace(tzinfo=None)),
            ActivePrintSpoolman(printer_id=removed.id, archive_id=archive.id, ams_trays={}),
            ActivePrintSpoolman(printer_id=other.id, archive_id=archive.id, ams_trays={}),
            job,
        ]
    )
    await db_session.commit()
    removed_id, other_id = removed.id, other.id

    monkeypatch.setattr(
        main, "_active_prints", {(removed_id, "fixture"): archive.id, (other_id, "fixture"): archive.id}
    )
    monkeypatch.setattr(main, "_print_ams_mappings", {(removed_id, archive.id): [2], (other_id, archive.id): [4]})
    monkeypatch.setattr(main, "_last_progress_milestone", {removed_id: 40, other_id: 60})
    monkeypatch.setattr(
        printers.printer_manager, "_current_print_user", {removed_id: {"user_id": 7}, other_id: {"user_id": 8}}
    )
    monkeypatch.setattr(printers.printer_manager, "_awaiting_plate_clear", {removed_id, other_id})
    monkeypatch.setattr(usage_tracker, "_active_sessions", {removed_id: object(), other_id: object()})
    monkeypatch.setattr(camera, "_last_frames", {removed_id: b"old", other_id: b"other"})
    monkeypatch.setattr(scheduler, "_upload_backoff", {removed_id: 42, other_id: 43})
    monkeypatch.setattr(kprofile_drift, "_default_chosen", {(removed_id, 0, 0), (other_id, 0, 0)})
    offline = asyncio.create_task(asyncio.Event().wait())
    monkeypatch.setattr(main, "_printer_offline_notify_tasks", {removed_id: offline})
    monkeypatch.setattr(settings, "plate_calibration_dir", tmp_path)
    removed_image = tmp_path / f"printer_{removed_id}_ref_0.jpg"
    removed_meta = tmp_path / f"printer_{removed_id}_metadata.json"
    other_image = tmp_path / f"printer_{other_id}_ref_0.jpg"
    for path in (removed_image, removed_meta, other_image):
        path.write_bytes(b"fixture")

    try:
        response = await async_client.delete(f"/api/v1/printers/{removed_id}", params={"delete_archives": "false"})
        assert response.status_code == 200
        await db_session.refresh(archive)
        await db_session.refresh(pipeline)
        await db_session.refresh(job)
        assert archive.printer_id is None
        assert pipeline.target_printer_id is None
        assert job.assigned_printer_id is None
        assert job.status == "completed"
        assert list(await db_session.scalars(select(ActivePrintSession.printer_id))) == [other_id]
        assert list(await db_session.scalars(select(ActivePrintSpoolman.printer_id))) == [other_id]
        assert main._active_prints == {(other_id, "fixture"): archive.id}
        assert main._print_ams_mappings == {(other_id, archive.id): [4]}
        assert main._last_progress_milestone == {other_id: 60}
        assert printers.printer_manager.get_current_print_user(removed_id) is None
        assert not printers.printer_manager.is_awaiting_plate_clear(removed_id)
        assert printers.printer_manager.is_awaiting_plate_clear(other_id)
        assert set(usage_tracker._active_sessions) == {other_id}
        assert camera._last_frames == {other_id: b"other"}
        assert scheduler._upload_backoff == {other_id: 43}
        assert kprofile_drift._default_chosen == {(other_id, 0, 0)}
        assert offline.cancelled()
        assert not removed_image.exists() and not removed_meta.exists()
        assert other_image.read_bytes() == b"fixture"
    finally:
        if not offline.done():
            offline.cancel()
            await asyncio.gather(offline, return_exceptions=True)


async def test_create_printer_removes_preexisting_plate_files_for_its_id(async_client, monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(settings, "plate_calibration_dir", tmp_path)
    monkeypatch.setattr(printers.printer_manager, "test_connection", AsyncMock(return_value={"success": True}))
    stale = tmp_path / "printer_1_ref_0.jpg"
    unrelated = tmp_path / "printer_2_ref_0.jpg"
    stale.write_bytes(b"stale")
    unrelated.write_bytes(b"other")

    response = await async_client.post(
        "/api/v1/printers/",
        json={
            "name": "New printer",
            "serial_number": "TEST0001",
            "ip_address": "192.0.2.21",
            "access_code": "test-fixture",
            "model": "X1C",
            "is_active": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert not stale.exists()
    assert unrelated.read_bytes() == b"other"
