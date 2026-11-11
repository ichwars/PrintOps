"""One-shot camera operations cannot leave an encoder or capture running."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.services import camera, external_camera, layer_timelapse
from backend.app.utils.ffmpeg_limits import STITCH_SCALE_FILTER, X264_BOUNDED_ARGS


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", ["usb", "external_rtsp", "printer_rtsp", "video_frame"])
async def test_cancelling_a_capture_stops_and_reaps_ffmpeg(capture, monkeypatch, tmp_path):
    started = asyncio.Event()

    async def communicate():
        started.set()
        await asyncio.Future()

    process = SimpleNamespace(pid=4321, returncode=None, communicate=communicate, kill=Mock(), wait=AsyncMock())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    monkeypatch.setattr(camera, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(external_camera, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(external_camera, "safe_usb_device_path", lambda _: "/dev/video0")
    prepared = SimpleNamespace(url="rtsp://127.0.0.1/fixture", close=AsyncMock())
    monkeypatch.setattr(external_camera, "prepare_external_camera_url", AsyncMock(return_value=prepared))
    proxy = SimpleNamespace(close=Mock(), wait_closed=AsyncMock())
    monkeypatch.setattr(camera, "create_tls_proxy", AsyncMock(return_value=(18554, proxy)))

    if capture == "usb":
        operation = external_camera._capture_usb_frame("/dev/video0", 15)
    elif capture == "external_rtsp":
        operation = external_camera._capture_rtsp_frame("rtsp://camera.example.test", 15)
    elif capture == "printer_rtsp":
        operation = camera.capture_camera_frame_bytes("192.0.2.1", "fixture", "X1C")
    else:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fixture")
        operation = camera.extract_video_last_frame(video, tmp_path / "frame.jpg")

    task = asyncio.create_task(operation)
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    if capture == "external_rtsp":
        prepared.close.assert_awaited_once()
    if capture == "printer_rtsp":
        proxy.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_layer_stitch_passes_encoder_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(layer_timelapse.settings, "base_dir", tmp_path)
    monkeypatch.setattr(layer_timelapse, "get_ffmpeg_path", lambda: "ffmpeg")
    process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    session = layer_timelapse.TimelapseSession(1, 1, "http://fixture.test", "snapshot")
    (session.frames_dir / "layer_00001.jpg").write_bytes(b"frame")
    session.frame_count = 1
    assert await session.stitch(tmp_path / "video.mp4")
    cmd = spawn.await_args.args
    assert cmd[cmd.index("-vf") + 1] == STITCH_SCALE_FILTER
    assert cmd[-len(X264_BOUNDED_ARGS) - 1 : -1] == X264_BOUNDED_ARGS
