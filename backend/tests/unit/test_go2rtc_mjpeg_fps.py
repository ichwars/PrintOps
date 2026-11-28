"""Per-viewer fps throttling for the go2rtc MJPEG fan-out path.

go2rtc's MJPEG derivative runs at the camera's native frame rate (commonly
~30fps) and that upstream is *shared*: one broadcaster per printer feeds
every viewer. Throttling must therefore happen at each subscriber's exit
(``iter_subscriber(max_fps=...)``) — throttling the shared upstream would pin
every later viewer to the fps of whoever created the broadcaster. These
tests pin the per-viewer throttle, the finite upstream read timeout and the
adaptive frozen-frame watchdog.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.api.routes import camera
from backend.app.services import camera_fanout
from backend.app.services.camera_fanout import iter_subscriber
from backend.app.services.camera_profiles import CameraProfile


@pytest.fixture
def streaming(monkeypatch):
    clock = [1000.0]
    sessions = []
    opened = []
    client_kwargs = []
    releases = AsyncMock()
    monkeypatch.setattr(camera.go2rtc_registry, "acquire", AsyncMock(return_value="printer-999"))
    monkeypatch.setattr(camera.go2rtc_registry, "release", releases)
    monkeypatch.setattr(camera.go2rtc_registry, "restart", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(camera, "monotonic", lambda: clock[0])

    class Response:
        status_code = 200

        async def aiter_bytes(self, *_):
            for dt, frame in sessions.pop(0):
                clock[0] += dt
                yield frame

    class Client:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

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
    yield SimpleNamespace(sessions=sessions, opened=opened, client_kwargs=client_kwargs, releases=releases)
    camera._last_frames.pop(999, None)


def jpeg(n):
    return b"\xff\xd8" + str(n).encode() + b"\xff\xd9"


def payload(chunk):
    """Extract the JPEG payload from a multipart chunk."""
    return chunk.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n")


async def drain(monkeypatch, source, fps, reconnect_max=0):
    monkeypatch.setattr(
        camera,
        "get_camera_profile",
        lambda _: CameraProfile(rtsp_reconnect_max=reconnect_max, rtsp_reconnect_delay=0),
    )
    stream = camera.generate_go2rtc_mjpeg_stream(source, "192.0.2.1", "P2S", fps=fps, printer_id=999)
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return chunks


class FakeBroadcaster:
    """Just enough of MjpegBroadcaster for iter_subscriber's finally block."""

    def __init__(self):
        self.unsubscribed = []

    async def unsubscribe(self, queue):
        self.unsubscribed.append(queue)
        return 0


def subscribe(chunks, times=None, max_fps=None, monkeypatch=None):
    """Queue scripted chunks + the upstream-gone sentinel, return (generator, broadcaster)."""
    if times is not None:
        assert monkeypatch is not None
        clock = iter(times)
        monkeypatch.setattr(camera_fanout, "monotonic", lambda: next(clock))
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)
    queue.put_nowait(camera_fanout._UPSTREAM_GONE)
    broadcaster = FakeBroadcaster()
    return iter_subscriber(broadcaster, queue, max_fps=max_fps), broadcaster


async def collect_all(generator):
    frames = []
    async for chunk in generator:
        frames.append(chunk)
    return frames


@pytest.mark.asyncio
async def test_max_fps_drops_frames_that_arrive_too_fast(monkeypatch):
    # The shared upstream delivers 10 frames at 5x the requested fps=2 (one
    # per 0.2s, the viewer's interval is 0.5s). Only the 1st, 4th, 7th and
    # 10th frame may pass. The first frame goes out immediately even though
    # the clock already reads 100.0 — no stale/black start for a viewer that
    # joins a long-running native-rate stream.
    times = [100.0 + 0.2 * i for i in range(10)]
    generator, _ = subscribe(
        [f"frame-{n}".encode() for n in range(1, 11)], times=times, max_fps=2, monkeypatch=monkeypatch
    )

    frames = await collect_all(generator)

    assert frames == [b"frame-1", b"frame-4", b"frame-7", b"frame-10"]


@pytest.mark.asyncio
async def test_first_part_of_subscription_passes_immediately(monkeypatch):
    # First part at any clock value must pass (last_sent starts unset); the
    # second part half an interval later must not.
    generator, broadcaster = subscribe([b"first", b"second"], times=[500.0, 500.1], max_fps=2, monkeypatch=monkeypatch)

    frames = await collect_all(generator)

    assert frames == [b"first"]
    assert broadcaster.unsubscribed


@pytest.mark.asyncio
async def test_upstream_gone_sentinel_is_never_dropped(monkeypatch):
    # The sentinel terminates the subscription even when it arrives "too
    # early" — dropping it would hang the viewer on an empty queue forever.
    clock = iter([0.0, 0.0])
    monkeypatch.setattr(camera_fanout, "monotonic", lambda: next(clock))
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    queue.put_nowait(b"frame-1")
    queue.put_nowait(camera_fanout._UPSTREAM_GONE)
    broadcaster = FakeBroadcaster()

    frames = await collect_all(iter_subscriber(broadcaster, queue, max_fps=2))

    assert frames == [b"frame-1"]
    assert broadcaster.unsubscribed == [queue]


@pytest.mark.asyncio
async def test_max_fps_none_keeps_unthrottled_behavior(monkeypatch):
    # max_fps=None is the old behavior: every frame is forwarded, however
    # fast the upstream delivers it.
    generator, _ = subscribe([b"f1", b"f2", b"f3", b"f4", b"f5"], max_fps=None, monkeypatch=monkeypatch)

    frames = await collect_all(generator)

    assert frames == [b"f1", b"f2", b"f3", b"f4", b"f5"]


@pytest.mark.asyncio
async def test_upstream_read_timeout_is_finite(streaming, monkeypatch):
    # A stalled go2rtc upstream must not block the read forever (read=None
    # froze the picture for the viewer); the read timeout stays aligned with
    # the reconnect cadence at 30s.
    streaming.sessions.append([(0.0, jpeg(1))])
    await drain(monkeypatch, MagicMock(), fps=10)

    (kwargs,) = streaming.client_kwargs
    assert kwargs["timeout"].read == 30.0


@pytest.mark.asyncio
async def test_builtin_sources_get_adaptive_frozen_watchdog(streaming, monkeypatch):
    # Built-in cameras see byte-identical MJPEG frames in still scenes too
    # (idle printer, closed chamber) — the watchdog must adapt for every
    # source, not just ExternalRtspSource, or it restarts the source every
    # frozen_seconds in a still scene.
    created = []

    class SpyWatchdog(camera.FrozenFrameWatchdog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(kwargs)

    monkeypatch.setattr(camera, "FrozenFrameWatchdog", SpyWatchdog)
    streaming.sessions.append([(0.0, jpeg(1)), (0.0, jpeg(2)), (0.0, jpeg(3))])
    await drain(monkeypatch, MagicMock(), fps=10)

    assert created and created[0].get("adaptive") is True
    streaming.releases.assert_awaited_once_with(999)


@pytest.mark.asyncio
async def test_go2rtc_upstream_forwards_every_frame_to_the_broadcaster(streaming, monkeypatch):
    # The upstream must deliver its *native* rate to the fan-out — the
    # per-viewer fps throttle lives in iter_subscriber, not here. Pin that
    # the upstream does not drop anything even at a low viewer fps.
    streaming.sessions.append([(0.0, jpeg(n)) for n in range(1, 11)])
    chunks = await drain(monkeypatch, MagicMock(), fps=1)

    assert [payload(c) for c in chunks] == [jpeg(n) for n in range(1, 11)]
