"""Shared, reference-counted go2rtc stream registration per printer.

The MJPEG fan-out path (``generate_go2rtc_mjpeg_stream``) and the MSE
WebSocket proxy need the *same* go2rtc stream (``printer-<id>``) registered
with the *same* producer list. go2rtc's ``PUT /api/streams`` replaces a
stream's whole producer list on every call rather than merging — if two
consumers registered independently (each with its own local bridge/proxy
port), whichever registered second would silently orphan the first one's
connection and swap every existing consumer over to a new upstream.

This module is the single place that resolves a printer's camera (via
``camera_source.CameraSource``) and registers the result with go2rtc, so
all consumers share one bridge/proxy and a grace period (mirroring
``camera_fanout``'s behaviour) that survives a page refresh without a
needless reconnect. Protocol-specific work (TLS proxy, chamber-image
bridge, external-URL rewriting) lives in ``camera_source.py`` — this
module only owns the registration lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from backend.app.services import go2rtc_client

if TYPE_CHECKING:
    from backend.app.services.camera_source import CameraSource

logger = logging.getLogger(__name__)

# Same rationale as camera_fanout._GRACE_SECONDS: absorb a quick reconnect
# (tab refresh, MSE-to-MJPEG fallback swap) without tearing down and
# re-establishing the printer-facing connection.
_GRACE_SECONDS = 5.0


class _Registration:
    __slots__ = ("go2rtc_name", "local_server", "refcount", "grace_task", "registered_at")

    def __init__(self, go2rtc_name: str, local_server: asyncio.Server | None) -> None:
        self.go2rtc_name = go2rtc_name
        self.local_server = local_server
        self.refcount = 0
        self.grace_task: asyncio.Task | None = None
        self.registered_at = time.time()


_registrations: dict[int, _Registration] = {}
_lock = asyncio.Lock()


def is_registered(printer_id: int) -> bool:
    """True iff printer_id has a live (non-torn-down) go2rtc registration.

    Synchronous, lock-free snapshot check — used by camera.py's
    is_stream_active() so callers (snapshot capture, diagnostics) recognise
    an MSE-only viewer as a live stream, not just an MJPEG one. A registered
    entry always means go2rtc currently holds the printer's one allowed
    camera connection, whether or not anything has actually flushed a
    reference-count decrement to zero yet.
    """
    return printer_id in _registrations


def registered_since(printer_id: int) -> float | None:
    """Unix timestamp the current registration was created, or None.

    Used by /camera/stream-info to compute stream uptime for an MSE-only
    session — those don't go through the MJPEG generator's
    ``_stream_start_times`` bookkeeping at all.
    """
    reg = _registrations.get(printer_id)
    return reg.registered_at if reg is not None else None


async def acquire(printer_id: int, source: CameraSource) -> str:
    """Ensure `printer_id`'s go2rtc stream is registered; return its go2rtc name.

    `source` resolves the actual printer-facing connection — see
    camera_source.py for the built-in and external implementations.
    Reference-counted: every successful call MUST be paired with exactly
    one ``release(printer_id)``, typically in a ``try/finally``. Raises
    ``RuntimeError`` if go2rtc is unreachable — callers should turn that
    into a user-facing stream error rather than letting it propagate raw.
    """
    async with _lock:
        reg = _registrations.get(printer_id)
        if reg is not None:
            if reg.grace_task is not None and not reg.grace_task.done():
                reg.grace_task.cancel()
                reg.grace_task = None
            reg.refcount += 1
            return reg.go2rtc_name

        go2rtc_name = go2rtc_client.stream_name(printer_id)
        result = await source.resolve(go2rtc_name)

        registered = await go2rtc_client.ensure_stream_multi(go2rtc_name, result.go2rtc_sources)
        if not registered:
            if result.local_server is not None:
                result.local_server.close()
                await result.local_server.wait_closed()
            raise RuntimeError("go2rtc unavailable")

        new_reg = _Registration(go2rtc_name, result.local_server)
        new_reg.refcount = 1
        _registrations[printer_id] = new_reg
        return go2rtc_name


async def release(printer_id: int) -> None:
    """Release one reference. Tears down after a short grace period once
    the refcount reaches zero, matching camera_fanout's page-refresh
    tolerance."""
    async with _lock:
        reg = _registrations.get(printer_id)
        if reg is None:
            return
        reg.refcount -= 1
        if reg.refcount > 0:
            return
        reg.grace_task = asyncio.create_task(
            _grace_then_teardown(printer_id), name=f"go2rtc-registry-grace-{printer_id}"
        )


async def _grace_then_teardown(printer_id: int) -> None:
    try:
        await asyncio.sleep(_GRACE_SECONDS)
    except asyncio.CancelledError:
        return  # A new consumer acquired during the grace window.

    async with _lock:
        reg = _registrations.get(printer_id)
        if reg is None or reg.refcount > 0:
            return
        del _registrations[printer_id]

    if reg.local_server is not None:
        reg.local_server.close()
        await reg.local_server.wait_closed()
    await go2rtc_client.remove_stream(reg.go2rtc_name)
    logger.debug("go2rtc registration for printer %s torn down", printer_id)
