"""The subprocess is killed and reaped on timeout or an editor cancellation."""

import asyncio
import sys
from pathlib import Path

import pytest

from backend.app.services import timelapse_processor as processor


@pytest.mark.asyncio
async def test_probe_timeout_reaps_child():
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    with pytest.raises(TimeoutError):
        await processor._communicate(child, 0.03)
    assert child.returncode is not None


@pytest.mark.asyncio
async def test_cancel_encode_reaps_child_and_removes_partial_file(monkeypatch, tmp_path: Path):
    create_process = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []

    async def start(*_args, **kwargs):
        child = await create_process(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        children.append(child)
        launched.set()
        return child

    monkeypatch.setattr(processor, "get_ffmpeg_path", lambda: sys.executable)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    input_file = tmp_path / "input.mp4"
    output = tmp_path / "out.mp4"
    output.write_bytes(b"partial")
    job = asyncio.create_task(processor.TimelapseProcessor(input_file).process(output, trim_end=3))
    await asyncio.wait_for(launched.wait(), 2)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert children[0].returncode is not None and not output.exists()


def test_usb_listing_sorts_canonical_capture_candidates(tmp_path, monkeypatch):
    from backend.app.services.external_camera import list_usb_cameras

    for node in ("video0", "video1", "video2", "video10", "video001", "video100", "video-input"):
        (tmp_path / node).touch()
    monkeypatch.setattr("backend.app.services.external_camera.shutil.which", lambda _tool: None)
    assert [camera["device"] for camera in list_usb_cameras(tmp_path)] == ["/dev/video0", "/dev/video2", "/dev/video10"]
