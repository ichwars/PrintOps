"""Regression tests for external USB camera cleanup (#2675)."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.api.routes import camera
from backend.app.services import camera_source_security, external_camera


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
    monkeypatch.setattr(camera_source_security, "Path", _FakePath)
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
async def test_stream_usb_rejects_prefix_traversal_before_ffmpeg(monkeypatch):
    """`/dev/video` is a full allowlist, not a path prefix."""
    proc = _UsbProc()
    spawn = AsyncMock(return_value=proc)

    monkeypatch.setattr(external_camera, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(external_camera.Path, "exists", lambda _path: True)
    monkeypatch.setattr(external_camera.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(external_camera.asyncio, "sleep", _instant_sleep)

    stream = external_camera._stream_usb("/dev/video0/../../etc/passwd", 10)
    async for _frame in stream:
        pass

    spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_endpoint_terminates_registered_external_process(monkeypatch):
    async def fake_shutdown(_key, *, only_if_idle):
        assert only_if_idle
        return False

    monkeypatch.setattr(camera, "shutdown_broadcaster", fake_shutdown)

    printer_id = 7
    stream_id = f"{printer_id}-ext-abc12345"
    proc = _CleanProc(pid=52010)
    event = asyncio.Event()
    camera._active_streams[stream_id] = proc
    camera._disconnect_events[stream_id] = event
    camera._spawned_ffmpeg_processes[proc] = time.time()
    camera._stream_last_frame_times[stream_id] = time.time()

    try:
        result = await camera.stop_camera_stream(printer_id, _=None)
        assert result["stopped"] == 1
        assert proc.returncode is not None
        assert event.is_set()
        assert stream_id not in camera._active_streams
        assert stream_id not in camera._disconnect_events
        assert proc not in camera._spawned_ffmpeg_processes
    finally:
        camera._active_streams.pop(stream_id, None)
        camera._disconnect_events.pop(stream_id, None)
        camera._spawned_ffmpeg_processes.pop(proc, None)
        camera._stream_last_frame_times.pop(stream_id, None)


@pytest.mark.asyncio
async def test_cleanup_janitor_reaps_stale_external_usb_stream():
    proc = _CleanProc(pid=52011)
    stream_id = "7-ext-deadbeef"
    now = time.time()
    camera._active_streams[stream_id] = proc
    camera._spawned_ffmpeg_processes[proc] = now - 120
    camera._stream_last_frame_times[stream_id] = now - 60
    camera._disconnect_events[stream_id] = asyncio.Event()

    try:
        await asyncio.wait_for(camera.cleanup_orphaned_streams(), timeout=2.0)
        assert proc.returncode is not None
        assert stream_id not in camera._active_streams
    finally:
        camera._active_streams.pop(stream_id, None)
        camera._spawned_ffmpeg_processes.pop(proc, None)
        camera._stream_last_frame_times.pop(stream_id, None)
        camera._disconnect_events.pop(stream_id, None)


@pytest.mark.asyncio
async def test_janitor_reaps_only_owned_detached_processes(monkeypatch):
    detached = _CleanProc(pid=52020)
    streaming = _CleanProc(pid=52021)
    monkeypatch.setattr(camera, "_spawned_ffmpeg_processes", {detached: time.time(), streaming: time.time()})
    monkeypatch.setattr(camera, "_active_streams", {"7-ext-active": streaming})

    with patch("os.listdir", return_value=["52022"]) as scan, patch("os.kill") as kill:
        await camera.cleanup_orphaned_streams()

    scan.assert_not_called()
    kill.assert_not_called()
    assert detached.returncode == -9
    assert streaming.returncode is None
    assert set(camera._spawned_ffmpeg_processes) == {streaming}


@pytest.mark.asyncio
async def test_janitor_keeps_stream_identity_between_processes(monkeypatch):
    process = _CleanProc(pid=52023)
    process.returncode = 0
    stream_id = "7-ext-reconnect"
    disconnected = asyncio.Event()
    monkeypatch.setattr(camera, "_active_streams", {stream_id: process})
    monkeypatch.setattr(camera, "_spawned_ffmpeg_processes", {process: time.time()})
    monkeypatch.setattr(camera, "_disconnect_events", {stream_id: disconnected})

    await camera.cleanup_orphaned_streams()

    assert camera._active_streams[stream_id] is process
    assert not disconnected.is_set()
    assert process not in camera._spawned_ffmpeg_processes
