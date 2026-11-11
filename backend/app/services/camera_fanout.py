"""MJPEG fan-out broadcaster for camera streams.

Most Bambu Lab printers only allow one concurrent camera connection: the
RTSP socket on X1/H2/P2 models, the chamber-image socket on port 6000 on
A1/P1 models. Without fan-out, opening a second viewer either fails or
kicks the first viewer off — see issue #1089.

This module owns a single upstream connection per printer and pushes each
frame to N independent subscriber queues. New viewers tap the existing
upstream; no new printer connection is opened. When the last subscriber
leaves, the upstream is torn down after a short grace window so that a
quick page refresh or second-tab open does not pay a reconnect.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing

logger = logging.getLogger(__name__)

# How long to keep the upstream pump alive after the last subscriber leaves.
# A short grace window absorbs page refreshes and "open camera in new tab"
# without paying a fresh ffmpeg/RTSP handshake (which can take several seconds
# on some firmwares and is the very reconnect cost we are trying to avoid).
_GRACE_SECONDS = 5.0

# Per-subscriber queue depth. Small on purpose: if a viewer can't keep up
# with the printer's frame rate we drop frames for that viewer rather than
# blocking the broadcaster. Live video — old frames have no value.
_SUBSCRIBER_QUEUE_SIZE = 4

# Sentinel pushed to subscriber queues when the upstream pump exits, so each
# subscriber's read loop can break out cleanly instead of hanging on get().
_UPSTREAM_GONE = b""

UpstreamFactory = Callable[[asyncio.Event], AsyncGenerator[bytes, None]]


class MjpegBroadcaster:
    """Single upstream MJPEG stream, fanned out to N subscribers."""

    def __init__(self, key: str, factory: UpstreamFactory, *, source_identity: tuple[str, ...] = ()) -> None:
        self._key = key
        self._factory = factory
        self.source_identity = source_identity
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._lock = asyncio.Lock()
        self._pump_task: asyncio.Task | None = None
        self._grace_task: asyncio.Task | None = None
        self._teardown_task: asyncio.Task | None = None
        # Disconnect event passed to the upstream generator so we can ask it to
        # stop reconnecting when the last subscriber leaves.
        self._upstream_disconnect = asyncio.Event()
        self._stopped = False

    @property
    def key(self) -> str:
        return self._key

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def stopped(self) -> bool:
        return self._stopped

    async def subscribe(self) -> asyncio.Queue[bytes]:
        """Add a subscriber and ensure the upstream pump is running."""
        async with self._lock:
            if self._stopped:
                raise RuntimeError(f"broadcaster {self._key!r} is stopped")

            # Cancel any pending grace-window shutdown — a viewer just rejoined.
            if self._grace_task is not None and not self._grace_task.done():
                self._grace_task.cancel()
                self._grace_task = None

            queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
            self._subscribers.append(queue)

            if self._pump_task is None or self._pump_task.done():
                # Reset the disconnect signal in case a previous pump set it.
                self._upstream_disconnect = asyncio.Event()
                self._pump_task = asyncio.create_task(self._pump(), name=f"camera-fanout-pump-{self._key}")
            return queue

    async def unsubscribe(self, queue: asyncio.Queue[bytes]) -> int:
        """Remove a subscriber and return the remaining count (atomic).

        If this was the last subscriber, schedule grace shutdown.
        """
        async with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                return len(self._subscribers)  # Already removed (e.g. force_shutdown)
            remaining = len(self._subscribers)
            if remaining == 0 and not self._stopped:
                # Last subscriber left. Schedule grace-window teardown.
                self._grace_task = asyncio.create_task(self._grace_then_stop(), name=f"camera-fanout-grace-{self._key}")
            return remaining

    async def force_shutdown(self) -> None:
        """Tear down immediately, kick all subscribers. Idempotent."""
        await self._stop(only_if_idle=False)

    async def _grace_then_stop(self) -> None:
        try:
            await asyncio.sleep(_GRACE_SECONDS)
        except asyncio.CancelledError:
            return  # New subscriber arrived during grace
        await self._stop(only_if_idle=True)

    async def _stop(self, *, only_if_idle: bool) -> bool:
        """Publish the teardown task before releasing the lock to other callers."""
        async with self._lock:
            if only_if_idle and self._subscribers:
                return False
            if not self._stopped:
                self._stopped = True
                self._upstream_disconnect.set()
                for queue in self._subscribers:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(_UPSTREAM_GONE)
                self._subscribers.clear()
                if self._grace_task is not None and self._grace_task is not asyncio.current_task():
                    self._grace_task.cancel()
                self._grace_task = None
                self._teardown_task = asyncio.create_task(self._await_pump_cancellation(self._pump_task))
                self._pump_task = None
            teardown = self._teardown_task
        assert teardown is not None
        await asyncio.shield(teardown)
        return True

    @property
    def torn_down(self) -> bool:
        return self._teardown_task is not None and self._teardown_task.done()

    async def _await_pump_cancellation(self, pump_task: asyncio.Task | None) -> None:
        if pump_task is None or pump_task.done():
            return
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):
            # Pump exceptions are already logged inside _pump; swallow here so
            # teardown can never propagate a stray crash.
            pass

    async def _pump(self) -> None:
        """Drive the upstream generator and broadcast each chunk."""
        try:
            async with aclosing(self._factory(self._upstream_disconnect)) as frames:
                async for chunk in frames:
                    async with self._lock:
                        for queue in self._subscribers:
                            if not queue.full():
                                queue.put_nowait(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Camera fan-out pump crashed for %s", self._key)
        finally:
            # Pump is exiting — wake up any subscribers still hanging on get().
            async with self._lock:
                for queue in self._subscribers:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(_UPSTREAM_GONE)


# Global registry. Keyed by printer_id (as str) so a chamber-mode printer
# and an RTSP-mode printer can never collide on the same key.
_broadcasters: dict[str, MjpegBroadcaster] = {}
_registry_lock = asyncio.Lock()


async def get_or_create_broadcaster(
    key: str, factory: UpstreamFactory, *, source_identity: tuple[str, ...] = ()
) -> MjpegBroadcaster:
    """Return the live broadcaster for `key`, creating one if needed.

    A broadcaster that has been stopped (force shutdown or grace timeout) is
    replaced with a fresh instance — the caller will subscribe to the new one.
    """
    while True:
        async with _registry_lock:
            existing = _broadcasters.get(key)
            if existing is None or existing.torn_down:
                broadcaster = MjpegBroadcaster(key, factory, source_identity=source_identity)
                _broadcasters[key] = broadcaster
                return broadcaster
            if not existing.stopped and existing.source_identity == source_identity:
                return existing
        await existing.force_shutdown()


async def shutdown_broadcaster(key: str, *, only_if_idle: bool = False) -> bool | None:
    """Return True if stopped, False if absent, and None if viewers remain."""
    async with _registry_lock:
        bc = _broadcasters.get(key)
    if bc is None:
        return False
    if not await bc._stop(only_if_idle=only_if_idle):
        return None
    async with _registry_lock:
        if _broadcasters.get(key) is bc:
            _broadcasters.pop(key)
    return True


async def shutdown_all_broadcasters() -> None:
    """Tear down every broadcaster (for app shutdown)."""
    async with _registry_lock:
        bcs = list(_broadcasters.values())
        _broadcasters.clear()
    await asyncio.gather(*(bc.force_shutdown() for bc in bcs), return_exceptions=True)


def active_broadcaster_keys() -> list[str]:
    """Snapshot of keys with a live (non-stopped) broadcaster. For diagnostics."""
    return [k for k, bc in _broadcasters.items() if not bc.stopped]


def active_source_identity(key: str) -> tuple[str, ...] | None:
    broadcaster = _broadcasters.get(key)
    return broadcaster.source_identity if broadcaster is not None and not broadcaster.stopped else None


# AsyncGenerator helper — turns a subscriber queue into an async generator
# that yields MJPEG chunks until the upstream signals it's gone.


async def iter_subscriber(
    broadcaster: MjpegBroadcaster,
    queue: asyncio.Queue[bytes],
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    on_unsubscribe: Callable[[int], None] | None = None,
    idle_check_seconds: float = 30.0,
) -> AsyncGenerator[bytes, None]:
    """Yield chunks from a subscriber queue until upstream ends or client leaves.

    Always unsubscribes from the broadcaster on exit, even on cancellation.
    The optional ``on_unsubscribe`` callback receives the post-unsubscribe
    subscriber count — useful for accurate detach-log lines that don't race
    with concurrent unsubscribes.
    """
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=idle_check_seconds)
            except asyncio.TimeoutError:
                # No frame in 30s — check whether the client is still there.
                # If yes, keep waiting; if no, bail out.
                if is_disconnected is not None and await is_disconnected():
                    break
                continue
            if chunk == _UPSTREAM_GONE:
                break
            yield chunk
            if is_disconnected is not None and await is_disconnected():
                break
    finally:
        remaining = await broadcaster.unsubscribe(queue)
        if on_unsubscribe is not None:
            try:
                on_unsubscribe(remaining)
            except Exception:
                logger.exception("on_unsubscribe callback raised")
