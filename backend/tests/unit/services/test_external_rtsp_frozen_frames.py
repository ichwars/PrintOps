"""Exercise the external RTSP watchdog and reconnect loop together."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.services import camera, external_camera
from backend.app.services.frozen_frame_watchdog import FrozenFrameWatchdog

JPEG = b"\xff\xd8picture\xff\xd9"
OTHER_JPEG = b"\xff\xd8movement\xff\xd9"


def test_external_camera_adapts_to_slow_changes_and_still_scenes():
    watch = FrozenFrameWatchdog(adaptive=True)
    assert not watch.observe(JPEG, 0)
    assert watch.observe(JPEG, 21)

    watch.begin_session()
    assert not watch.observe(JPEG, 22)
    assert not watch.observe(JPEG, 321)
    assert watch.observe(JPEG, 323)

    watch.begin_session()
    assert not watch.observe(OTHER_JPEG, 324)
    assert not watch.observe(OTHER_JPEG, 623)
    assert watch.observe(OTHER_JPEG, 625)


@pytest.mark.asyncio
async def test_external_rtsp_restarts_repeated_freezes_and_closes_each_session(monkeypatch):
    clock = [0.0]
    processes = []
    connections = []

    async def prepare(*_args):
        connection = SimpleNamespace(url="rtsp://127.0.0.1/fixture", close=AsyncMock())
        connections.append(connection)
        return connection

    async def spawn(*_args, **_kwargs):
        reads = iter((JPEG, JPEG) if len(processes) < 5 else ())
        process = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0))

        async def read(_size):
            clock[0] += 301
            return next(reads, b"")

        def terminate():
            process.returncode = 0

        process.stdout = SimpleNamespace(read=read)
        process.terminate = Mock(side_effect=terminate)
        processes.append(process)
        return process

    monkeypatch.setattr(external_camera, "monotonic", lambda: clock[0])
    monkeypatch.setattr(external_camera, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(external_camera, "prepare_external_camera_url", prepare)
    monkeypatch.setattr(camera, "rtsp_socket_timeout_flag", lambda: "timeout")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    frames = [frame async for frame in external_camera.generate_mjpeg_stream("rtsp://camera.test", "rtsp")]

    assert frames == [external_camera._format_mjpeg_frame(JPEG)] * 5
    assert len(processes) == len(connections) == 6
    for process, connection in zip(processes, connections, strict=True):
        process.terminate.assert_called_once()
        process.wait.assert_awaited_once()
        connection.close.assert_awaited_once()
