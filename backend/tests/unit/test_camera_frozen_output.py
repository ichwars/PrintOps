"""A live MJPEG response must recover even when it repeats the same JPEG."""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.api.routes import camera
from backend.app.services.camera_profiles import CameraProfile


@pytest.fixture
def streaming(monkeypatch):
    clock = [1000.0]
    sessions = []
    opened = []
    releases = AsyncMock()
    restarts = AsyncMock(return_value=True)
    monkeypatch.setattr(camera.go2rtc_registry, "acquire", AsyncMock(return_value="printer-999"))
    monkeypatch.setattr(camera.go2rtc_registry, "release", releases)
    # Raising=False keeps the regression runnable before the recovery hook exists.
    monkeypatch.setattr(camera.go2rtc_registry, "restart", restarts, raising=False)
    monkeypatch.setattr(camera, "monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(
        camera, "get_camera_profile", lambda _: CameraProfile(rtsp_reconnect_max=4, rtsp_reconnect_delay=0)
    )

    class Response:
        status_code = 200

        async def aiter_bytes(self, *_):
            for frame in sessions.pop(0):
                clock[0] += 1.0
                yield frame

    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def stream(self, *_):
            opened.append(1)
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=Response())
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

    monkeypatch.setattr(camera.httpx, "AsyncClient", Client)
    yield sessions, opened, restarts, releases
    camera._last_frames.pop(999, None)


def jpeg(n):
    return b"\xff\xd8" + str(n).encode() + b"\xff\xd9"


async def collect(count):
    stream = camera.generate_go2rtc_mjpeg_stream(MagicMock(), "192.0.2.1", "P2S", printer_id=999)
    frames = []
    try:
        async for chunk in stream:
            frames.append(chunk.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
            if len(frames) >= count:
                break
    finally:
        with suppress(Exception):
            await stream.aclose()
    return frames


@pytest.mark.asyncio
async def test_frozen_output_restarts_shared_source_and_keeps_viewer(streaming):
    sessions, opened, restart, release = streaming
    sessions.extend([[jpeg(1)] * 100, [jpeg(n) for n in range(2, 70)]])
    frames = await asyncio.wait_for(collect(50), 5)
    restart.assert_awaited_once_with(999)
    release.assert_awaited_once_with(999)
    assert len(opened) == 2
    assert 20 <= frames.count(jpeg(1)) <= 23
    assert frames[-1] != jpeg(1)


@pytest.mark.asyncio
async def test_moving_picture_and_short_repeats_do_not_restart(streaming):
    sessions, opened, restart, _ = streaming
    sessions.append([jpeg(n // 5) for n in range(150)])
    assert len(await collect(150)) == 150
    restart.assert_not_awaited()
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_same_picture_after_restart_gets_long_still_scene_interval(streaming):
    sessions, opened, restart, _ = streaming
    sessions.extend([[jpeg(1)] * 100, [jpeg(1)] * 400, [jpeg(n) for n in range(2, 80)]])
    frames = await collect(250)
    assert len(frames) == 250
    restart.assert_awaited_once()
    assert len(opened) == 2


@pytest.mark.asyncio
async def test_still_scene_is_rechecked_and_movement_resets_interval(streaming):
    sessions, opened, restart, _ = streaming
    sessions.extend(
        [[jpeg(0)] * 100, [jpeg(0)] * 400, [jpeg(0), jpeg(1)] + [jpeg(1)] * 100, [jpeg(n) for n in range(2, 80)]]
    )
    frames = await collect(380)
    assert restart.await_count == 3
    assert len(opened) == 4
    assert frames[-1] != jpeg(1)


@pytest.mark.asyncio
async def test_source_restart_preserves_references_and_existing_tls_relay(monkeypatch):
    from backend.app.services import go2rtc_registry as registry

    relay = MagicMock()
    reg = registry._Registration(
        "printer-123456", relay, ["rtsp://127.0.0.1:45678/live", "ffmpeg:printer-123456#video=mjpeg"]
    )
    reg.refcount = 2
    monkeypatch.setitem(registry._registrations, 123456, reg)
    remove = AsyncMock()
    ensure = AsyncMock(return_value=True)
    monkeypatch.setattr(registry.go2rtc_client, "remove_stream", remove)
    monkeypatch.setattr(registry.go2rtc_client, "ensure_stream_multi", ensure)
    try:
        assert await registry.restart(123456)
        remove.assert_awaited_once_with("printer-123456")
        ensure.assert_awaited_once_with("printer-123456", reg.source_urls)
        assert registry._registrations[123456] is reg
        assert reg.refcount == 2
        relay.close.assert_not_called()
    finally:
        registry._registrations.pop(123456, None)


@pytest.mark.asyncio
async def test_restart_failure_keeps_registry_ownership_for_retry(monkeypatch):
    from backend.app.services import go2rtc_registry as registry

    reg = registry._Registration("printer-123456", None, ["rtsp://127.0.0.1:45678/live"])
    reg.refcount = 1
    monkeypatch.setitem(registry._registrations, 123456, reg)
    monkeypatch.setattr(registry.go2rtc_client, "remove_stream", AsyncMock())
    monkeypatch.setattr(registry.go2rtc_client, "ensure_stream_multi", AsyncMock(return_value=False))
    try:
        assert not await registry.restart(123456)
        assert reg.refcount == 1
        assert registry._registrations[123456] is reg
    finally:
        registry._registrations.pop(123456, None)
