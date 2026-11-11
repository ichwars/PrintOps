"""Unread cards, recovery backoff and ownership of the running print."""

import ftplib
import ssl
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services import bambu_ftp, timelapse_baseline as baseline
from backend.app.services.ftp_background import clear_stall, record_stall
from backend.app.services.ftp_listing import FileListResult

pytestmark = pytest.mark.asyncio
PRINTER = SimpleNamespace(id=1, ip_address="192.0.2.84", access_code="fixture", model="P1S")


def recovery_context():
    names = baseline.BaselineNames()
    baselines = {1: names}
    status = SimpleNamespace(connected=True, state="RUNNING", timelapse=True)
    db = AsyncMock()
    db.get.return_value = PRINTER

    @asynccontextmanager
    async def session():
        yield db

    return (
        names,
        baselines,
        status,
        {"baselines": baselines, "get_status": lambda _: status, "session_factory": session},
    )


async def test_one_empty_folder_cannot_vouch_for_unread_folders(monkeypatch):
    read = AsyncMock(side_effect=[[], OSError("unread"), [], []])
    monkeypatch.setattr(bambu_ftp, "list_files_strict_async", read)
    with pytest.raises(OSError, match="unread"):
        await baseline.list_videos(PRINTER)
    assert read.await_count == 4


@pytest.mark.parametrize("message,missing", [("550 No such directory", True), ("550 Permission denied", False)])
async def test_missing_directory_is_distinct_from_permission_failure(monkeypatch, message, missing):
    error = bambu_ftp.FileListingError("wrapped")
    error.__cause__ = ftplib.error_perm(message)
    assert FileListResult([], False, error=error).missing is missing
    monkeypatch.setattr(bambu_ftp, "list_files_strict_async", AsyncMock(side_effect=[[], error, [], []]))
    if missing:
        assert await baseline.list_videos(PRINTER) == ([], None)
    else:
        with pytest.raises(bambu_ftp.FileListingError):
            await baseline.list_videos(PRINTER)


async def test_later_directory_with_videos_can_answer_after_an_ordinary_failure(monkeypatch):
    read = AsyncMock(side_effect=[OSError("path unavailable"), [{"name": "old.avi"}]])
    monkeypatch.setattr(bambu_ftp, "list_files_strict_async", read)
    assert await baseline.list_videos(PRINTER) == ([{"name": "old.avi"}], "/timelapse/video")
    assert read.await_count == 2


async def test_stall_stops_the_directory_walk_after_one_attempt(monkeypatch):
    async def hung(*args, **kwargs):
        record_stall(PRINTER.ip_address, "fixture")
        raise TimeoutError("silent printer")

    read = AsyncMock(side_effect=hung)
    monkeypatch.setattr(bambu_ftp, "list_files_strict_async", read)
    with pytest.raises(bambu_ftp.FileListingError, match="paused"):
        await baseline.list_videos(PRINTER)
    read.assert_awaited_once()


async def test_unread_capture_keeps_trust_and_schedules_recovery():
    names, baselines, status, context = recovery_context()
    archive = SimpleNamespace(
        printer_id=1, started_at=None, timelapse_baseline={"names": ["last-run.avi"], "trusted": True}
    )
    db = AsyncMock()
    db.get.return_value = archive
    db.scalar.return_value = None
    spawn = MagicMock(side_effect=lambda coro, **_: coro.close())
    await baseline.capture(
        PRINTER, 1, list_videos=AsyncMock(side_effect=OSError("unread")), spawn=spawn, db=db, archive_id=4, **context
    )
    assert baselines[1] is not names
    assert baselines[1].trusted is False
    assert archive.timelapse_baseline == {"names": [], "trusted": False}
    spawn.assert_called_once()


