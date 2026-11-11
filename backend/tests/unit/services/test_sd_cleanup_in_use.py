"""Late completion cleanup preserves the file a printer is already using."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services import bambu_ftp, print_sd_cleanup


def state(status="RUNNING", filename="", subtask=""):
    return SimpleNamespace(state=status, gcode_file=filename, subtask_name=subtask)


@pytest.mark.parametrize("status", ["RUNNING", "PREPARE", "SLICING", "PAUSE"])
@pytest.mark.parametrize("filename", ["REPEAT.3MF", "/cache/REPEAT.3MF", "file:///userdata/REPEAT.3MF"])
def test_busy_file_is_compared_by_name_ignoring_case(status, filename):
    assert "repeat.3mf" in print_sd_cleanup.sd_files_in_use(state(status, filename))


def test_uri_hash_is_part_of_the_printer_filename():
    names = print_sd_cleanup.sd_files_in_use(state(filename="file:///cache/Part#2.3mf"))
    assert "part#2.3mf" in names
    assert "part" not in names


@pytest.mark.parametrize("subtask", ["Repeat", "Repeat.gcode.3mf"])
def test_subtask_protects_the_dispatchers_normalized_filename(subtask):
    assert "repeat.3mf" in print_sd_cleanup.sd_files_in_use(state(subtask=subtask))


def test_subtask_protects_space_and_underscore_spellings():
    names = print_sd_cleanup.sd_files_in_use(state(subtask="Some File"))
    assert {"some file.3mf", "some_file.3mf", "some file.gcode", "some_file.gcode"} <= names


@pytest.mark.parametrize("status", ["IDLE", "FINISH", "FAILED", "UNKNOWN", ""])
def test_terminal_or_initial_state_retains_existing_cleanup_behavior(status):
    assert not print_sd_cleanup.sd_files_in_use(state(status, "repeat.3mf", "repeat"))


def cleanup_session():
    db = AsyncMock()
    printer = SimpleNamespace(name="Fixture", ip_address="192.0.2.10", access_code="fixture", model="P1S")
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=printer)),
        MagicMock(scalar_one_or_none=MagicMock(return_value="repeat.gcode.3mf")),
    ]

    @asynccontextmanager
    async def session():
        yield db

    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,filename,subtask,deleted",
    [
        ("RUNNING", "repeat.3mf", "repeat", False),
        ("PREPARE", "repeat.3mf", "repeat", False),
        ("PAUSE", "/cache/repeat.3mf", "repeat", False),
        ("FINISH", "repeat.3mf", "repeat", True),
        ("RUNNING", "another.3mf", "another", True),
    ],
)
async def test_cleanup_keeps_current_file_but_still_removes_an_old_one(monkeypatch, status, filename, subtask, deleted):
    delete = AsyncMock(return_value=bambu_ftp.DeleteResult.NOT_FOUND)
    monkeypatch.setattr(bambu_ftp, "delete_file_async", delete)
    await print_sd_cleanup.cleanup_after_print(
        1, "repeat", 7, MagicMock(), cleanup_session(), get_status=lambda _: state(status, filename, subtask)
    )
    assert delete.await_count == (2 if deleted else 0)


@pytest.mark.asyncio
async def test_new_print_during_retry_prevents_the_next_delete(monkeypatch):
    current = state("FINISH", "repeat.3mf", "repeat")

    async def failed(*args, **kwargs):
        current.state = "RUNNING"
        return bambu_ftp.DeleteResult.FAILED

    delete = AsyncMock(side_effect=failed)
    monkeypatch.setattr(bambu_ftp, "delete_file_async", delete)
    monkeypatch.setattr(print_sd_cleanup.asyncio, "sleep", AsyncMock())
    await print_sd_cleanup.cleanup_after_print(
        1, "repeat", 7, MagicMock(), cleanup_session(), get_status=lambda _: current
    )
    delete.assert_awaited_once()
