"""LAN display links may use names; control data needs stronger print evidence."""

import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import main
from backend.app.api.routes import printers, printers_controls
from backend.app.models.active_print_session import ActivePrintSession
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.running_print_archive import find_running_archive, local_archive_file

pytestmark = pytest.mark.asyncio


def running_state(job="0", name="Part"):
    state = PrinterState()
    state.connected, state.state = True, "RUNNING"
    state.subtask_id, state.subtask_name = job, name
    state.gcode_file = "/data/Metadata/plate_1.gcode"
    return state


def source_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.png", b"LOCAL_ARCHIVE_PNG")
        archive.writestr("Metadata/plate_1.gcode", "G28\n")
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/>'
            '<object identify_id="3" name="Part A" skipped="false"/></plate></config>',
        )


@pytest.mark.parametrize("by_name,expected", [(False, False), (True, True)])
async def test_lan_name_match_is_display_only(by_name, expected, db_session, printer_factory, archive_factory):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="Part.gcode.3mf",
        print_name="Embedded title",
        status="printing",
        subtask_id=None,
    )
    result = await find_running_archive(db_session, printer.id, running_state(), bindings={}, by_name=by_name)
    assert (result is archive) is expected


@pytest.mark.parametrize("blocked", ["deleted", "other-printer", "different-id", "terminal"])
async def test_name_fallback_rejects_unrelated_or_terminal_rows(blocked, db_session, printer_factory, archive_factory):
    printer = await printer_factory()
    other = await printer_factory()
    await archive_factory(
        other.id if blocked == "other-printer" else printer.id,
        with_run=False,
        filename="Part.gcode.3mf",
        status="completed" if blocked == "terminal" else "printing",
        subtask_id="real-id" if blocked == "different-id" else None,
        deleted_at=datetime.now() if blocked == "deleted" else None,
    )
    assert await find_running_archive(db_session, printer.id, running_state(), bindings={}, by_name=True) is None


async def test_explicit_lan_binding_can_supply_objects(db_session, printer_factory, archive_factory):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, filename="Part.gcode.3mf", status="printing")
    found = await find_running_archive(
        db_session, printer.id, running_state(), bindings={(printer.id, "Part.3mf"): archive.id}
    )
    assert found is archive


