"""Loopback-only MJPEG-over-HTTP bridge for the A1/P1 chamber-image protocol.

A1, A1 Mini, P1P and P1S don't speak RTSP — their camera uses a proprietary
binary protocol on port 6000 (see ``camera.read_chamber_image_frame``).
go2rtc has no native support for that protocol, so unlike X1/X2D/H2/P2's
RTSP feed it can't ingest the chamber-image stream directly.

This module re-exposes the chamber-image feed as plain MJPEG-over-HTTP on
loopback, which go2rtc *can* ingest natively — its HTTP source
auto-detects MJPEG, matching go2rtc's own documented pattern for a
"stream will be proxied without modification" MJPEG source. That gives
A1/P1 owners the same go2rtc-backed fan-out, MJPEG delivery, and
diagnostics endpoint as RTSP models — see go2rtc_registry.py, which starts
one of these bridges per printer instead of a TLS proxy when
``is_chamber_image_model()`` is true.

A bridge instance serves exactly one upstream chamber-image connection
(these printers allow only one at a time, same constraint as RTSP models)
and expects exactly one downstream consumer: go2rtc's own internal HTTP
puller. It is not a general-purpose HTTP server — no routing, no
concurrent-client fan-out (go2rtc does that on its side once it has
ingested the stream via this bridge).

Chamber-image cameras only ever produce JPEG frames — there is no H.264
elementary stream to stream-copy the way RTSP models' MSE path does. MSE
therefore stays unavailable for A1/P1 for now (see camera_mse_stream's
chamber-image rejection); offering it would mean go2rtc transcoding JPEG
to H.264 itself, a real re-encode cost that hasn't been asked for.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from backend.app.services.camera import generate_chamber_image_stream, read_next_chamber_frame

logger = logging.getLogger(__name__)

_MJPEG_RESPONSE_HEADERS = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    b"Cache-Control: no-cache\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)

_BAD_GATEWAY = b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n"

# How long to wait for the incoming HTTP request line/headers before giving
# up on a connection. Generous but bounded — this is loopback-only traffic
# from go2rtc itself, not a real network client.
_REQUEST_TIMEOUT = 5.0


async def start_bridge(ip_address: str, access_code: str, fps: int = 5) -> tuple[int, asyncio.Server]:
    """Start a loopback MJPEG bridge for one printer's chamber-image feed.

    Returns ``(port, server)``; caller must close the server when done.
    The upstream chamber-image connection is opened lazily, per incoming
    HTTP request (mirroring ``camera.create_tls_proxy``'s pattern) — in
    practice go2rtc makes exactly one such request and keeps it open for
    the life of the registration.
    """

    async def _drain_request_headers(reader: asyncio.StreamReader) -> None:
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                return

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        chamber_writer: asyncio.StreamWriter | None = None
        try:
            try:
                await asyncio.wait_for(_drain_request_headers(reader), timeout=_REQUEST_TIMEOUT)
            except TimeoutError:
                return

            connection = await generate_chamber_image_stream(ip_address, access_code, fps)
            if connection is None:
                writer.write(_BAD_GATEWAY)
                await writer.drain()
                return

            chamber_reader, chamber_writer = connection
            writer.write(_MJPEG_RESPONSE_HEADERS)
            await writer.drain()

            frame_interval = 1.0 / fps if fps > 0 else 0.2
            loop = asyncio.get_event_loop()
            last_frame_time = 0.0

            while True:
                frame = await read_next_chamber_frame(chamber_reader, timeout=30.0)
                if frame is None:
                    break

                now = loop.time()
                if now - last_frame_time < frame_interval:
                    continue
                last_frame_time = now

                writer.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                    b"\r\n" + frame + b"\r\n"
                )
                await writer.drain()
        except (ConnectionError, OSError, TimeoutError, asyncio.CancelledError):
            pass
        finally:
            if chamber_writer is not None:
                chamber_writer.close()
                with contextlib.suppress(OSError):
                    await chamber_writer.wait_closed()
            if not writer.is_closing():
                writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    logger.debug("Chamber-image MJPEG bridge for %s listening on 127.0.0.1:%s", ip_address, port)
    return port, server
