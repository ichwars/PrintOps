"""Camera streaming API endpoints for Bambu Lab printers."""

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import aclosing, suppress
from io import BytesIO
from time import monotonic

import httpx
import websockets
import websockets.exceptions
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequireCameraStreamTokenIfAuthEnabled,
    RequirePermissionIfAuthEnabled,
    RequirePrinterPermissionIfAuthEnabled,
    create_camera_stream_token,
)
from backend.app.core.auth_camera import StreamOpener, camera_request_access, stream_opener_still_allowed
from backend.app.core.config import settings
from backend.app.core.database import DB_SESSION, async_session
from backend.app.core.logging_filters import redact_url_credentials
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.services import go2rtc_client, go2rtc_registry
from backend.app.services.camera import (
    capture_camera_frame,
    get_camera_port,
    is_chamber_image_model,
    parse_jpeg_dimensions,
    test_camera_connection,
)
from backend.app.services.camera_fanout import (
    active_broadcaster_keys,
    active_source_identity,
    get_or_create_broadcaster,
    iter_subscriber,
    shutdown_broadcaster,
)
from backend.app.services.camera_light import automatic_camera_light
from backend.app.services.camera_profiles import get_camera_profile
from backend.app.services.camera_source import (
    BambuRtspSource,
    CameraSource,
    ExternalHttpSource,
    ExternalRtspSource,
    get_camera_source,
)
from backend.app.services.external_camera import generate_mjpeg_stream, jpeg_resolution
from backend.app.services.frozen_frame_watchdog import FrozenFrameWatchdog
from backend.app.utils.ffmpeg_limits import reap_ffmpeg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/printers", tags=["camera"])

_LIVE_FRAME_MAX_AGE_SECONDS = 10
_LIVE_FRAME_PENDING = "The live view has no recent frame yet. Try again in a moment."
_STREAM_RECHECK_SECONDS = 30.0
_STREAM_RECHECK_TIMEOUT = 5.0

# Track active ffmpeg processes for cleanup
_active_streams: dict[str, asyncio.subprocess.Process] = {}
_mse_stream_tasks: dict[int, set[asyncio.Task]] = {}

# Store last frame for each printer (for photo capture from active stream)
_last_frames: dict[int, bytes] = {}

# Track last frame timestamp for each printer (for stall detection)
_last_frame_times: dict[int, float] = {}

# Track stream start times for each printer
_stream_start_times: dict[int, float] = {}

# Last fps a viewer requested for each printer's stream (diagnostics only —
# the broadcaster's actual upstream rate is fixed by whichever viewer
# created it, see camera_stream()).
_stream_fps_target: dict[int, int] = {}

# Keep subprocess handles until they exit, even after a stream is detached.
_spawned_ffmpeg_processes: dict[asyncio.subprocess.Process, float] = {}

# Track disconnect events per stream_id — allows stop endpoint and cleanup
# to signal generators to stop reconnecting instead of just killing the process
_disconnect_events: dict[str, asyncio.Event] = {}

# Track last frame time per stream_id (not just per printer_id) for stale detection
_stream_last_frame_times: dict[str, float] = {}

# Rolling window of recent frame arrival timestamps per printer, used to
# compute a measured FPS for the diagnostics endpoint. A deque (not just a
# counter) so "measured fps" reflects a short recent window rather than a
# lifetime average that would understate a stream's current rate after a
# slow start or a brief stall.
_FPS_WINDOW_SECONDS = 5.0
_frame_arrival_times: dict[int, deque[float]] = {}


def _record_frame(printer_id: int, frame: bytes | None = None) -> None:
    """Update per-printer frame bookkeeping used by /camera/status and
    /camera/stream-info: last-frame buffer + timestamp, and the rolling
    arrival-time window used to measure FPS.
    """
    now = time.time()
    if frame is not None:
        _last_frames[printer_id] = frame
    _last_frame_times[printer_id] = now

    window = _frame_arrival_times.setdefault(printer_id, deque())
    window.append(now)
    cutoff = now - _FPS_WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.popleft()


def measured_fps(printer_id: int) -> float | None:
    """Frames/second over the last _FPS_WINDOW_SECONDS, or None if unknown."""
    window = _frame_arrival_times.get(printer_id)
    if not window or len(window) < 2:
        return None
    elapsed = window[-1] - window[0]
    if elapsed <= 0:
        return None
    return (len(window) - 1) / elapsed


def get_buffered_frame(printer_id: int) -> bytes | None:
    """Get the last buffered frame for a printer from an active stream.

    Returns the JPEG frame data if available, or None if no active stream.
    """
    return _last_frames.get(printer_id)


def is_stream_active(printer_id: int) -> bool:
    """Return True iff a fan-out camera stream is currently registered for this printer.

    Snapshot callers (Obico polling, manual /camera/snapshot) MUST NOT open a
    second concurrent RTSP/chamber-image socket while a viewer is attached:
    most Bambu firmwares allow only one camera connection, so the competing
    socket either kicks the live viewer off or gets refused itself, and the
    resulting reconnect storm tears down the fan-out broadcaster (see #1348).

    Callers should consult this BEFORE trying to open a fresh socket and skip
    the capture cycle when it returns True — even if try_get_active_buffered_frame
    returns None (the stream may be running but the first frame hasn't landed
    in the buffer yet, or the upstream is mid-reconnect).
    """
    if any(k.startswith(f"{printer_id}-") for k in _active_streams):
        return True
    # Built-in cameras (RTSP and, since the chamber-image bridge, A1/P1 too)
    # are go2rtc-backed and don't spawn a locally-owned ffmpeg process, so
    # they never appear in _active_streams above — go2rtc itself holds the
    # printer's one allowed connection. The fan-out broadcaster (MJPEG
    # viewers) and the go2rtc registry (MSE viewers — see
    # go2rtc_registry.py) are the two independent liveness signals for that
    # path; either one means go2rtc currently owns the printer's connection.
    return f"printer-{printer_id}" in active_broadcaster_keys() or go2rtc_registry.is_registered(printer_id)


def try_get_active_buffered_frame(printer_id: int) -> bytes | None:
    """Return a recent JPEG from a running MJPEG camera stream."""
    last_frame = _last_frame_times.get(printer_id)
    if last_frame is None or not 0 <= time.time() - last_frame <= _LIVE_FRAME_MAX_AGE_SECONDS:
        return None
    return _last_frames.get(printer_id) if is_stream_active(printer_id) else None


async def live_frame_for_capture(
    printer_id: int, *, external_source: tuple[str, str] | None = None
) -> tuple[bool, bytes | None]:
    """Indicate whether the live view owns the camera and offer its current frame."""
    if not is_stream_active(printer_id):
        return False, None
    if external_source is not None:
        identity = active_source_identity(f"printer-{printer_id}")
        registered = go2rtc_registry.registered_source(printer_id) if external_source[0] != "usb" else None
        if isinstance(registered, ExternalRtspSource):
            identity = ("rtsp", registered.url)
        elif isinstance(registered, ExternalHttpSource):
            identity = (registered.pipeline_label.removeprefix("external_"), registered.url)
        elif registered is not None:
            identity = None
        if identity != external_source:
            # A changed source may still have a viewer attached to its predecessor.
            return True, None
    frame = try_get_active_buffered_frame(printer_id)
    if frame is None and f"printer-{printer_id}" not in active_broadcaster_keys():
        if go2rtc_registry.is_registered(printer_id):
            # An MSE-only viewer has no JPEG buffer. Use the shared sidecar source.
            frame = await go2rtc_client.get_snapshot(printer_id)
    return True, frame