async def test_restart_preserves_trusted_persisted_baseline_without_reading_card():
    _, baselines, _, context = recovery_context()
    db = AsyncMock()
    db.scalar.return_value = None
    db.get.return_value = SimpleNamespace(
        printer_id=1, started_at=None, timelapse_baseline={"names": ["old.avi"], "trusted": True}
    )
    read, spawn = AsyncMock(), MagicMock()
    await baseline.capture(
        PRINTER, 1, list_videos=read, spawn=spawn, db=db, archive_id=4, preserve_stored=True, **context
    )
    assert baselines[1] == {"old.avi"} and baselines[1].trusted
    read.assert_not_awaited()
    spawn.assert_not_called()


async def test_new_capture_owns_the_run_while_old_listing_returns():
    _, baselines, _, context = recovery_context()
    newer = baseline.BaselineNames({"other-run.avi"})

    async def superseded(_):
        baselines[1] = newer
        return [{"name": "late.avi"}], "/timelapse"

    db = AsyncMock()
    db.scalar.return_value = None
    db.get.return_value = SimpleNamespace(printer_id=1, started_at=None, timelapse_baseline=None)
    await baseline.capture(PRINTER, 1, list_videos=superseded, spawn=MagicMock(), db=db, archive_id=4, **context)
    assert baselines[1] is newer
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "disconnected,recording,state,expected",
    [
        (True, True, "RUNNING", None),
        (False, False, "RUNNING", None),
        (False, True, "FINISH", False),
        (False, True, "PREPARE", True),
    ],
)
async def test_reread_requires_the_same_active_recording(disconnected, recording, state, expected):
    names, baselines, status, context = recovery_context()
    status.connected, status.timelapse, status.state = not disconnected, recording, state
    assert baseline.reread_state(1, names, baselines, context["get_status"]) is expected
    baselines.pop(1)
    assert baseline.reread_state(1, names, baselines, context["get_status"]) is False


async def test_failed_rereads_back_off_and_stop_after_five_rounds(monkeypatch):
    names, _, _, context = recovery_context()
    sleep = AsyncMock()
    monkeypatch.setattr(baseline.asyncio, "sleep", sleep)
    read = AsyncMock(side_effect=OSError("unread"))
    await baseline.reread(1, names, None, None, list_videos=read, **context)
    assert read.await_count == 5
    assert [call.args[0] for call in sleep.await_args_list] == [120, 240, 480, 960, 1800]
    assert not names.trusted


@pytest.mark.parametrize("change", ["finished", "next-print", "disconnected"])
async def test_late_read_cannot_trust_a_finished_or_replaced_print(monkeypatch, change):
    names, baselines, status, context = recovery_context()
    monkeypatch.setattr(baseline.asyncio, "sleep", AsyncMock())

    async def late(_):
        if change == "next-print":
            baselines[1] = baseline.BaselineNames()
        elif change == "finished":
            status.state = "FINISH"
        else:
            status.connected = False
        return [{"name": "late.avi"}], "/timelapse"

    monkeypatch.setattr(baseline, "REREAD_MAX_ROUNDS", 1)
    await baseline.reread(1, names, None, None, list_videos=late, **context)
    assert not names and not names.trusted


async def test_successful_reread_trusts_names_and_stops(monkeypatch):
    names, _, _, context = recovery_context()
    monkeypatch.setattr(baseline.asyncio, "sleep", AsyncMock())
    read = AsyncMock(return_value=([{"name": "old.avi"}], "/timelapse"))
    await baseline.reread(1, names, None, None, list_videos=read, **context)
    assert names == {"old.avi"} and names.trusted
    read.assert_awaited_once()


async def test_background_stall_does_not_block_manual_listing(monkeypatch):
    record_stall(PRINTER.ip_address, "fixture")
    client = MagicMock()
    client.connect.return_value = True
    client.list_files.return_value = [{"name": "old.avi"}]
    monkeypatch.setattr(bambu_ftp, "BambuFTPClient", MagicMock(return_value=client))
    result = await bambu_ftp.list_files_result_async(PRINTER.ip_address, "fixture")
    assert result.available and result.files
    assert not bambu_ftp.ftps_background_blocked(PRINTER.ip_address)


