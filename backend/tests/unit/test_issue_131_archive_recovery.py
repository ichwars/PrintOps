"""Regression coverage for safe fallback archive and timelapse recovery (#131)."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_log import PrintLogEntry
from backend.app.services.fallback_archive_recovery import (
    _cached_3mf_filename,
    fallback_print_time,
    try_recover_fallback_archive,
)
from backend.app.services.threemf_identity import candidate_3mf_conflict, normalized_model_name
from backend.app.services.timelapse_archive import baseline_state, read_baseline_state
from backend.app.utils.print_jobs import is_internal_printer_job


def _make_3mf(path: Path, *, plate: int = 1, slot: int = 1) -> None:
    config = (
        f'<config><plate><metadata key="index" value="{plate}"/>'
        f'<filament id="{slot}" used_g="12.5" type="PLA" color="#FFFFFF"/>'
        "</plate></config>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/slice_info.config", config)
        archive.writestr(f"Metadata/plate_{plate}.gcode", "G28\n")


def test_internal_job_matching_is_exact():
    assert is_internal_printer_job(None, "pa_line_calib_mode")
    assert is_internal_printer_job("/usr/etc/print/anything.gcode", "anything")
    assert not is_internal_printer_job("pa_line_calib_mode_v2.3mf", None)
    assert not is_internal_printer_job("customer_pa_line_calib_mode.3mf", None)


def test_generic_plate_name_does_not_identify_a_model():
    assert normalized_model_name("/data/Metadata/plate_1.gcode") is None
    assert normalized_model_name("Widget - Plate 1.3mf") == "widget_plate_1"


def test_candidate_rejects_wrong_plate_and_filament_mapping(tmp_path):
    candidate = tmp_path / "Widget.3mf"
    _make_3mf(candidate, plate=2, slot=2)

    assert "no plate 1" in candidate_3mf_conflict(candidate, expected_plate=1, ams_mapping=[0])
    assert "filament slots" in candidate_3mf_conflict(candidate, expected_plate=2, ams_mapping=[0])
    assert candidate_3mf_conflict(candidate, expected_plate=2, ams_mapping=[-1, 4]) is None
    assert candidate_3mf_conflict(candidate, expected_plate=2, ams_mapping=[0, 4, 65535]) is None


def test_candidate_rejects_generic_zip_without_3mf_data(tmp_path):
    candidate = tmp_path / "not-a-model.3mf"
    with zipfile.ZipFile(candidate, "w") as archive:
        archive.writestr("notes.txt", "not a 3MF")

    assert "no recognizable 3MF" in candidate_3mf_conflict(candidate, expected_plate=None, ams_mapping=None)


def test_cached_alias_gets_safe_3mf_filename():
    assert _cached_3mf_filename("Widget") == "Widget.gcode.3mf"
    assert _cached_3mf_filename("/data/Widget.gcode") == "Widget.gcode.3mf"
    assert _cached_3mf_filename(r"C:\\prints\\Widget.3MF") == "Widget.3MF"


def test_fallback_print_time_ignores_malformed_raw_data():
    assert fallback_print_time({"raw_data": "not-a-dict"}) is None


@pytest.mark.asyncio
async def test_later_3mf_completes_same_row_and_preserves_history(
    db_session,
    printer_factory,
    tmp_path,
    monkeypatch,
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    printer = await printer_factory()
    started = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    fallback = PrintArchive(
        printer_id=printer.id,
        project_id=77,
        created_by_id=88,
        filename="Widget.3mf",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        started_at=started,
        filament_used_grams=9.5,
        cost=1.25,
        energy_kwh=0.42,
        notes="keep me",
        extra_data={"no_3mf_available": True, "business": "keep", "_print_data": {}},
    )
    db_session.add(fallback)
    await db_session.commit()
    await db_session.refresh(fallback)
    original_id = fallback.id
    log = PrintLogEntry(
        archive_id=original_id,
        printer_id=printer.id,
        print_name="Widget",
        status="completed",
        filament_used_grams=9.5,
        cost=1.25,
    )
    db_session.add(log)
    await db_session.commit()

    candidate = tmp_path / "Widget.3mf"
    _make_3mf(candidate)
    with patch(
        "backend.app.services.fallback_archive_recovery.ws_manager.send_archive_updated",
        new_callable=AsyncMock,
    ):
        recovered = await try_recover_fallback_archive(db_session, printer.id, "Widget.3mf", candidate)
        repeated = await try_recover_fallback_archive(db_session, printer.id, "Widget.3mf", candidate)

    assert recovered is not None and recovered.id == original_id
    assert repeated is None
    await db_session.refresh(fallback)
    assert fallback.status == "printing"
    assert fallback.started_at.replace(tzinfo=timezone.utc) == started
    assert fallback.project_id == 77 and fallback.created_by_id == 88
    assert fallback.filament_used_grams == 9.5 and fallback.cost == 1.25
    assert fallback.energy_kwh == 0.42 and fallback.notes == "keep me"
    assert fallback.file_path.endswith("Widget.3mf")
    assert fallback.extra_data["business"] == "keep"
    assert fallback.extra_data["recovered_no_3mf"] is True
    assert "no_3mf_available" not in fallback.extra_data
    assert await db_session.scalar(select(func.count(PrintArchive.id))) == 1
    assert await db_session.scalar(select(PrintLogEntry.archive_id).where(PrintLogEntry.id == log.id)) == original_id


@pytest.mark.asyncio
async def test_same_name_wrong_plate_does_not_complete_fallback(
    db_session,
    printer_factory,
    tmp_path,
):
    printer = await printer_factory()
    fallback = PrintArchive(
        printer_id=printer.id,
        filename="Widget.3mf",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        extra_data={"_print_data": {"filename": "/data/Metadata/plate_2.gcode"}},
    )
    db_session.add(fallback)
    await db_session.commit()
    candidate = tmp_path / "Widget.3mf"
    _make_3mf(candidate, plate=1)

    recovered = await try_recover_fallback_archive(db_session, printer.id, "Widget.3mf", candidate)

    assert recovered is None
    await db_session.refresh(fallback)
    assert fallback.file_path == ""


@pytest.mark.asyncio
async def test_session_without_mapping_uses_stored_mapping_evidence(
    db_session,
    printer_factory,
    tmp_path,
):
    printer = await printer_factory()
    fallback = PrintArchive(
        printer_id=printer.id,
        filename="Widget.3mf",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        extra_data={"_print_data": {"ams_mapping": [0]}},
    )
    db_session.add(fallback)
    db_session.add(
        ActivePrintSession(
            printer_id=printer.id,
            print_name="Widget",
            started_at=datetime.now(timezone.utc),
            tray_now_at_start=-1,
            plate_id=1,
            ams_mapping=None,
        )
    )
    await db_session.commit()
    candidate = tmp_path / "Widget.3mf"
    _make_3mf(candidate, plate=1, slot=2)

    recovered = await try_recover_fallback_archive(db_session, printer.id, "Widget.3mf", candidate)

    assert recovered is None
    await db_session.refresh(fallback)
    assert fallback.file_path == ""


@pytest.mark.asyncio
async def test_usage_fallback_rejects_same_name_from_another_plate(
    db_session,
    printer_factory,
    tmp_path,
):
    from backend.app.services.usage_tracker import _resolve_3mf_fallback

    printer = await printer_factory()
    candidate = tmp_path / "library" / "Widget.3mf"
    candidate.parent.mkdir()
    _make_3mf(candidate, plate=1)
    db_session.add(
        LibraryFile(
            filename="Widget.3mf",
            file_path=str(candidate),
            file_type="3mf",
            file_size=candidate.stat().st_size,
        )
    )
    fallback = PrintArchive(
        printer_id=printer.id,
        filename="/data/Metadata/plate_2.gcode",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        extra_data={},
    )
    db_session.add(fallback)
    await db_session.commit()

    resolved = await _resolve_3mf_fallback(
        fallback,
        db_session,
        tmp_path,
        ams_mapping=[0],
    )

    assert resolved is None


@pytest.mark.asyncio
@pytest.mark.parametrize("file_type", ["gcode.3mf", "gcode"])
async def test_usage_fallback_accepts_compound_and_legacy_3mf_types(
    db_session,
    printer_factory,
    tmp_path,
    file_type,
):
    from backend.app.services.usage_tracker import _find_3mf_by_filename, _resolve_3mf_fallback

    printer = await printer_factory()
    candidate = tmp_path / "library" / "Widget.gcode.3mf"
    candidate.parent.mkdir()
    _make_3mf(candidate)
    db_session.add(
        LibraryFile(
            filename="Widget.gcode.3mf",
            file_path=str(candidate),
            file_type=file_type,
            file_size=candidate.stat().st_size,
        )
    )
    fallback = PrintArchive(
        printer_id=printer.id,
        filename="Widget.gcode.3mf",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        extra_data={},
    )
    db_session.add(fallback)
    await db_session.commit()

    assert await _resolve_3mf_fallback(fallback, db_session, tmp_path) == candidate
    assert await _find_3mf_by_filename(printer.id, "Widget", db_session, tmp_path) == candidate


@pytest.mark.asyncio
async def test_usage_fallback_does_not_treat_dotted_prefix_as_same_name(
    db_session,
    printer_factory,
    tmp_path,
):
    from backend.app.services.usage_tracker import _resolve_3mf_fallback

    printer = await printer_factory()
    candidate = tmp_path / "library" / "Widget.variant.3mf"
    candidate.parent.mkdir()
    _make_3mf(candidate)
    db_session.add(
        LibraryFile(
            filename="Widget.variant.3mf",
            file_path=str(candidate),
            file_type="3mf",
            file_size=candidate.stat().st_size,
        )
    )
    fallback = PrintArchive(
        printer_id=printer.id,
        filename="Widget.3mf",
        file_path="",
        file_size=0,
        print_name="Widget",
        status="printing",
        extra_data={},
    )
    db_session.add(fallback)
    await db_session.commit()

    assert await _resolve_3mf_fallback(fallback, db_session, tmp_path) is None


@pytest.mark.asyncio
async def test_fallback_timelapse_stays_under_archive_root(tmp_path):
    from backend.app.services.archive import ArchiveService

    archive = MagicMock(id=1, file_path="", timelapse_path=None)
    db = AsyncMock()
    service = ArchiveService(db)
    service.get_archive = AsyncMock(return_value=archive)
    printer_directory = tmp_path / "archives" / "1"
    printer_directory.mkdir(parents=True)
    (printer_directory / "existing-print.3mf").write_bytes(b"keep")
    with patch("backend.app.services.archive.settings") as settings:
        settings.base_dir = tmp_path
        settings.archive_dir = tmp_path / "archives"
        assert await service.attach_timelapse(1, b"video", "print.mp4")

    target = tmp_path / "archives" / "_fallback" / "1" / "print.mp4"
    assert target.read_bytes() == b"video"
    assert (printer_directory / "existing-print.3mf").read_bytes() == b"keep"
    assert Path(archive.timelapse_path) == Path("archives/_fallback/1/print.mp4")


def test_baseline_state_records_trust_and_round_trips():
    stored = baseline_state({"old.mp4", ""}, trusted=True)
    assert stored == {"names": ["old.mp4"], "trusted": True}
    assert read_baseline_state(stored) == ({"old.mp4"}, True)
    assert read_baseline_state({"names": [], "trusted": False}) == (set(), False)


def _timelapse_session(printer, *, claimed: list[str] | None = None):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()

    async def execute(statement):
        if "timelapse_path" in str(statement):
            return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=claimed or []))))
        return MagicMock(scalar_one_or_none=MagicMock(return_value=printer))

    session.execute = AsyncMock(side_effect=execute)
    return session


@pytest.mark.asyncio
async def test_multiple_new_timelapses_are_left_unassigned():
    from backend.app.services.timelapse_archive import scan_for_timelapse_with_retries

    archive = MagicMock(id=1, printer_id=7, timelapse_path=None)
    printer = MagicMock(id=7)
    session = _timelapse_session(printer)
    service = MagicMock()
    service.get_archive = AsyncMock(return_value=archive)
    service.attach_timelapse = AsyncMock(return_value=True)
    videos = AsyncMock(
        return_value=(
            [
                {"name": "short_a.mp4", "path": "/timelapse/short_a.mp4"},
                {"name": "short_b.mp4", "path": "/timelapse/short_b.mp4"},
            ],
            "/timelapse",
        )
    )
    with patch("backend.app.services.timelapse_archive.asyncio.sleep", new_callable=AsyncMock):
        await scan_for_timelapse_with_retries(
            1,
            set(),
            session_factory=lambda: session,
            archive_service_factory=lambda db: service,
            list_videos=videos,
            websocket_manager=MagicMock(),
        )

    service.attach_timelapse.assert_not_awaited()


@pytest.mark.asyncio
async def test_previous_prints_claimed_timelapse_is_not_reused():
    from backend.app.services.timelapse_archive import scan_for_timelapse_with_retries

    archive = MagicMock(id=2, printer_id=7, timelapse_path=None)
    printer = MagicMock(id=7)
    session = _timelapse_session(printer, claimed=["archives/7/old.mp4"])
    service = MagicMock()
    service.get_archive = AsyncMock(return_value=archive)
    service.attach_timelapse = AsyncMock(return_value=True)
    videos = AsyncMock(return_value=([{"name": "old.mp4", "path": "/timelapse/old.mp4"}], "/timelapse"))
    with patch("backend.app.services.timelapse_archive.asyncio.sleep", new_callable=AsyncMock):
        await scan_for_timelapse_with_retries(
            2,
            set(),
            session_factory=lambda: session,
            archive_service_factory=lambda db: service,
            list_videos=videos,
            websocket_manager=MagicMock(),
        )

    service.attach_timelapse.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_completion_has_no_production_side_effects():
    data = {"filename": "pa_line_calib_mode.gcode", "subtask_name": "pa_line_calib_mode"}
    with (
        patch("backend.app.main.print_provenance.claim_print_session", new_callable=AsyncMock) as claim,
        patch("backend.app.main.print_provenance.discard_print_session", new_callable=AsyncMock) as discard,
        patch("backend.app.services.bambu_ftp.clear_3mf_cache") as clear_cache,
        patch("backend.app.main.ws_manager.send_print_complete", new_callable=AsyncMock) as notify,
    ):
        session = MagicMock()
        claim.return_value = session
        from backend.app.main import on_print_complete

        await on_print_complete(1, data)

    discard.assert_awaited_once_with(1, session, ANY)
    clear_cache.assert_not_called()
    notify.assert_not_awaited()