@pytest.mark.parametrize("session_matches", [False, True])
async def test_shared_source_requires_this_printers_current_session_on_id_conflict(
    session_matches, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    other = await printer_factory()
    archive = await archive_factory(
        other.id, with_run=False, filename="Part.gcode.3mf", status="printing", subtask_id="other-printer-run"
    )
    if session_matches:
        db_session.add(
            ActivePrintSession(
                printer_id=printer.id, print_name="Part", subtask_id="this-run", started_at=datetime.now()
            )
        )
        await db_session.commit()
    found = await find_running_archive(
        db_session, printer.id, running_state("this-run"), bindings={(printer.id, "Part.3mf"): archive.id}
    )
    assert (found is archive) is session_matches


async def test_rest_status_links_lan_print_without_selecting_any_zero_id_row(
    monkeypatch, async_client, printer_factory, archive_factory
):
    printer = await printer_factory()
    wanted = await archive_factory(
        printer.id, with_run=False, filename="Part.gcode.3mf", status="printing", subtask_id=None
    )
    await archive_factory(
        printer.id, with_run=False, filename="Unrelated.3mf", print_name="Unrelated", status="completed", subtask_id="0"
    )
    state = running_state()
    monkeypatch.setattr(main, "_active_prints", {})
    monkeypatch.setattr(main.printer_manager, "get_status", lambda _: state)
    response = await async_client.get(f"/api/v1/printers/{printer.id}/status")
    assert response.status_code == 200, response.text
    assert response.json()["current_archive_id"] == wanted.id


async def test_cover_passes_larger_size_budget_only_for_a_fallback_archive(
    monkeypatch, async_client, printer_factory, archive_factory, tmp_path
):
    from backend.app.services.bambu_ftp import RECOVERY_DOWNLOAD_MAX_TIMEOUT, DownloadDeadlineExceeded

    printer = await printer_factory()
    monkeypatch.setattr(printers, "settings", SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives"))
    monkeypatch.setattr(printers.printer_manager, "get_status", lambda _: running_state())
    monkeypatch.setattr(printers, "get_cached_3mf", lambda *args: None)
    monkeypatch.setattr(main, "_active_prints", {})
    printers.clear_cover_cache(printer.id)
    ftp = AsyncMock(return_value=False)
    monkeypatch.setattr(printers, "download_file_try_paths_async", ftp)
    url = f"/api/v1/printers/{printer.id}/cover"

    response = await async_client.get(url)
    assert response.status_code == 404, response.text
    assert ftp.await_count > 0
    assert all(call.kwargs["max_total_timeout"] is None for call in ftp.await_args_list)

    await archive_factory(printer.id, with_run=False, filename="Part.gcode.3mf", status="printing", file_path="")
    ftp.reset_mock()
    ftp.side_effect = DownloadDeadlineExceeded("fixture")
    response = await async_client.get(url)

    assert response.status_code == 503, response.text
    assert ftp.await_count == 1
    assert ftp.await_args.kwargs["max_total_timeout"] == RECOVERY_DOWNLOAD_MAX_TIMEOUT


async def test_cover_uses_later_archived_file_even_after_a_cached_404(
    monkeypatch, async_client, printer_factory, archive_factory, tmp_path
):
    printer = await printer_factory()
    state = running_state()
    settings = SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives")
    monkeypatch.setattr(printers, "settings", settings)
    monkeypatch.setattr(printers.printer_manager, "get_status", lambda _: state)
    monkeypatch.setattr(printers, "get_cached_3mf", lambda *args: None)
    monkeypatch.setattr(main, "_active_prints", {})
    printers.clear_cover_cache(printer.id)
    ftp = AsyncMock(return_value=False)
    monkeypatch.setattr(printers, "download_file_try_paths_async", ftp)
    response = await async_client.get(f"/api/v1/printers/{printer.id}/cover")
    assert response.status_code == 404, response.text
    attempts = ftp.await_count
    source_file(settings.archive_dir / "part" / "Part.3mf")
    await archive_factory(
        printer.id, with_run=False, filename="Part.gcode.3mf", status="printing", file_path="archives/part/Part.3mf"
    )
    response = await async_client.get(f"/api/v1/printers/{printer.id}/cover")
    assert response.status_code == 200 and response.content == b"LOCAL_ARCHIVE_PNG"
    assert ftp.await_count == attempts
    assert (settings.archive_dir / "part" / "Part.3mf").is_file()
    printers.clear_cover_cache(printer.id)


async def test_object_reload_uses_bound_file_and_preserves_skipped_objects(
    monkeypatch, async_client, printer_factory, archive_factory, tmp_path
):
    from backend.app.services import bambu_ftp

    printer = await printer_factory()
    source_file(tmp_path / "Part.3mf")
    archive = await archive_factory(
        printer.id, with_run=False, filename="Part.gcode.3mf", status="printing", file_path="Part.3mf"
    )
    state = running_state()
    state.skipped_objects = [3]
    client = SimpleNamespace(state=state)
    monkeypatch.setattr(printers_controls, "settings", SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr(printers.printer_manager, "get_client", lambda _: client)
    monkeypatch.setattr(main, "_active_prints", {(printer.id, "Part.3mf"): archive.id})
    ftp = AsyncMock(side_effect=AssertionError("bound archive should satisfy reload"))
    monkeypatch.setattr(bambu_ftp, "download_file_try_paths_async", ftp)
    response = await async_client.get(f"/api/v1/printers/{printer.id}/print/objects?reload=true")
    assert response.status_code == 200, response.text
    assert response.json()["objects"][0]["id"] == 3
    assert response.json()["objects"][0]["skipped"] is True
    ftp.assert_not_awaited()


@pytest.mark.parametrize("change_during", ["lookup", "parse"])
async def test_reload_rejects_a_print_change_before_applying_objects(
    change_during, monkeypatch, async_client, printer_factory, archive_factory, tmp_path
):
    from backend.app.services import archive as archive_module, running_print_archive

    printer = await printer_factory()
    source_file(tmp_path / "Part.3mf")
    archive = await archive_factory(
        printer.id, with_run=False, filename="Part.gcode.3mf", status="printing", file_path="Part.3mf"
    )
    state = running_state()
    client = SimpleNamespace(state=state)
    monkeypatch.setattr(printers_controls, "settings", SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr(printers.printer_manager, "get_client", lambda _: client)
    monkeypatch.setattr(main, "_active_prints", {(printer.id, "Part.3mf"): archive.id})
    if change_during == "lookup":
        original = running_print_archive.find_running_archive

        async def changed(*args, **kwargs):
            result = await original(*args, **kwargs)
            state.subtask_id = "new-print"
            return result

        monkeypatch.setattr(running_print_archive, "find_running_archive", changed)
    else:
        original = archive_module.extract_printable_objects_from_3mf

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            state.subtask_id = "new-print"
            return result

        monkeypatch.setattr(archive_module, "extract_printable_objects_from_3mf", changed)
    response = await async_client.get(f"/api/v1/printers/{printer.id}/print/objects?reload=true")
    assert response.status_code == 409, response.text
    assert not state.printable_objects


@pytest.mark.parametrize("escape", ["traversal", "absolute", "symlink"])
async def test_local_archive_file_rejects_paths_outside_base(escape, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.3mf"
    source_file(outside)
    if escape == "symlink":
        (base / "link.3mf").symlink_to(outside)
        path = "link.3mf"
    else:
        path = "../outside.3mf" if escape == "traversal" else str(outside)
    assert local_archive_file(SimpleNamespace(id=1, file_path=path), base) is None


@pytest.mark.parametrize("status", ["printing", "archived"])
async def test_archiving_uses_detected_start_only_for_a_running_print(status, monkeypatch, db_session, tmp_path):
    from backend.app.services import archive as archive_module

    detected = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    source = tmp_path / "input.3mf"
    source_file(source)
    monkeypatch.setattr(
        archive_module, "settings", SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives")
    )
    result = await archive_module.ArchiveService(db_session).archive_print(
        None, source, print_data={"status": status}, original_filename="Part.gcode.3mf", started_at=detected
    )
    assert result is not None
    assert result.filename == "Part.gcode.3mf"
    assert result.started_at == (detected.replace(tzinfo=None) if status == "printing" else None)


async def test_restart_restores_objects_without_resetting_skip_telemetry(
    monkeypatch, test_engine, printer_factory, archive_factory, tmp_path
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.app.services.printer_archive_objects import restore_running_objects

    printer = await printer_factory()
    source_file(tmp_path / "Part.3mf")
    archive = await archive_factory(
        printer.id, with_run=False, filename="Part.gcode.3mf", file_path="Part.3mf", status="printing", subtask_id="job"
    )
    state = running_state("job")
    state.skipped_objects = [3]
    client = SimpleNamespace(state=state)
    manager = SimpleNamespace(get_client=lambda _: client)
    await restore_running_objects(
        printer.id, manager=manager, bindings={}, session_factory=async_sessionmaker(test_engine), base_dir=tmp_path
    )
    assert archive.id and 3 in state.printable_objects
    assert state.skipped_objects == [3]