async def get_printer_or_404(printer_id: int, db: AsyncSession) -> Printer:
    """Get printer by ID or raise 404."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return printer


async def _terminate_ffmpeg(process: asyncio.subprocess.Process, stream_id: str | None = None) -> None:
    """Terminate an ffmpeg process gracefully, then kill if needed."""
    if process.returncode is not None:
        return  # Already dead
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except TimeoutError:
            logger.warning("ffmpeg didn't terminate gracefully, killing (stream_id=%s)", stream_id)
            await reap_ffmpeg(process)
    except ProcessLookupError:
        pass  # Already dead
    except OSError as e:
        logger.warning("Error terminating ffmpeg: %s", e)


def _summarize_ffmpeg_stderr(text: str | None) -> str:
    """Strip ffmpeg's boilerplate banner and keep only actionable lines.

    ffmpeg prints ~20 lines of version/build/configuration/lib headers before
    any actual error message. Logging the full banner on every retry floods
    the log (hundreds of lines per failed stream). This filter drops the
    banner and caps output at the last 10 meaningful lines.
    """
    if not text:
        return ""
    text = redact_url_credentials(text) or ""
    banner_prefixes = (
        "ffmpeg version ",
        "  built with ",
        "  configuration:",
        "  libavutil ",
        "  libavcodec ",
        "  libavformat ",
        "  libavdevice ",
        "  libavfilter ",
        "  libswscale ",
        "  libswresample ",
        "  libpostproc ",
    )
    meaningful = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith(banner_prefixes)]
    return "\n".join(meaningful[-10:])


async def _read_ffmpeg_stderr(process: asyncio.subprocess.Process) -> str | None:
    """Read whatever ffmpeg has written to stderr so far (best-effort).

    ffmpeg's stderr must be drained *incrementally*. A stalled-but-still-alive
    ffmpeg — the typical P2S RTSP failure, where it connects but never produces
    a frame — never closes stderr, so a plain ``stderr.read()`` (read-to-EOF)
    blocks until the wait_for timeout and returns nothing, discarding the
    banner + stream-analysis lines ffmpeg already printed. Reading in bounded
    chunks returns the buffered output promptly whether or not ffmpeg has
    exited. Returns the content with ffmpeg's boilerplate banner stripped.
    """
    if not process or not process.stderr:
        return None
    chunks: list[bytes] = []
    total = 0
    cap = 65536
    try:
        while total < cap:
            chunk = await asyncio.wait_for(process.stderr.read(8192), timeout=2.0)
            if not chunk:
                break  # EOF — ffmpeg has exited
            chunks.append(chunk)
            total += len(chunk)
    except Exception:
        # Timed out waiting for more data — ffmpeg is alive but quiet now.
        # Fall through and return whatever it already printed.
        pass
    if not chunks:
        return None
    return _summarize_ffmpeg_stderr(b"".join(chunks).decode(errors="replace")) or None


def _is_nearly_black_jpeg(
    frame: bytes, *, mean_threshold: float = 6.0, bright_fraction_threshold: float = 0.005
) -> bool:
    """Return True when a decoded JPEG is effectively black.

    Used only as a reconnect signal for model profiles with known black-frame
    RTSP failures; decode failures are not treated as black so corrupt frames
    keep following the normal stream/error path.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return False

    try:
        with Image.open(BytesIO(frame)) as image:
            image.thumbnail((64, 64))
            gray = image.convert("L")
            histogram = gray.histogram()
    except (OSError, UnidentifiedImageError):
        return False

    total_pixels = sum(histogram)
    if total_pixels <= 0:
        return False

    mean = sum(value * count for value, count in enumerate(histogram)) / total_pixels
    bright_pixels = sum(histogram[int(mean_threshold) + 1 :])
    bright_fraction = bright_pixels / total_pixels
    return mean <= mean_threshold and bright_fraction <= bright_fraction_threshold


