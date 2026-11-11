"""Verify the streaming route shares an external USB camera between viewers."""

import asyncio
from contextlib import aclosing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.api.routes import camera
from backend.app.services import camera_fanout

JPEG = b"\xff\xd8sample\xff\xd9"


@pytest.fixture
async def usb_camera(monkeypatch):
    printer = SimpleNamespace(
        id=4321,
        model="X1C",
        ip_address="192.0.2.1",
        external_camera_enabled=True,
        external_camera_type="usb",
        external_camera_url="/dev/video0",
    )
    started = []
    active = set()
    frames = asyncio.Queue()
    closing = asyncio.Event()
    close_allowed = asyncio.Event()

    async def upstream(url, _kind, _fps, *, on_process, on_frame, stop_event):
        assert not active
        active.add(url)
        started.append(url)
        try:
            while not stop_event.is_set():
                jpeg = await frames.get()
                on_frame(jpeg)
                yield jpeg
        finally:
            closing.set()
            await close_allowed.wait()
            active.remove(url)

    monkeypatch.setattr(camera, "get_printer_or_404", AsyncMock(return_value=printer))
    monkeypatch.setattr(camera, "generate_mjpeg_stream", upstream)
    try:
        yield SimpleNamespace(
            printer=printer, started=started, active=active, frames=frames, closing=closing, close_allowed=close_allowed
        )
    finally:
        close_allowed.set()
        await camera_fanout.shutdown_all_broadcasters()


async def viewer():
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    db = SimpleNamespace(close=AsyncMock())
    response = await camera.camera_stream(4321, request, db=db, _=None)
    db.close.assert_awaited_once()
    return response.body_iterator


@pytest.mark.asyncio
async def test_two_viewers_share_one_usb_upstream_and_the_same_buffer(usb_camera):
    usb_camera.close_allowed.set()
    async with aclosing(await viewer()) as first, aclosing(await viewer()) as second:
        assert usb_camera.started == []
        usb_camera.frames.put_nowait(JPEG)
        assert await asyncio.wait_for(asyncio.gather(anext(first), anext(second)), 2) == [JPEG, JPEG]
        assert usb_camera.started == ["/dev/video0"]
        assert camera.try_get_active_buffered_frame(4321) == JPEG

        await first.aclose()
        assert await camera.stop_camera_stream(4321, _=None) == {"stopped": 0, "skipped": True}
        usb_camera.frames.put_nowait(JPEG)
        assert await asyncio.wait_for(anext(second), 2) == JPEG

    assert await camera_fanout.shutdown_broadcaster("printer-4321")
    assert usb_camera.active == set()
    assert camera.get_buffered_frame(4321) is None


@pytest.mark.asyncio
async def test_changing_the_camera_waits_until_the_old_device_is_released(usb_camera):
    async with aclosing(await viewer()) as first:
        usb_camera.frames.put_nowait(JPEG)
        assert await asyncio.wait_for(anext(first), 2) == JPEG
        usb_camera.printer.external_camera_url = "/dev/video1"

        async with aclosing(await viewer()) as second:
            replacement = asyncio.create_task(anext(second))
            try:
                await asyncio.wait_for(usb_camera.closing.wait(), 2)
                assert usb_camera.started == ["/dev/video0"]
                assert usb_camera.active == {"/dev/video0"}
                usb_camera.close_allowed.set()
                usb_camera.frames.put_nowait(JPEG)
                assert await asyncio.wait_for(replacement, 2) == JPEG
                assert usb_camera.active == {"/dev/video1"}
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(first), 2)
            finally:
                usb_camera.close_allowed.set()
                if not replacement.done():
                    replacement.cancel()
                    await asyncio.gather(replacement, return_exceptions=True)
