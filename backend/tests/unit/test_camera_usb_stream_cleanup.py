"""Regression tests for external USB camera cleanup (#2675)."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import suppress
from unittest.mock import mock_open, patch

import pytest

from backend.app.api.routes import camera
from backend.app.services import external_camera


async def _instant_sleep(*_args, **_kwargs) -> None:
    return None


class _CleanProc:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode = None

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode if self.returncode is not None else 0


class _ImmediateEOFReader:
    async def read(self, _size: int = -1) -> bytes:
        return b""


class _UsbProc:
    def __init__(self, pid: int = 52001) -> None:
        self.pid = pid
        self.returncode = None
        self.stdout = _ImmediateEOFReader()
        self.stderr = _ImmediateEOFReader()

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_stream_usb_registers_process_via_on_process(monkeypatch):
    class _FakePath:
        def __init__(self, _path: str) -> None:
            pass

        def exists(self) -> bool:
            return True

    proc = _UsbProc()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(external_camera, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(external_camera, "Path", _FakePath)
    monkeypatch.setattr(external_camera.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(external_camera.asyncio, "sleep", _instant_sleep)

    captured: list[object] = []
    stream = external_camera._stream_usb("/dev/video0", 10, on_process=captured.append)
    try:
        async for _frame in stream:
            pass
    finally:
        with suppress(Exception):
            await stream.aclose()

    assert captured == [proc]


@pytest.mark.asyncio
async def test_stop_endpoint_terminates_registered_external_process(monkeypatch):
    monkeypatch.setattr(camera, "get_subscriber_count", lambda _key: 0)

    async def fake_shutdown(_key):
        return False

    monkeypatch.setattr(camera, "shutdown_broadcaster", fake_shutdown)

    printer_id = 7
    stream_id = f"{printer_id}-ext-abc12345"
    proc = _CleanProc(pid=52010)
    event = asyncio.Event()
    camera._active_streams[stream_id] = proc
    camera._disconnect_events[stream_id] = event
    camera._spawned_ffmpeg_pids[proc.pid] = time.time()
    camera._stream_last_frame_times[stream_id] = time.time()

    try:
        result = await camera.stop_camera_stream(printer_id, _=None)
        assert result["stopped"] == 1
        assert proc.returncode is not None
        assert event.is_set()
        assert stream_id not in camera._active_streams
        assert stream_id not in camera._disconnect_events
        assert proc.pid not in camera._spawned_ffmpeg_pids
    finally:
        camera._active_streams.pop(stream_id, None)
        camera._disconnect_events.pop(stream_id, None)
        camera._spawned_ffmpeg_pids.pop(proc.pid, None)
        camera._stream_last_frame_times.pop(stream_id, None)


@pytest.mark.asyncio
async def test_cleanup_janitor_reaps_stale_external_usb_stream(monkeypatch):
    monkeypatch.setattr(camera, "_scan_bambu_ffmpeg_pids", lambda: [])

    proc = _CleanProc(pid=os.getpid())
    stream_id = "7-ext-deadbeef"
    now = time.time()
    camera._active_streams[stream_id] = proc
    camera._spawned_ffmpeg_pids[proc.pid] = now - 120
    camera._stream_last_frame_times[stream_id] = now - 60
    camera._disconnect_events[stream_id] = asyncio.Event()

    try:
        await asyncio.wait_for(camera.cleanup_orphaned_streams(), timeout=2.0)
        assert proc.returncode is not None
        assert stream_id not in camera._active_streams
    finally:
        camera._active_streams.pop(stream_id, None)
        camera._spawned_ffmpeg_pids.pop(proc.pid, None)
        camera._stream_last_frame_times.pop(stream_id, None)
        camera._disconnect_events.pop(stream_id, None)


def test_scan_matches_tracked_v4l2_ffmpeg(monkeypatch):
    cmdline = b"ffmpeg\x00-f\x00v4l2\x00-i\x00/dev/video0\x00-f\x00mjpeg\x00-\x00"
    monkeypatch.setattr("os.listdir", lambda _path: ["52020"])
    camera._spawned_ffmpeg_pids[52020] = time.time()
    try:
        with patch("builtins.open", mock_open(read_data=cmdline)):
            assert 52020 in camera._scan_bambu_ffmpeg_pids()
    finally:
        camera._spawned_ffmpeg_pids.pop(52020, None)


def test_scan_ignores_untracked_v4l2_ffmpeg(monkeypatch):
    cmdline = b"ffmpeg\x00-f\x00v4l2\x00-i\x00/dev/video0\x00-f\x00mjpeg\x00-\x00"
    monkeypatch.setattr("os.listdir", lambda _path: ["52020"])
    camera._spawned_ffmpeg_pids.pop(52020, None)
    with patch("builtins.open", mock_open(read_data=cmdline)):
        assert camera._scan_bambu_ffmpeg_pids() == []


def test_scan_ignores_unrelated_ffmpeg(monkeypatch):
    cmdline = b"ffmpeg\x00-i\x00C:\\Users\\droth\\video.mp4\x00out.mkv\x00"
    monkeypatch.setattr("os.listdir", lambda _path: ["52021"])
    with patch("builtins.open", mock_open(read_data=cmdline)):
        assert camera._scan_bambu_ffmpeg_pids() == []