async def generate_go2rtc_mjpeg_stream(
    camera_source: CameraSource,
    ip_address: str,
    model: str | None = None,
    fps: int = 10,
    stream_id: str | None = None,
    disconnect_event: asyncio.Event | None = None,
    printer_id: int | None = None,
) -> AsyncGenerator[bytes, None]:
    """Generate MJPEG stream from a printer's camera via the go2rtc sidecar.

    Works for every camera_source.py source — built-in RTSP (X1/X2D/H2/P2),
    built-in chamber-image (A1/P1, bridged into go2rtc as MJPEG — see
    chamber_image_bridge.py), and external RTSP/MJPEG/snapshot cameras
    alike. ``camera_source`` is what resolves the protocol-specific
    connection; this generator only ever talks to go2rtc's own HTTP API
    once that's done, so it doesn't need to know which kind it's dealing
    with. ``ip_address`` is only used for log messages.

    go2rtc ingests the printer-facing source exactly once (stream-copy for
    RTSP, no transcoding) and this generator re-frames its MJPEG output
    into PrintOps's own ``--frame`` multipart boundary — the wire format
    seen by the fan-out broadcaster and every downstream viewer is
    unchanged from before go2rtc existed. This replaces spawning our own
    ffmpeg re-encode per printer (which discarded H.264's inter-frame
    compression and was the root cause of high bandwidth / poor quality on
    X2D — see #camera quality investigation). Auto-reconnects the
    *consumer* side if go2rtc's MJPEG endpoint drops; go2rtc handles the
    actual printer-facing reconnects internally.

    Per-model reconnect cadence still comes from
    :func:`camera_profiles.get_camera_profile`. The ffmpeg-specific knobs on
    that profile (probesize, analyzeduration, extra_ffmpeg_input_args) no
    longer apply here — go2rtc's native RTSP client ingests the source, not
    ffmpeg — and are validated separately against the P2S TLS quirk that
    motivated them (see plan: "TLS-Proxy-Frage offen lassen").
    """
    profile = get_camera_profile(model)

    # Register disconnect event so stop endpoint can signal us
    if stream_id and disconnect_event:
        _disconnect_events[stream_id] = disconnect_event

    # The TLS proxy + go2rtc registration (RTSP producer + its internal
    # ffmpeg-derived MJPEG track) are shared with the MSE WebSocket path via
    # go2rtc_registry — see that module's docstring for why registering
    # them independently per-consumer is unsafe (go2rtc replaces a stream's
    # whole producer list on every registration call).
    #
    # NOTE: the MJPEG derivative runs at the camera's native fps (commonly
    # ~30) rather than the viewer-requested `fps` — go2rtc's REST API has
    # no reliable way to pass a raw ffmpeg arg containing a space
    # (`#raw=-r 15` fails go2rtc's own source-string validation; every
    # percent-encoding of the space we tried against go2rtc 1.9.14 was
    # preserved literally instead of decoded, so ffmpeg always saw a
    # malformed single token). Not worth chasing further for a codepath
    # that's meant to become a legacy fallback once the MSE player (Phase
    # B) is the primary path.
    if printer_id is None:
        logger.error("generate_go2rtc_mjpeg_stream requires printer_id (go2rtc registration is keyed by it)")
        yield (b"--frame\r\nContent-Type: text/plain\r\n\r\nError: internal error (missing printer id)\r\n")
        return

    try:
        go2rtc_name = await go2rtc_registry.acquire(printer_id, camera_source)
    except RuntimeError:
        logger.error("go2rtc unavailable - cannot start camera stream for %s", ip_address)
        if stream_id:
            _disconnect_events.pop(stream_id, None)
        _clear_mjpeg_frame_state(printer_id)
        yield (b"--frame\r\nContent-Type: text/plain\r\n\r\nError: restreaming service unavailable\r\n")
        return

    logger.info(
        "Starting go2rtc-backed camera stream for %s (stream_id=%s, model=%s, fps=%s, go2rtc_name=%s)",
        ip_address,
        stream_id,
        model,
        fps,
        go2rtc_name,
    )

    jpeg_start = b"\xff\xd8"
    jpeg_end = b"\xff\xd9"
    reconnect_count = 0
    got_any_frames = False
    mjpeg_endpoint = go2rtc_client.mjpeg_url(go2rtc_name)
    frozen_watchdog = FrozenFrameWatchdog(adaptive=isinstance(camera_source, ExternalRtspSource))

    try:
        while reconnect_count <= profile.rtsp_reconnect_max:
            # Check for client disconnect before (re)connecting
            if disconnect_event and disconnect_event.is_set():
                break

            if reconnect_count > 0:
                logger.info(
                    "go2rtc MJPEG reconnecting (%d/%d) for %s (stream_id=%s)",
                    reconnect_count,
                    profile.rtsp_reconnect_max,
                    ip_address,
                    stream_id,
                )
                await asyncio.sleep(profile.rtsp_reconnect_delay)
                if disconnect_event and disconnect_event.is_set():
                    break

            buffer = b""
            black_frame_streak = 0
            frozen_watchdog.begin_session()
            restart_source = False
            stream_ended = False
            client_gone = False

            try:
                async with (
                    httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as client,
                    client.stream("GET", mjpeg_endpoint) as resp,
                ):
                    if resp.status_code != 200:
                        logger.warning(
                            "go2rtc MJPEG endpoint returned %s for %s (stream_id=%s)",
                            resp.status_code,
                            go2rtc_name,
                            stream_id,
                        )
                        stream_ended = True
                    else:
                        async for chunk in resp.aiter_bytes(8192):
                            if disconnect_event and disconnect_event.is_set():
                                client_gone = True
                                break

                            buffer += chunk

                            # Extract complete JPEG frames from buffer
                            while True:
                                start_idx = buffer.find(jpeg_start)
                                if start_idx == -1:
                                    buffer = buffer[-2:] if len(buffer) > 2 else buffer
                                    break

                                if start_idx > 0:
                                    buffer = buffer[start_idx:]

                                end_idx = buffer.find(jpeg_end, 2)
                                if end_idx == -1:
                                    break

                                frame = buffer[: end_idx + 2]
                                buffer = buffer[end_idx + 2 :]
                                got_any_frames = True

                                if profile.black_frame_reconnect_threshold > 0:
                                    if await asyncio.to_thread(_is_nearly_black_jpeg, frame):
                                        black_frame_streak += 1
                                        if black_frame_streak >= profile.black_frame_reconnect_threshold:
                                            logger.warning(
                                                "go2rtc stream for %s (stream_id=%s) produced %d "
                                                "consecutive black frames; reconnecting",
                                                ip_address,
                                                stream_id,
                                                black_frame_streak,
                                            )
                                            stream_ended = True
                                            break
                                    else:
                                        black_frame_streak = 0

                                if printer_id is not None:
                                    _record_frame(printer_id, frame)
                                    if stream_id:
                                        _stream_last_frame_times[stream_id] = time.time()

                                yield (
                                    b"--frame\r\n"
                                    b"Content-Type: image/jpeg\r\n"
                                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                                    b"\r\n" + frame + b"\r\n"
                                )
                                if frozen_watchdog.observe(frame, monotonic()):
                                    logger.warning(
                                        "Camera picture unchanged for %s (stream_id=%s); restarting shared source",
                                        ip_address,
                                        stream_id,
                                    )
                                    restart_source = True
                                    stream_ended = True
                                    break
                            if stream_ended or client_gone:
                                break

                        if not (stream_ended or client_gone):
                            # go2rtc closed the response body on its own —
                            # treat like the old "ffmpeg exited" case.
                            logger.warning(
                                "go2rtc MJPEG stream ended for %s (stream_id=%s), will reconnect",
                                ip_address,
                                stream_id,
                            )
                            stream_ended = True

            except (httpx.HTTPError, OSError) as e:
                logger.warning("go2rtc MJPEG read error for %s (stream_id=%s): %s", ip_address, stream_id, e)
                stream_ended = True
            except asyncio.CancelledError:
                logger.info("Camera stream cancelled (stream_id=%s)", stream_id)
                client_gone = True
            except GeneratorExit:
                logger.info("Camera stream generator exit (stream_id=%s)", stream_id)
                client_gone = True

            if client_gone:
                break

            if not got_any_frames and reconnect_count == 0 and stream_ended:
                # First attempt never produced a frame — camera is likely
                # unreachable; don't retry silently forever.
                pass  # fall through to normal reconnect accounting below

            if stream_ended:
                if restart_source:
                    if await go2rtc_registry.restart(printer_id):
                        # Valid frames were received; periodic still-scene
                        # checks must not exhaust the transport retry budget.
                        reconnect_count = 1
                    else:
                        reconnect_count += 1
                else:
                    reconnect_count += 1
                continue

            # Normal exit (shouldn't reach here, but be safe)
            break

        if reconnect_count > profile.rtsp_reconnect_max:
            logger.error(
                "go2rtc MJPEG max reconnects (%d) reached for %s (stream_id=%s)",
                profile.rtsp_reconnect_max,
                ip_address,
                stream_id,
            )
            if not got_any_frames:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: text/plain\r\n\r\n"
                    b"Error: Camera connection failed. Check printer is on and camera is enabled.\r\n"
                )

    except asyncio.CancelledError:
        logger.info("Camera stream task cancelled (stream_id=%s)", stream_id)
    except GeneratorExit:
        logger.info("Camera stream generator closed (stream_id=%s)", stream_id)
    except Exception as e:
        logger.exception("Camera stream error: %s", e)
    finally:
        # Remove from active streams and disconnect events
        if stream_id:
            _active_streams.pop(stream_id, None)
            _disconnect_events.pop(stream_id, None)
            _stream_last_frame_times.pop(stream_id, None)

        # Clean up frame buffer and timestamps
        if printer_id is not None:
            _clear_mjpeg_frame_state(printer_id)

        # Release our reference on the shared go2rtc registration (see
        # go2rtc_registry) — only torn down once nothing else (e.g. a
        # concurrent MSE viewer) still holds a reference.
        if printer_id is not None:
            await go2rtc_registry.release(printer_id)
        logger.info("Camera stream stopped for %s (stream_id=%s)", ip_address, stream_id)


