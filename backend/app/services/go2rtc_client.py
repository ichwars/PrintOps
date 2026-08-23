"""Thin async client for the embedded go2rtc restreaming sidecar.

go2rtc (https://github.com/AlexxIT/go2rtc) is started by
``deploy/docker-entrypoint.sh`` alongside uvicorn and listens on loopback
only (see ``Settings.go2rtc_api_url``). It ingests a camera source exactly
once per printer and re-serves it as MJPEG/MSE/WebRTC/RTSP to any number of
consumers, replacing PrintOps's previous per-viewer ffmpeg re-encode.

Streams are managed at runtime through go2rtc's REST API rather than a
static YAML file, so a printer's stream only exists in go2rtc while
something in PrintOps is actually using it — mirrors the lifecycle
``camera_fanout.MjpegBroadcaster`` already applies to its subscribers.
"""

from __future__ import annotations

import logging

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Short timeout: this is a loopback call to a local sidecar process, not a
# network request. If it doesn't answer quickly something is wrong with the
# sidecar itself and callers should fail fast rather than hang a viewer.
_TIMEOUT = httpx.Timeout(5.0)


def stream_name(printer_id: int) -> str:
    """Canonical go2rtc stream name for a printer's built-in camera."""
    return f"printer-{printer_id}"


async def ensure_stream(name: str, source_url: str) -> bool:
    """Register `source_url` as go2rtc source `name` if not already present.

    Idempotent: go2rtc's `PUT /api/streams` (add-or-replace semantics) is
    used so repeated calls for the same name/URL are cheap no-ops from the
    caller's perspective. Returns True on success, False if go2rtc could not
    be reached or rejected the request — callers should fall back to
    reporting a stream error rather than raising, since a camera hiccup must
    not take down the request handler.
    """
    return await ensure_stream_multi(name, [source_url])


async def ensure_stream_multi(name: str, source_urls: list[str]) -> bool:
    """Register multiple sources under one go2rtc stream `name`.

    go2rtc's ``PUT /api/streams`` accepts repeated ``src`` query params for
    one stream, matching its YAML ``streams: <name>: [url1, url2]`` list
    syntax. This is how a stream ends up with more than one codec track —
    e.g. the printer's raw H.264 RTSP feed *and* an internal ffmpeg producer
    (``ffmpeg:<name>#video=mjpeg``) that transcodes it to MJPEG for the
    ``mjpeg`` output module. Without the second source, ``/api/stream.mjpeg``
    fails with "codecs not matched: video:H264 => video:JPEG, video:RAW" —
    go2rtc's MJPEG endpoint only serves a track that already exists, it does
    not transcode on the fly.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.put(
                f"{settings.go2rtc_api_url}/api/streams",
                params={"name": name, "src": source_urls},
            )
            resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        logger.warning("go2rtc: failed to register stream %s: %s", name, e)
        return False


async def remove_stream(name: str) -> None:
    """Deregister a go2rtc stream. Best-effort; never raises."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{settings.go2rtc_api_url}/api/streams",
                params={"src": name},
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug("go2rtc: failed to remove stream %s (may already be gone): %s", name, e)


async def is_available() -> bool:
    """Quick liveness check used by startup diagnostics / /camera/status."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{settings.go2rtc_api_url}/api/streams")
            resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


async def get_stream_details(name: str) -> dict | None:
    """Fetch go2rtc's live producer/consumer info for one stream.

    Used by the camera diagnostics endpoint to surface the real negotiated
    codec/profile/level and byte counters without PrintOps re-deriving or
    re-probing them — go2rtc already tracks this per-connection. Returns
    None if go2rtc is unreachable or the stream isn't currently registered.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{settings.go2rtc_api_url}/api/streams", params={"src": name})
            resp.raise_for_status()
            data = resp.json()
        return data or None
    except httpx.HTTPError as e:
        logger.debug("go2rtc: failed to fetch stream details for %s: %s", name, e)
        return None


def mjpeg_url(name: str) -> str:
    """Loopback URL PrintOps's own generator reads MJPEG frames from.

    Not exposed to clients directly — the existing multipart re-framing in
    generate_go2rtc_mjpeg_stream() reads this and re-emits PrintOps's own
    ``--frame`` boundary so downstream consumers (fan-out broadcaster,
    <img> viewers) see no change in wire format.
    """
    return f"{settings.go2rtc_api_url}/api/stream.mjpeg?src={name}"