async def test_connect_alone_does_not_clear_a_listing_stall(monkeypatch):
    record_stall(PRINTER.ip_address, "fixture")
    ftp = MagicMock()
    monkeypatch.setattr(bambu_ftp, "ImplicitFTP_TLS", MagicMock(return_value=ftp))
    client = bambu_ftp.BambuFTPClient(PRINTER.ip_address, "fixture")
    assert client.connect()
    assert bambu_ftp.ftps_background_blocked(PRINTER.ip_address)
    assert client.list_files("/timelapse", raise_on_error=True) == []
    assert not bambu_ftp.ftps_background_blocked(PRINTER.ip_address)
    client.disconnect()


@pytest.mark.parametrize("background", [False, True])
async def test_socket_timeout_records_stall_for_regular_clients(monkeypatch, background):
    ftp = MagicMock()
    ftp.connect.side_effect = TimeoutError("silent handshake")
    monkeypatch.setattr(bambu_ftp, "ImplicitFTP_TLS", MagicMock(return_value=ftp))
    client = bambu_ftp.BambuFTPClient(PRINTER.ip_address, "fixture", respect_handshake_cooldown=background)
    assert not client.connect()
    assert bambu_ftp.ftps_background_blocked(PRINTER.ip_address) is background


async def test_stall_expires_without_blocking_other_printers(monkeypatch):
    from backend.app.services import ftp_background

    monkeypatch.setattr(ftp_background.time, "monotonic", lambda: 1)
    record_stall(PRINTER.ip_address, "fixture")
    assert bambu_ftp.ftps_background_blocked(PRINTER.ip_address)
    assert not bambu_ftp.ftps_background_blocked("192.0.2.85")
    monkeypatch.setattr(ftp_background.time, "monotonic", lambda: 302)
    assert not bambu_ftp.ftps_background_blocked(PRINTER.ip_address)
    clear_stall(PRINTER.ip_address)


@pytest.mark.parametrize("cleartext", [False, True])
async def test_session_exhaustion_is_diagnosed_and_requeued(monkeypatch, cleartext):
    from backend.app.services.print_scheduler import _UPLOAD_REQUEUE_KINDS
    from backend.app.services.queue_upload_refusal import hold_reason

    ftp = MagicMock()
    if cleartext:
        error = ssl.SSLError("wrong version")
        error.reason = "WRONG_VERSION_NUMBER"
        ftp.connect.side_effect = error
        monkeypatch.setattr(bambu_ftp, "_read_cleartext_reply", lambda *args: "421 too many connections")
    else:
        ftp.connect.side_effect = ftplib.error_temp("421 too many connections")
    monkeypatch.setattr(bambu_ftp, "ImplicitFTP_TLS", MagicMock(return_value=ftp))
    client = bambu_ftp.BambuFTPClient(PRINTER.ip_address, "fixture", respect_handshake_cooldown=False)
    try:
        assert client.connect() is False
        assert client.last_failure.kind is bambu_ftp.FtpFailureKind.SESSIONS
        assert client.last_failure.kind in _UPLOAD_REQUEUE_KINDS
        assert "restart the printer" in bambu_ftp.describe_upload_failure(client.last_failure)
        assert "restart the printer" in hold_reason("Fixture printer", client.last_failure.kind)
        if cleartext:
            other = bambu_ftp.BambuFTPClient(PRINTER.ip_address, "fixture")
            with pytest.raises(bambu_ftp.FtpsCooldownActive, match="421 too many connections"):
                other.connect()
            assert other.last_failure.kind is bambu_ftp.FtpFailureKind.SESSIONS
    finally:
        bambu_ftp.clear_ftps_cooldown(PRINTER.ip_address)
