"""Pause schedules follow the active 3MF plate and durable print run."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from backend.app.models.print_log import RUN_OPEN, PrintLogEntry
from backend.app.services import pause_eta
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.notification_service import notification_service
from backend.app.services.printer_manager import printer_manager, printer_state_to_dict
from backend.app.utils.gcode_pause_points import PausePoint, extract_pause_points

pytestmark = pytest.mark.integration


def make_archive(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "M73 L9 R8\nM400 U1\n")
        archive.writestr(
            "Metadata/plate_2.gcode",
            "M400 U1\nM73 L42\nM400\nM400 U10\n; M400 U1\nM73 P32 R10\nm400 u1 ; pause\n"
            "M73 R8\nM400 U1\nM73 L80 R2\nM400 U1\n",
        )


def test_reads_only_the_selected_plate(tmp_path):
    path = tmp_path / "test.gcode.3mf"
    make_archive(path)
    assert extract_pause_points(path, 1) == (PausePoint(9, 8),)
    assert extract_pause_points(path, 2) == (PausePoint(42, 10), PausePoint(80, 2))
    assert extract_pause_points(path, 3) == extract_pause_points(path, None) == ()

    with ZipFile(path, "w") as archive:
        archive.writestr("print.gcode", "M73 L31\nM400 U1\n")
    assert extract_pause_points(path, 3) == (PausePoint(31, None),)


@pytest.mark.asyncio
async def test_resolves_and_warns_once_per_run_after_restart(
    async_client, db_session, printer_factory, archive_factory, notification_provider_factory, tmp_path, monkeypatch
):
    path = tmp_path / "test.gcode.3mf"
    make_archive(path)
    printer = await printer_factory()
    other_printer = await printer_factory()
    archive = await archive_factory(printer.id, file_path=path.name, with_run=False)
    run = PrintLogEntry(archive_id=archive.id, printer_id=printer.id, subtask_id="91", plate_id=2, status=RUN_OPEN)
    db_session.add(run)
    await db_session.commit()
    provider = await notification_provider_factory(printer_id=printer.id)
    await notification_provider_factory(printer_id=other_printer.id, on_print_pause_upcoming=True)
    current = PrinterState(
        connected=True, state="RUNNING", subtask_id="91", subtask_name="Test", remaining_time=14, layer_num=31
    )

    @asynccontextmanager
    async def use_db():
        yield db_session

    monkeypatch.setattr(pause_eta, "async_session", use_db)
    monkeypatch.setattr(pause_eta.settings, "base_dir", tmp_path)
    monkeypatch.setattr(printer_manager, "get_status", lambda _: current)
    monkeypatch.setattr(printer_manager, "get_printer", lambda _: SimpleNamespace(name=printer.name))
    broadcast = AsyncMock()
    monkeypatch.setattr(printer_manager, "broadcast_status_change", broadcast)
    send = AsyncMock()
    monkeypatch.setattr(notification_service, "_send_to_providers", send)

    async def observe():
        if current.pause_tracking is not None:
            current.pause_tracking.next_check = 0
        pause_eta.observe(printer.id, current, printer_manager)
        await current.pause_tracking.task

    await observe()
    assert printer_state_to_dict(current)["next_pause"] == {"layer": 42, "minutes": 4}
    status = await async_client.get(f"/api/v1/printers/{printer.id}/status")
    assert status.status_code == 200, status.text
    assert status.json()["next_pause"] == {"layer": 42, "minutes": 4}
    broadcast.assert_awaited_once_with(printer.id)
    send.assert_not_awaited()

    current.speed_level = 1
    assert pause_eta.next_pause(current) == {"layer": 42, "minutes": None}
    current.speed_level = 2
    assert (await async_client.put("/api/v1/settings/", json={"pause_warning_minutes": 0})).status_code == 422
    assert (await async_client.put("/api/v1/settings/", json={"pause_warning_minutes": 3})).status_code == 200
    saved = await async_client.patch(f"/api/v1/notifications/{provider.id}", json={"on_print_pause_upcoming": True})
    assert saved.status_code == 200 and saved.json()["on_print_pause_upcoming"] is True, saved.text
    await observe()
    send.assert_not_awaited()

    current.remaining_time = 13
    await observe()
    send.assert_awaited_once()
    assert [p.id for p in send.call_args.args[0]] == [provider.id]
    assert send.call_args.args[4] == "print_pause_upcoming"
    assert send.call_args.kwargs["variables"]["layer"] == "42"

    current.pause_tracking = None
    await observe()
    send.assert_awaited_once()
    current.layer_num = 42
    assert pause_eta.next_pause(current) == {"layer": 80, "minutes": 11}
    current.connected = False
    assert pause_eta.next_pause(current) is None


@pytest.mark.asyncio
async def test_stale_scan_cannot_attach_to_a_new_print(
    db_session, printer_factory, archive_factory, tmp_path, monkeypatch
):
    printer = await printer_factory()
    path = tmp_path / "test.gcode.3mf"
    make_archive(path)
    archive = await archive_factory(printer.id, file_path=path.name, with_run=False)
    db_session.add(PrintLogEntry(archive_id=archive.id, printer_id=printer.id, subtask_id="91", status=RUN_OPEN))
    await db_session.commit()
    current = PrinterState(connected=True, state="RUNNING", subtask_id="91")

    @asynccontextmanager
    async def use_db():
        yield db_session

    async def change_run(*args):
        await asyncio.sleep(0)
        current.subtask_id = "92"
        return (PausePoint(42, 10),)

    monkeypatch.setattr(pause_eta, "async_session", use_db)
    monkeypatch.setattr(pause_eta.settings, "base_dir", tmp_path)
    monkeypatch.setattr(pause_eta.asyncio, "to_thread", change_run)
    monkeypatch.setattr(printer_manager, "get_status", lambda _: current)
    pause_eta.observe(printer.id, current, printer_manager)
    await current.pause_tracking.task
    assert current.pause_tracking.run_id is None
    assert pause_eta.next_pause(current) is None