@router.post("/camera/stream-token")
async def create_stream_token(
    request: Request,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Create a reusable token for camera stream/snapshot access.

    Returns a token valid for 60 minutes that can be appended as ?token=xxx
    to camera stream/snapshot URLs loaded via <img> tags.
    """
    return {"token": await create_camera_stream_token(request, user)}


async def _stream_access_allowed(opener: StreamOpener, printer_id: int) -> bool:
    try:
        async with asyncio.timeout(_STREAM_RECHECK_TIMEOUT):
            return await stream_opener_still_allowed(opener, printer_id)
    except Exception:
        logger.warning("Camera access recheck failed for printer %s", printer_id)
        return False


def _clear_mjpeg_frame_state(printer_id: int) -> None:
    _last_frames.pop(printer_id, None)
    _last_frame_times.pop(printer_id, None)
    _stream_start_times.pop(printer_id, None)
    _stream_fps_target.pop(printer_id, None)
    _frame_arrival_times.pop(printer_id, None)


async def _generate_external_mjpeg_stream(
    printer_id: int, url: str, camera_type: str, fps: int, stop_event: asyncio.Event
) -> AsyncGenerator[bytes, None]:
    """Own the single upstream capture for an external camera outside go2rtc."""
    stream_id = f"{printer_id}-ext-{uuid.uuid4().hex[:8]}"
    _disconnect_events[stream_id] = stop_event

    def register_process(process: asyncio.subprocess.Process) -> None:
        _active_streams[stream_id] = process
        _spawned_ffmpeg_processes[process] = time.time()
        _stream_last_frame_times[stream_id] = time.time()

    def record_frame(frame: bytes) -> None:
        if not stop_event.is_set():
            _record_frame(printer_id, frame)
            _stream_last_frame_times[stream_id] = _last_frame_times[printer_id]

    try:
        async with aclosing(
            generate_mjpeg_stream(
                url, camera_type, fps, on_process=register_process, on_frame=record_frame, stop_event=stop_event
            )
        ) as frames:
            async for chunk in frames:
                if stop_event.is_set():
                    break
                yield chunk
    finally:
        stop_event.set()
        process = _active_streams.pop(stream_id, None)
        if process is not None and process.returncode is not None:
            _spawned_ffmpeg_processes.pop(process, None)
        _disconnect_events.pop(stream_id, None)
        _stream_last_frame_times.pop(stream_id, None)
        _clear_mjpeg_frame_state(printer_id)


@router.get("/{printer_id}/camera/stream")
async def camera_stream(
    printer_id: int,
    request: Request,
    fps: int = 10,
    db: AsyncSession = DB_SESSION,
    _: StreamOpener = RequireCameraStreamTokenIfAuthEnabled,
):
    """Share one multipart MJPEG upstream among viewers of the printer."""
    printer = await get_printer_or_404(printer_id, db)
    camera_source = get_camera_source(printer)
    ip_address, model = printer.ip_address, printer.model
    external_url = printer.external_camera_url or ""
    external_type = printer.external_camera_type or ""
    await db.close()

    max_fps = camera_source.max_fps if camera_source is not None else 15
    fps = min(max(fps, 1), max_fps)
    fanout_key = f"printer-{printer_id}"
    source_identity = (external_type, external_url) if printer.external_camera_enabled and external_url else ()

    def open_camera(disconnect_event: asyncio.Event) -> AsyncGenerator[bytes, None]:
        _stream_start_times[printer_id] = time.time()
        if camera_source is None:
            return _generate_external_mjpeg_stream(printer_id, external_url, external_type, fps, disconnect_event)
        return generate_go2rtc_mjpeg_stream(
            camera_source=camera_source,
            ip_address=ip_address,
            model=model,
            fps=fps,
            stream_id=f"{printer_id}-fanout",
            disconnect_event=disconnect_event,
            printer_id=printer_id,
        )

    async def factory(disconnect_event: asyncio.Event) -> AsyncGenerator[bytes, None]:
        async with automatic_camera_light(printer), aclosing(open_camera(disconnect_event)) as frames:
            async for chunk in frames:
                yield chunk

    next_check = monotonic() + _STREAM_RECHECK_SECONDS

    async def may_continue() -> bool:
        nonlocal next_check
        if monotonic() < next_check:
            return True
        next_check = monotonic() + _STREAM_RECHECK_SECONDS
        return await _stream_access_allowed(_, printer_id)

    async def is_disconnected() -> bool:
        if not await may_continue():
            return True
        try:
            return await request.is_disconnected()
        except Exception:
            return True

    async def generate() -> AsyncGenerator[bytes, None]:
        while True:
            broadcaster = await get_or_create_broadcaster(fanout_key, factory, source_identity=source_identity)
            try:
                queue = await broadcaster.subscribe()
            except RuntimeError:
                continue
            break

        _stream_fps_target[printer_id] = fps
        async with aclosing(
            iter_subscriber(
                broadcaster, queue, is_disconnected=is_disconnected, idle_check_seconds=_STREAM_RECHECK_SECONDS
            )
        ) as frames:
            async for chunk in frames:
                if not await may_continue():
                    return
                yield chunk

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.websocket("/{printer_id}/camera/mse")
async def camera_mse_stream(
    websocket: WebSocket,
    printer_id: int,
    token: str | None = Query(default=None),
) -> None:
    """MSE (fMP4-over-WebSocket) proxy for any RTSP-backed camera (built-in
    or external — see camera_source.py's ``has_h264`` sources).

    Relays go2rtc's `/api/ws?src=<name>` protocol verbatim: the browser
    sends a JSON handshake (`{"type":"mse","value":"<supported codecs>"}`)
    once its MediaSource is ready, go2rtc replies with the negotiated MIME
    type, then streams raw fMP4 segments as binary frames. PrintOps doesn't
    need to understand this protocol — it only needs to sit in front of it
    so browsers never reach go2rtc directly (it has no auth of its own) and
    so the printer's IP/access code never leave the backend.

    Same token-gate as the MJPEG stream (RequireCameraStreamTokenIfAuthEnabled
    can't be used directly here — it's an HTTP dependency, and auth must be
    checked *before* accept() so an unauthorized socket is never admitted).
    """
    try:
        async with asyncio.timeout(_STREAM_RECHECK_TIMEOUT):
            _, opener = await camera_request_access(token, printer_id)
    except Exception:
        logger.warning("Camera MSE access probe failed for printer %s", printer_id)
        await websocket.close(code=4401)
        return

    if opener is None:
        logger.info("Camera MSE connect refused: missing/invalid token (printer_id=%s)", printer_id)
        await websocket.close(code=4401)
        return

    task = asyncio.current_task()
    assert task is not None
    viewers = _mse_stream_tasks.setdefault(printer_id, set())
    viewers.add(task)
    try:
        await _relay_camera_mse(websocket, printer_id, opener)
    except asyncio.CancelledError:
        if _mse_stream_tasks.get(printer_id) is viewers:
            raise
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await websocket.close(code=4404)
    finally:
        viewers.discard(task)
        if not viewers and _mse_stream_tasks.get(printer_id) is viewers:
            _mse_stream_tasks.pop(printer_id, None)


async def _relay_camera_mse(websocket: WebSocket, printer_id: int, opener: StreamOpener) -> None:
    async with async_session() as db:
        printer = (await db.execute(select(Printer).where(Printer.id == printer_id))).scalar_one_or_none()

    camera_source = get_camera_source(printer) if printer is not None else None

    if camera_source is None or not camera_source.has_h264:
        # Chamber-image (A1/P1) and external MJPEG/snapshot sources are
        # bridged into go2rtc as MJPEG but never have an H.264 producer for
        # MSE to stream-copy — go2rtc could transcode JPEG→H.264, but that's
        # a real re-encode cost nobody's asked for (see
        # camera_source.CameraSource.has_h264 / chamber_image_bridge.py).
        # USB sources (camera_source is None) aren't even go2rtc-backed.
        # The frontend is expected to not offer MSE for these, but fail
        # closed here too rather than opening a socket with nothing to relay.
        await websocket.close(code=4404)
        return

    await websocket.accept()

    try:
        go2rtc_name = await go2rtc_registry.acquire(printer_id, camera_source)
    except RuntimeError:
        logger.error("go2rtc unavailable - cannot start MSE stream for printer %s", printer_id)
        await websocket.close(code=1011)
        return

    upstream_url = (
        f"{settings.go2rtc_api_url.replace('http://', 'ws://').replace('https://', 'wss://')}/api/ws?src={go2rtc_name}"
    )

    try:
        # max_size raised from the 1MB default — a 1080p H.264 keyframe
        # fragment can exceed that, which would otherwise get the upstream
        # connection dropped by the client library itself.
        async with (
            automatic_camera_light(printer),
            websockets.connect(upstream_url, open_timeout=10, max_size=8 * 1024 * 1024) as upstream,
        ):

            async def browser_to_go2rtc() -> None:
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if (text := msg.get("text")) is not None:
                        await upstream.send(text)
                    elif (data := msg.get("bytes")) is not None:
                        await upstream.send(data)

            async def go2rtc_to_browser() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            async def wait_for_access_loss() -> None:
                while True:
                    await asyncio.sleep(_STREAM_RECHECK_SECONDS)
                    if not await _stream_access_allowed(opener, printer_id):
                        return

            pump_a = asyncio.create_task(browser_to_go2rtc())
            pump_b = asyncio.create_task(go2rtc_to_browser())
            access_watch = asyncio.create_task(wait_for_access_loss())
            tasks = {pump_a, pump_b, access_watch}
            try:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            if access_watch in done:
                await websocket.close(code=4401)
    except WebSocketDisconnect:
        pass
    except (OSError, websockets.exceptions.WebSocketException) as e:
        logger.warning("Camera MSE upstream connection failed for printer %s: %s", printer_id, e)
    finally:
        await go2rtc_registry.release(printer_id)
        logger.info("Camera MSE stream ended for printer %s", printer_id)


@router.get("/{printer_id}/camera/stop")
@router.post("/{printer_id}/camera/stop")
async def stop_camera_stream(
    printer_id: int,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Stop active camera streams for a printer.

    Called by the frontend on viewer unmount (cam-wall tile, embedded viewer,
    popup window). Accepts both GET and POST (POST for sendBeacon compatibility).

    Reference-count guard: every viewer of a printer subscribes to the same
    fan-out broadcaster, so a force-shutdown triggered by ONE leaving viewer
    used to kill the others' streams (cam-wall tile froze when a user opened
    then closed the embedded viewer). If any subscriber is still attached,
    skip the force-teardown — the broadcaster's natural grace-shutdown (5 s
    after subscribers drop to 0) handles cleanup when the leaving viewer's
    HTTP connection actually closes.
    """
    broadcaster_key = f"printer-{printer_id}"
    shutdown = await shutdown_broadcaster(broadcaster_key, only_if_idle=True)
    if shutdown is None:
        return {"stopped": 0, "skipped": True}
    if shutdown:
        # The broadcaster owns its source teardown. A viewer may already be
        # opening the replacement by the time that teardown finishes.
        return {"stopped": 0}

    stopped = await _terminate_printer_processes(printer_id)
    logger.info("Stopped %s camera stream(s) for printer %s", stopped, printer_id)
    return {"stopped": stopped}


async def forget_printer_camera(printer_id: int) -> None:
    viewers = _mse_stream_tasks.pop(printer_id, set())
    for task in viewers:
        task.cancel()
    if viewers:
        await asyncio.gather(*viewers, return_exceptions=True)

    await shutdown_broadcaster(f"printer-{printer_id}")
    for stream_id, event in list(_disconnect_events.items()):
        if stream_id.startswith(f"{printer_id}-"):
            event.set()
    await _terminate_printer_processes(printer_id)
    await go2rtc_registry.discard(printer_id)
    _clear_mjpeg_frame_state(printer_id)


async def _terminate_printer_processes(printer_id: int) -> int:
    stopped = 0

    # Stop ffmpeg/RTSP streams
    to_remove = []
    for stream_id, process in list(_active_streams.items()):
        if stream_id.startswith(f"{printer_id}-"):
            to_remove.append((stream_id, process))
            # Signal the generator to stop reconnecting BEFORE killing the process
            event = _disconnect_events.get(stream_id)
            if event:
                event.set()
            if process.returncode is None:
                await _terminate_ffmpeg(process, stream_id)
                if process.returncode is not None:
                    stopped += 1
                    logger.info("Terminated ffmpeg process for stream %s", stream_id)
            if process.returncode is not None:
                _spawned_ffmpeg_processes.pop(process, None)

    for stream_id, process in to_remove:
        if _active_streams.get(stream_id) is process:
            _active_streams.pop(stream_id, None)
            _disconnect_events.pop(stream_id, None)
            _stream_last_frame_times.pop(stream_id, None)

    return stopped


@router.get("/{printer_id}/camera/snapshot")
async def camera_snapshot(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    """Capture a single frame from the printer camera.

    Returns a JPEG image.

    Requires a stream token query param (?token=xxx) when auth is enabled.
    """
    printer = await get_printer_or_404(printer_id, db)
    await db.close()
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Content-Disposition": f'inline; filename="snapshot_{printer_id}.jpg"',
    }
    async with automatic_camera_light(printer, wait=True):
        return await _capture_snapshot(printer, headers)


async def _capture_snapshot(printer: Printer, headers: dict[str, str]) -> Response:
    import tempfile
    from pathlib import Path

    printer_id = printer.id
    external = bool(printer.external_camera_enabled and printer.external_camera_url)

    if not (external and printer.external_camera_snapshot_url):
        external_source = (printer.external_camera_type or "", printer.external_camera_url) if external else None
        watched, buffered = await live_frame_for_capture(printer_id, external_source=external_source)
        if watched:
            if not buffered:
                raise HTTPException(503, _LIVE_FRAME_PENDING, headers={"Retry-After": "2"})
            return Response(content=buffered, media_type="image/jpeg", headers=headers)

    if external:
        from backend.app.services.external_camera import capture_frame

        frame = await capture_frame(
            printer.external_camera_url,
            printer.external_camera_type,
            timeout=15,
            snapshot_url=printer.external_camera_snapshot_url,
        )
        if not frame:
            raise HTTPException(503, "Failed to capture frame from external camera.")
        return Response(content=frame, media_type="image/jpeg", headers=headers)

    # Create temporary file for the snapshot (0600 so only the app user can read it)
    fd, tmp_name = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    temp_path = Path(tmp_name)
    temp_path.chmod(0o600)

    try:
        success = await capture_camera_frame(
            ip_address=printer.ip_address,
            access_code=printer.access_code,
            model=printer.model,
            output_path=temp_path,
            timeout=15,
        )

        if not success:
            raise HTTPException(
                status_code=503,
                detail="Failed to capture camera frame. Ensure printer is on and camera is enabled.",
            )

        # Read and return the image
        with open(temp_path, "rb") as f:
            image_data = f.read()

        return Response(content=image_data, media_type="image/jpeg", headers=headers)
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.get("/{printer_id}/camera/test")
async def test_camera(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Test camera connection for a printer.

    Returns success status and any error message.
    """
    printer = await get_printer_or_404(printer_id, db)
    await db.close()

    result = await test_camera_connection(
        ip_address=printer.ip_address,
        access_code=printer.access_code,
        model=printer.model,
    )

    return result


@router.post("/{printer_id}/camera/diagnose")
async def diagnose_camera_route(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Run staged diagnostics for a printer's camera path.

    Returns a structured result the frontend renders inline so users can
    self-diagnose "connection lost" before opening a ticket. See
    ``camera_diagnose`` for stage details and the live-stream shortcut.
    """
    from backend.app.services.camera_diagnose import diagnose_camera

    printer = await get_printer_or_404(printer_id, db)
    await db.close()

    # Look up live-stream evidence so the diagnostic can short-circuit
    # instead of fighting a viewer for the printer's single camera slot.
    has_live = is_stream_active(printer_id)
    last_ts = _last_frame_times.get(printer_id) if has_live else None
    live_age = (time.time() - last_ts) if (has_live and last_ts) else None

    result = await diagnose_camera(
        ip_address=printer.ip_address,
        access_code=printer.access_code,
        model=printer.model,
        printer_id=printer_id,
        has_live_stream=has_live,
        live_frame_age_seconds=live_age,
    )
    return result.to_dict()


@router.get("/{printer_id}/camera/status")
async def camera_status(
    printer_id: int,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Get the status of an active camera stream.

    Returns whether a stream is active and when the last frame was received.
    Used by the frontend to detect stalled streams and auto-reconnect.
    """
    has_active_stream = is_stream_active(printer_id)

    # Get timing information
    current_time = time.time()
    last_frame_time = _last_frame_times.get(printer_id)
    stream_start_time = _stream_start_times.get(printer_id)

    # Calculate seconds since last frame
    seconds_since_frame = None
    if last_frame_time is not None:
        seconds_since_frame = current_time - last_frame_time

    # Calculate stream uptime
    stream_uptime = None
    if stream_start_time is not None:
        stream_uptime = current_time - stream_start_time

    return {
        "active": has_active_stream,
        "has_frames": printer_id in _last_frames,
        "seconds_since_frame": seconds_since_frame,
        "stream_uptime": stream_uptime,
        # Consider stalled if no frame for more than 10 seconds after stream started
        "stalled": (
            has_active_stream
            and stream_uptime is not None
            and stream_uptime > 5  # Give 5 seconds for stream to start
            and (seconds_since_frame is None or seconds_since_frame > 10)
        ),
    }


@router.get("/{printer_id}/camera/stream-info")
async def camera_stream_info(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Technical details of a printer's camera pipeline, for the Diagnose panel.

    Deliberately separate from the lightweight, frequently-polled
    /camera/status: this one queries go2rtc's own API for codec/byte
    counters and parses the buffered frame's JPEG header for resolution, so
    it's only meant to be called on-demand (e.g. when the user opens the
    diagnostics modal), not on a stall-detection timer.

    All fields are best-effort — a printer with no active stream still gets
    a 200 with the static (protocol/port/profile) fields and nulls for the
    live ones, so the panel can explain *why* nothing is playing.
    """
    printer = await get_printer_or_404(printer_id, db)
    camera_source = get_camera_source(printer)
    is_external = bool(printer.external_camera_enabled and printer.external_camera_url)

    if camera_source is None:
        # USB/v4l2 — not go2rtc-backed (see camera_source.py).
        source = "external"
        pipeline = f"external_{printer.external_camera_type}"
        go2rtc_name = None
        port = None
        tls_proxy = False
        camera_profile = None
    else:
        go2rtc_name = go2rtc_client.stream_name(printer_id)
        pipeline = camera_source.pipeline_label
        tls_proxy = isinstance(camera_source, BambuRtspSource) or (
            isinstance(camera_source, ExternalRtspSource) and camera_source.url.lower().startswith("rtsps://")
        )
        if is_external:
            source = "external"
            port = None
            camera_profile = None
        else:
            from backend.app.services.camera_diagnose import _profile_label

            source = "built_in_chamber_image" if is_chamber_image_model(printer.model) else "built_in_rtsp"
            port = get_camera_port(printer.model)
            camera_profile = _profile_label(printer.model)

    resolution = None
    buffered = _last_frames.get(printer_id)
    if buffered:
        dims = parse_jpeg_dimensions(buffered)
        if dims:
            resolution = {"width": dims[0], "height": dims[1]}

    # _stream_start_times is only populated by the MJPEG generator path — an
    # MSE-only session falls back to go2rtc_registry's own timestamp so
    # uptime (and the bitrate estimate below, which needs it) isn't blank
    # just because no MJPEG viewer ever opened.
    start_time = _stream_start_times.get(printer_id) or go2rtc_registry.registered_since(printer_id)
    stream_uptime = (time.time() - start_time) if start_time is not None else None

    codec_name = None
    codec_profile = None
    codec_level = None
    bitrate_kbps = None

    if go2rtc_name is not None:
        # Sources with no H.264 producer (chamber-image, external
        # MJPEG/snapshot) only ever have an MJPEG producer to report — for
        # H.264-capable sources, skip that MJPEG derivative and keep
        # looking for the real video codec, since that's the one MSE
        # actually uses.
        skip_codecs = () if camera_source is not None and not camera_source.has_h264 else ("mjpeg",)
        details = await go2rtc_client.get_stream_details(go2rtc_name)
        if details:
            for producer in details.get("producers") or []:
                codec = None
                for receiver in producer.get("receivers") or []:
                    if receiver.get("codec", {}).get("codec_type") == "video":
                        codec = receiver["codec"]
                        break
                if codec and codec.get("codec_name") not in (None, *skip_codecs):
                    codec_name = codec.get("codec_name")
                    codec_profile = codec.get("profile")
                    level = codec.get("level")
                    # go2rtc reports H.264 level as an integer tenths value
                    # (41 == "4.1"), matching how the spec itself names levels.
                    codec_level = f"{level / 10:.1f}" if isinstance(level, int | float) else None
                    if stream_uptime and stream_uptime > 0:
                        bitrate_kbps = round((producer.get("bytes_recv", 0) * 8 / 1000) / stream_uptime, 1)
                    break

    return {
        "printer_id": printer_id,
        "source": source,
        "pipeline": pipeline,
        "go2rtc_stream": go2rtc_name,
        "port": port,
        "camera_profile": camera_profile,
        "tls_proxy": tls_proxy,
        "codec": codec_name,
        "codec_profile": codec_profile,
        "codec_level": codec_level,
        "resolution": resolution,
        "fps_target": _stream_fps_target.get(printer_id),
        "fps_measured": measured_fps(printer_id),
        "bitrate_kbps": bitrate_kbps,
        "stream_uptime_seconds": stream_uptime,
        "active": is_stream_active(printer_id),
    }


class ExternalCameraTestRequest(BaseModel):
    url: str
    camera_type: str


@router.post("/{printer_id}/camera/external/test")
async def test_external_camera(
    printer_id: int,
    url: str | None = None,
    camera_type: str | None = None,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    request: ExternalCameraTestRequest | None = None,
):
    """Test an external camera, reusing the live view of the configured source."""
    from backend.app.services.external_camera import test_connection

    if request is not None:
        url, camera_type = request.url, request.camera_type
    if not url or not camera_type:
        raise HTTPException(422, "A camera URL and type are required.")

    printer = await get_printer_or_404(printer_id, db)
    await db.close()
    if (
        printer.external_camera_enabled
        and url == printer.external_camera_url
        and camera_type == printer.external_camera_type
    ):
        watched, frame = await live_frame_for_capture(printer_id, external_source=(camera_type, url))
        if watched:
            if frame:
                return {"success": True, "resolution": jpeg_resolution(frame), "live_view": True}
            return {"success": False, "error": _LIVE_FRAME_PENDING, "live_view": True}
    return await test_connection(url, camera_type)


@router.get("/{printer_id}/camera/check-plate")
async def check_plate_empty(
    printer_id: int,
    plate_type: str | None = None,
    use_external: bool | None = None,
    include_debug_image: bool = False,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Check if the build plate is empty using camera vision.

    Uses calibration-based difference detection - compares current frame
    to a reference image of the empty plate.

    IMPORTANT: Chamber light must be ON for reliable detection.

    Args:
        printer_id: Printer ID
        plate_type: Type of build plate (e.g., "High Temp Plate") for calibration lookup
        use_external: If True, prefer external camera over built-in. When omitted
            (None), defaults to the printer's external_camera_enabled setting —
            mirroring the runtime auto-check at print start (main.py). Without
            this default the UI's manual check would always use the built-in
            camera, mismatching the reference saved during calibration (#1359).
        include_debug_image: If True, return URL to annotated debug image

    Returns:
        Dict with detection results:
        - is_empty: bool - Whether plate appears empty
        - confidence: float - Confidence level (0.0 to 1.0)
        - difference_percent: float - How different from calibration reference
        - message: str - Human-readable result message
        - needs_calibration: bool - True if calibration is required
        - failure_reason: str | None - why a check could not run
        - light_warning: bool - True if chamber light is off
    """
    from backend.app.services.plate_detection import (
        check_plate_empty as do_check,
        is_plate_detection_available,
    )
    from backend.app.services.printer_manager import printer_manager

    # Check printer exists first (before OpenCV check)
    printer = await get_printer_or_404(printer_id, db)
    await db.close()

    if use_external is None:
        use_external = bool(
            printer.external_camera_enabled and printer.external_camera_url and printer.external_camera_type
        )

    if not is_plate_detection_available():
        raise HTTPException(
            status_code=503,
            detail="Plate detection not available. Install opencv-python-headless to enable.",
        )

    # Check chamber light status
    light_warning = False
    state = printer_manager.get_status(printer_id)
    if state and not state.chamber_light:
        light_warning = True

    from backend.app.services.plate_detection import PlateDetector

    # Build ROI tuple from printer settings if available
    roi = None
    if all(
        [
            printer.plate_detection_roi_x is not None,
            printer.plate_detection_roi_y is not None,
            printer.plate_detection_roi_w is not None,
            printer.plate_detection_roi_h is not None,
        ]
    ):
        roi = (
            printer.plate_detection_roi_x,
            printer.plate_detection_roi_y,
            printer.plate_detection_roi_w,
            printer.plate_detection_roi_h,
        )

    result = await do_check(
        printer_id=printer.id,
        ip_address=printer.ip_address,
        access_code=printer.access_code,
        model=printer.model,
        plate_type=plate_type,
        include_debug_image=include_debug_image,
        external_camera_url=printer.external_camera_url if printer.external_camera_enabled else None,
        external_camera_type=printer.external_camera_type if printer.external_camera_enabled else None,
        use_external=use_external,
        roi=roi,
        external_camera_snapshot_url=printer.external_camera_snapshot_url if printer.external_camera_enabled else None,
    )

    # Get reference count for the response
    detector = PlateDetector()
    ref_count = detector.get_calibration_count(printer.id)

    response = result.to_dict()
    response["light_warning"] = light_warning
    response["reference_count"] = ref_count
    response["max_references"] = detector.MAX_REFERENCES
    # Include current ROI in response
    if roi:
        response["roi"] = {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}
    else:
        # Return default ROI
        response["roi"] = {"x": 0.15, "y": 0.35, "w": 0.70, "h": 0.55}

    # If debug image requested and available, encode as base64 data URL
    if include_debug_image and result.debug_image:
        import base64

        b64_image = base64.b64encode(result.debug_image).decode("utf-8")
        response["debug_image_url"] = f"data:image/jpeg;base64,{b64_image}"

    return response


@router.post("/{printer_id}/camera/plate-detection/calibrate")
async def calibrate_plate_detection(
    printer_id: int,
    label: str | None = None,
    use_external: bool | None = None,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePrinterPermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
):
    """Calibrate plate detection by capturing a reference image of the empty plate.

    The plate MUST be empty when calling this endpoint. The captured image
    will be used as the reference for future detection comparisons.

    Supports up to 5 reference images per printer. When adding a 6th, the oldest
    is automatically removed.

    IMPORTANT: Chamber light should be ON for calibration.

    Args:
        printer_id: Printer ID
        label: Optional label for this reference (e.g., "High Temp Plate", "Wham Bam")
        use_external: If True, prefer external camera over built-in. When omitted
            (None), defaults to the printer's external_camera_enabled setting so
            calibration captures from the same source the runtime auto-check
            uses at print start (#1359).

    Returns:
        Dict with:
        - success: bool - Whether calibration succeeded
        - message: str - Status message
        - index: int - The reference slot used (0-4)
    """
    from backend.app.services.plate_detection import (
        calibrate_plate,
        is_plate_detection_available,
    )
    from backend.app.services.printer_manager import printer_manager

    # Check printer exists first (before OpenCV check)
    printer = await get_printer_or_404(printer_id, db)
    await db.close()

    if use_external is None:
        use_external = bool(
            printer.external_camera_enabled and printer.external_camera_url and printer.external_camera_type
        )

    if not is_plate_detection_available():
        raise HTTPException(
            status_code=503,
            detail="Plate detection not available. Install opencv-python-headless to enable.",
        )

    # Check chamber light - warn but don't block
    state = printer_manager.get_status(printer_id)
    light_warning = state and not state.chamber_light

    success, message, index = await calibrate_plate(
        printer_id=printer.id,
        ip_address=printer.ip_address,
        access_code=printer.access_code,
        model=printer.model,
        label=label,
        external_camera_url=printer.external_camera_url if printer.external_camera_enabled else None,
        external_camera_type=printer.external_camera_type if printer.external_camera_enabled else None,
        use_external=use_external,
        external_camera_snapshot_url=printer.external_camera_snapshot_url if printer.external_camera_enabled else None,
    )

    if light_warning and success:
        message += " (Warning: Chamber light was off)"

    return {"success": success, "message": message, "index": index}


@router.delete("/{printer_id}/camera/plate-detection/calibrate")
async def delete_plate_calibration(
    printer_id: int,
    plate_type: str | None = None,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePrinterPermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
):
    """Delete the plate detection calibration for a printer and plate type.

    Args:
        printer_id: Printer ID
        plate_type: Type of build plate (if None, deletes legacy non-plate-specific calibration)

    Returns:
        Dict with:
        - success: bool - Whether deletion succeeded
        - message: str - Status message
    """
    from backend.app.services.plate_detection import (
        delete_calibration,
        is_plate_detection_available,
    )

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        raise HTTPException(
            status_code=503,
            detail="Plate detection not available. Install opencv-python-headless to enable.",
        )

    deleted = delete_calibration(printer_id, plate_type)
    plate_msg = f" for '{plate_type}'" if plate_type else ""

    return {
        "success": deleted,
        "message": f"Calibration deleted{plate_msg}" if deleted else f"No calibration found{plate_msg}",
    }


@router.get("/{printer_id}/camera/plate-detection/status")
async def get_plate_detection_status(
    printer_id: int,
    plate_type: str | None = None,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Check plate detection status for a printer and plate type.

    Returns:
        Dict with:
        - available: bool - Whether OpenCV is installed
        - calibrated: bool - Whether printer has calibration for this plate type
        - plate_type: str - The plate type queried
        - chamber_light: bool - Whether chamber light is on
        - message: str - Status message
    """
    from backend.app.services.plate_detection import (
        get_calibration_status,
        is_plate_detection_available,
    )
    from backend.app.services.printer_manager import printer_manager

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        return {
            "available": False,
            "calibrated": False,
            "plate_type": plate_type,
            "chamber_light": False,
            "message": "OpenCV not installed",
        }

    # Get chamber light status
    state = printer_manager.get_status(printer_id)
    chamber_light = state.chamber_light if state else False

    status = get_calibration_status(printer_id, plate_type)
    status["chamber_light"] = chamber_light

    return status


@router.get("/{printer_id}/camera/plate-detection/references")
async def get_plate_references(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Get all calibration references for a printer with metadata.

    Returns list of references with index, label, timestamp, and thumbnail URL.
    """
    from backend.app.services.plate_detection import PlateDetector, is_plate_detection_available

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        raise HTTPException(503, "Plate detection not available")

    detector = PlateDetector()
    references = detector.get_references(printer_id)

    # Add thumbnail URLs
    for ref in references:
        ref["thumbnail_url"] = (
            f"/api/v1/printers/{printer_id}/camera/plate-detection/references/{ref['index']}/thumbnail"
        )

    return {
        "references": references,
        "max_references": detector.MAX_REFERENCES,
    }


@router.get("/{printer_id}/camera/plate-detection/references/{index}/thumbnail")
async def get_reference_thumbnail(
    printer_id: int,
    index: int,
    db: AsyncSession = DB_SESSION,
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    """Get thumbnail image for a calibration reference.

    Requires a stream token query param (?token=xxx) when auth is enabled.
    """
    from fastapi.responses import Response

    from backend.app.services.plate_detection import PlateDetector, is_plate_detection_available

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        raise HTTPException(503, "Plate detection not available")

    detector = PlateDetector()
    thumbnail = detector.get_reference_thumbnail(printer_id, index)

    if thumbnail is None:
        raise HTTPException(404, "Reference not found")

    return Response(content=thumbnail, media_type="image/jpeg")


@router.put("/{printer_id}/camera/plate-detection/references/{index}")
async def update_reference_label(
    printer_id: int,
    index: int,
    label: str,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePrinterPermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
):
    """Update the label for a calibration reference."""
    from backend.app.services.plate_detection import PlateDetector, is_plate_detection_available

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        raise HTTPException(503, "Plate detection not available")

    detector = PlateDetector()
    success = detector.update_reference_label(printer_id, index, label)

    if not success:
        raise HTTPException(404, "Reference not found")

    return {"success": True, "index": index, "label": label}


@router.delete("/{printer_id}/camera/plate-detection/references/{index}")
async def delete_reference(
    printer_id: int,
    index: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePrinterPermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
):
    """Delete a specific calibration reference."""
    from backend.app.services.plate_detection import PlateDetector, is_plate_detection_available

    # Verify printer exists first (before OpenCV check)
    await get_printer_or_404(printer_id, db)

    if not is_plate_detection_available():
        raise HTTPException(503, "Plate detection not available")

    detector = PlateDetector()
    success = detector.delete_reference(printer_id, index)

    if not success:
        raise HTTPException(404, "Reference not found")

    return {"success": True, "message": "Reference deleted"}


async def cleanup_orphaned_streams() -> None:
    """Reap this instance's detached or stalled stream processes."""
    now = time.time()

    for stream_id, process in list(_active_streams.items()):
        event = _disconnect_events.get(stream_id)
        if process.returncode is not None:
            if event is None or event.is_set():
                _active_streams.pop(stream_id, None)
            continue
        started_at = _spawned_ffmpeg_processes.get(process)
        if started_at is None:
            continue
        last_frame_at = _stream_last_frame_times.get(stream_id, started_at)
        if now - started_at <= 60 or now - last_frame_at <= 30:
            continue

        logger.info("Stopping stalled ffmpeg stream %s (no frames for %.0fs)", stream_id, now - last_frame_at)
        if event is not None:
            event.set()
        _active_streams.pop(stream_id, None)
        _disconnect_events.pop(stream_id, None)
        _stream_last_frame_times.pop(stream_id, None)

    active_processes = set(_active_streams.values())
    for process in list(_spawned_ffmpeg_processes):
        if process.returncode is None and process not in active_processes:
            logger.info("Reaping detached ffmpeg stream (pid=%d)", process.pid)
            await reap_ffmpeg(process)
        if process.returncode is not None:
            _spawned_ffmpeg_processes.pop(process, None)
