"""Timelapse writes own their target and never clobber an earlier recording."""

from pathlib import Path

import pytest

from backend.app.services.archive_timelapse import reserve_conversion_path, write_unique


def test_existing_filename_is_preserved(tmp_path):
    old = tmp_path / "video.mp4"
    old.write_bytes(b"keep existing")
    created = write_unique(tmp_path, "video.mp4", b"new recording")
    assert created != old
    assert old.read_bytes() == b"keep existing"
    assert created.read_bytes() == b"new recording"


def test_converter_reserves_a_distinct_output_from_an_earlier_mp4(tmp_path):
    old = tmp_path / "video.mp4"
    old.write_bytes(b"keep existing")
    output = reserve_conversion_path(tmp_path / "video.avi")
    assert output != old and output.exists()
    assert old.read_bytes() == b"keep existing"


def test_open_failure_does_not_unlink_a_target_not_owned_by_this_write(tmp_path, monkeypatch):
    old = tmp_path / "video.mp4"
    old.write_bytes(b"keep existing")
    original = Path.open

    def refused(self, mode="r", *args, **kwargs):
        if mode == "xb":
            raise PermissionError("fixture denial")
        return original(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refused)
    with pytest.raises(PermissionError):
        write_unique(tmp_path, "video.mp4", b"new recording")
    assert old.read_bytes() == b"keep existing"


@pytest.mark.asyncio
async def test_refresh_failure_does_not_fail_a_successful_change(monkeypatch):
    from unittest.mock import AsyncMock

    from backend.app.core.websocket import ws_manager
    from backend.app.services.archive_timelapse import announce_timelapse

    announce = AsyncMock(side_effect=OSError("fixture disconnected client"))
    monkeypatch.setattr(ws_manager, "send_archive_updated", announce)
    await announce_timelapse(5, attached=True)
    announce.assert_awaited_once_with({"id": 5, "timelapse_attached": True})
