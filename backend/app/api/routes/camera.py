"""Camera streaming API endpoints for Bambu Lab printers."""

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator
from io import BytesIO

import httpx
import websockets
import websockets.exceptions
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequireCameraStreamTokenIfAuthEnabled,
    RequirePermissionIfAuthEnabled,
    create_camera_stream_token,
    is_auth_enabled,
    verify_camera_stream_token,
)
from backend.app.core.config import settings
from backend.app.core.database import async_session, get_db
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
    MjpegBroadcaster,
    active_broadcaster_keys,
    get_or_create_broadcaster,
    get_subscriber_count,
    iter_subscriber,
    shutdown_broadcaster,
)
from backend.app.services.camera_profiles import get_camera_profile
from backend.app.services.camera_source import BambuRtspSource, CameraSource, ExternalRtspSource, get_camera_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/printers", tags=["camera"])

# Track active ffmpeg processes for cleanup
_active_streams: dict[str, asyncio.subprocess.Process] = {}

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

# Track active external camera streams by printer ID
_active_external_streams: set[int] = set()

# Track ALL spawned ffmpeg PIDs (persists even if _active_streams entries are removed)
# Maps PID -> spawn timestamp — used by cleanup to find truly orphaned OS processes
_spawned_ffmpeg_pids: dict[int, float] = {}

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
    """Return a buffered frame iff a stream is currently running for this printer.

    Snapshot callers (Obico polling, manual /camera/snapshot) tap the fan-out
    broadcaster's running upstream instead of opening a second concurrent
    RTSP/chamber-image socket. Critical for printers that allow only one
    camera connection (e.g. X2D firmware 01.01.00.00; see #1271).

    Returns None when no broadcaster is active for this printer, so callers
    fall through to their existing fresh-socket path unchanged.

    NB: returning None does NOT mean "safe to open a fresh socket" — it also
    fires when the stream is registered but no frame has been buffered yet
    (startup race, mid-reconnect). Callers that must avoid competing sockets
    should consult is_stream_active() first; see #1348.
    """
    if not is_stream_active(printer_id):
        return None
    return _last_frames.get(printer_id)


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
            process.kill()
            await process.wait()
    except ProcessLookupError:
        pass  # Already dead
    except OSError as e:
        logger.warning("Error terminating ffmpeg: %s", e)
    _spawned_ffmpeg_pids.pop(process.pid, None)


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
            _last_frames.pop(printer_id, None)
            _last_frame_times.pop(printer_id, None)
            _stream_start_times.pop(printer_id, None)

        # Release our reference on the shared go2rtc registration (see
        # go2rtc_registry) — only torn down once nothing else (e.g. a
        # concurrent MSE viewer) still holds a reference.
        if printer_id is not None:
            await go2rtc_registry.release(printer_id)
        logger.info("Camera stream stopped for %s (stream_id=%s)", ip_address, stream_id)


@router.post("/camera/stream-token")
async def create_stream_token(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Create a reusable token for camera stream/snapshot access.

    Returns a token valid for 60 minutes that can be appended as ?token=xxx
    to camera stream/snapshot URLs loaded via <img> tags.
    """
    return {"token": await create_camera_stream_token()}


@router.get("/{printer_id}/camera/stream")
async def camera_stream(
    printer_id: int,
    request: Request,
    fps: int = 10,
    db: AsyncSession = Depends(get_db),
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    """Stream live video from printer camera as MJPEG.

    This endpoint returns a multipart MJPEG stream that can be used directly
    in an <img> tag or video player.

    Requires a stream token query param (?token=xxx) when auth is enabled.

    Uses external camera if configured, otherwise uses built-in camera:
    - External: MJPEG, RTSP, or HTTP snapshot
    - A1/P1: Chamber image protocol (port 6000)
    - X1/H2/P2: RTSP via ffmpeg (port 322)

    Args:
        printer_id: Printer ID
        fps: Target frames per second (default: 10, max: 30)
    """
    printer = await get_printer_or_404(printer_id, db)

    camera_source = get_camera_source(printer)

    if camera_source is None:
        # USB/v4l2 (or an unrecognised external type) — not go2rtc-ingestible
        # (see camera_source.py: device passthrough into the container is a
        # separate deployment-time problem this abstraction doesn't solve).
        # Falls back to the original direct-ffmpeg-per-viewer path, with no
        # fan-out — each viewer of a USB camera opens its own capture.
        from backend.app.services.external_camera import generate_mjpeg_stream

        # Limit external camera FPS to reduce browser load
        fps = min(max(fps, 1), 15)
        logger.info(
            "Using external camera (%s) for printer %s at %s fps", printer.external_camera_type, printer_id, fps
        )

        stream_id = f"{printer_id}-ext-{uuid.uuid4().hex[:8]}"
        stop_event = asyncio.Event()
        _disconnect_events[stream_id] = stop_event

        # Track stream start
        _stream_start_times[printer_id] = time.time()
        _active_external_streams.add(printer_id)

        current_proc: dict[str, asyncio.subprocess.Process] = {}

        def _register_external_process(proc: asyncio.subprocess.Process) -> None:
            prev = current_proc.get("proc")
            if prev is not None and prev.pid != proc.pid:
                _spawned_ffmpeg_pids.pop(prev.pid, None)
            current_proc["proc"] = proc
            _active_streams[stream_id] = proc
            _spawned_ffmpeg_pids[proc.pid] = time.time()
            _stream_last_frame_times[stream_id] = time.time()

        async def external_stream_wrapper():
            """Wrap external stream to track start/stop and update frame times."""
            try:
                async for frame in generate_mjpeg_stream(
                    printer.external_camera_url,
                    printer.external_camera_type,
                    fps,
                    on_process=_register_external_process,
                    stop_event=stop_event,
                ):
                    # generate_mjpeg_stream already handles rate limiting;
                    # just track frame times for stall detection.
                    _record_frame(printer_id)
                    _stream_last_frame_times[stream_id] = time.time()
                    yield frame
            finally:
                stop_event.set()
                proc = current_proc.get("proc")
                if proc is not None:
                    _spawned_ffmpeg_pids.pop(proc.pid, None)
                _active_streams.pop(stream_id, None)
                _disconnect_events.pop(stream_id, None)
                _stream_last_frame_times.pop(stream_id, None)
                _active_external_streams.discard(printer_id)
                logger.info("External camera stream ended for printer %s", printer_id)

        return StreamingResponse(
            external_stream_wrapper(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # Every other camera — built-in RTSP, built-in chamber-image, and
    # external RTSP/MJPEG/snapshot — is go2rtc-backed via camera_source.py,
    # sharing the same fan-out broadcaster and generator.
    fps = min(max(fps, 1), camera_source.max_fps)
    logger.info(
        "Using go2rtc-backed protocol for printer %s (%s)",
        printer_id,
        type(camera_source).__name__,
    )

    # Track stream start time. Set only if absent so the value reflects when
    # the SHARED upstream first started streaming, not when each new viewer
    # attached — otherwise /camera/status would report stream_uptime jumping
    # backward whenever a second viewer joins. The upstream generator's
    # finally clears this entry when the upstream actually ends.
    _stream_start_times.setdefault(printer_id, time.time())
    # Last-requested fps, surfaced by /camera/stream-info. Not necessarily
    # the upstream's actual rate (see note below on fps being fixed by the
    # first viewer) — just what the current viewer asked for.
    _stream_fps_target[printer_id] = fps

    # Fan-out broadcaster (#1089): one upstream connection per printer, shared
    # across all viewers. Most Bambu printers only allow a single concurrent
    # camera connection, so opening the same printer in two tabs would
    # otherwise kick the first viewer off. The broadcaster owns the single
    # upstream and the per-viewer disconnect handling.
    #
    # Note: the upstream's fps is fixed by the first viewer who creates the
    # broadcaster. Concurrent viewers share that rate; new viewers after
    # teardown create a fresh broadcaster at their requested fps.
    fanout_key = f"printer-{printer_id}"
    upstream_stream_id = f"{printer_id}-fanout"

    def _factory(disconnect_event: asyncio.Event):
        # Re-bind locals into the closure so the async generator below sees
        # them — disconnect_event is owned by the broadcaster and signalled
        # when the last subscriber leaves (after the grace window).
        return generate_go2rtc_mjpeg_stream(
            camera_source=camera_source,
            ip_address=printer.ip_address,
            model=printer.model,
            fps=fps,
            stream_id=upstream_stream_id,
            disconnect_event=disconnect_event,
            printer_id=printer_id,
        )

    # Subscribe with a one-shot retry to close a tiny race: the grace-window
    # teardown can flip the broadcaster to `stopped=True` between the registry
    # lookup and our subscribe call. The retry forces the registry to mint a
    # fresh broadcaster (since the now-stopped one is replaced), and the second
    # subscribe is guaranteed to land on it before any teardown can fire.
    broadcaster: MjpegBroadcaster = await get_or_create_broadcaster(fanout_key, _factory)
    try:
        queue = await broadcaster.subscribe()
    except RuntimeError:
        broadcaster = await get_or_create_broadcaster(fanout_key, _factory)
        queue = await broadcaster.subscribe()
    logger.info(
        "Camera viewer attached to %s (subscribers=%d)",
        fanout_key,
        broadcaster.subscriber_count,
    )

    async def _is_disconnected() -> bool:
        try:
            return await request.is_disconnected()
        except Exception:
            # Older starlette/uvicorn can raise during teardown — treat that
            # as "client gone" so the subscriber cleanly unsubscribes.
            return True

    def _log_detach(remaining: int) -> None:
        logger.info("Camera viewer detached from %s (subscribers=%d)", fanout_key, remaining)

    async def _generate():
        async for chunk in iter_subscriber(
            broadcaster,
            queue,
            is_disconnected=_is_disconnected,
            on_unsubscribe=_log_detach,
        ):
            yield chunk

    return StreamingResponse(
        _generate(),
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
    auth_required = False
    try:
        async with async_session() as db:
            auth_required = await is_auth_enabled(db)
    except Exception:
        logger.error("Camera MSE auth probe failed; refusing connection", exc_info=True)
        await websocket.close(code=4401)
        return

    if auth_required and (not token or not await verify_camera_stream_token(token)):
        logger.info("Camera MSE connect refused: missing/invalid token (printer_id=%s)", printer_id)
        await websocket.close(code=4401)
        return

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

    upstream_url = f"{settings.go2rtc_api_url.replace('http://', 'ws://').replace('https://', 'wss://')}/api/ws?src={go2rtc_name}"

    try:
        # max_size raised from the 1MB default — a 1080p H.264 keyframe
        # fragment can exceed that, which would otherwise get the upstream
        # connection dropped by the client library itself.
        async with websockets.connect(upstream_url, open_timeout=10, max_size=8 * 1024 * 1024) as upstream:

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

            pump_a = asyncio.create_task(browser_to_go2rtc())
            pump_b = asyncio.create_task(go2rtc_to_browser())
            try:
                await asyncio.wait({pump_a, pump_b}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (pump_a, pump_b):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(pump_a, pump_b, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    except (OSError, websockets.exceptions.WebSocketException) as e:
        logger.warning("Camera MSE upstream connection failed for printer %s: %s", printer_id, e)
    finally:
        await go2rtc_registry.release(printer_id)
        logger.info("Camera MSE stream ended for printer %s", printer_id)


@router.api_route("/{printer_id}/camera/stop", methods=["GET", "POST"])
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
    remaining_subscribers = get_subscriber_count(broadcaster_key)
    if remaining_subscribers >= 1:
        logger.info(
            "Skipping force-shutdown for printer %s: %d subscriber(s) still attached; "
            "natural cleanup will tear down when last viewer disconnects",
            printer_id,
            remaining_subscribers,
        )
        return {"stopped": 0, "skipped": True}

    stopped = 0

    # Tear down the fan-out broadcaster first (#1089). This cleanly notifies
    # all subscribed viewers and asks the upstream generator to stop
    # reconnecting before we fall back to forcefully killing the process below.
    if await shutdown_broadcaster(broadcaster_key):
        logger.info("Shut down camera fan-out broadcaster for printer %s", printer_id)

    # Stop ffmpeg/RTSP streams
    to_remove = []
    for stream_id, process in list(_active_streams.items()):
        if stream_id.startswith(f"{printer_id}-"):
            to_remove.append(stream_id)
            # Signal the generator to stop reconnecting BEFORE killing the process
            event = _disconnect_events.get(stream_id)
            if event:
                event.set()
            if process.returncode is None:
                try:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except TimeoutError:
                        logger.warning("ffmpeg didn't terminate gracefully, killing (stream_id=%s)", stream_id)
                        process.kill()
                        await process.wait()
                    stopped += 1
                    logger.info("Terminated ffmpeg process for stream %s", stream_id)
                except ProcessLookupError:
                    pass  # Process already dead
                except OSError as e:
                    logger.warning("Error stopping stream %s: %s", stream_id, e)
            _spawned_ffmpeg_pids.pop(process.pid, None)

    for stream_id in to_remove:
        _active_streams.pop(stream_id, None)
        _disconnect_events.pop(stream_id, None)
        _stream_last_frame_times.pop(stream_id, None)

    logger.info("Stopped %s camera stream(s) for printer %s", stopped, printer_id)
    return {"stopped": stopped}


@router.get("/{printer_id}/camera/snapshot")
async def camera_snapshot(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    """Capture a single frame from the printer camera.

    Returns a JPEG image.

    Requires a stream token query param (?token=xxx) when auth is enabled.
    """
    import tempfile
    from pathlib import Path

    printer = await get_printer_or_404(printer_id, db)
    camera_source = get_camera_source(printer)

    if camera_source is None:
        # USB/v4l2 (or an unrecognised external type) — not go2rtc-backed
        # (see camera_source.py), so there's no fan-out buffer to reuse.
        from backend.app.services.external_camera import capture_frame

        frame_data = await capture_frame(
            printer.external_camera_url,
            printer.external_camera_type,
            timeout=15,
            snapshot_url=printer.external_camera_snapshot_url,
        )
        if not frame_data:
            raise HTTPException(
                status_code=503,
                detail="Failed to capture frame from external camera.",
            )
        return Response(
            content=frame_data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Disposition": f'inline; filename="snapshot_{printer_id}.jpg"',
            },
        )

    # Reuse the fan-out broadcaster's buffered frame when a viewer is already
    # watching — avoids opening a second concurrent connection on printers
    # (or external cameras) that allow only one at a time (e.g. X2D firmware
    # 01.01.00.00; see #1271). Buffered frame is <1s old while a viewer is
    # connected. Applies uniformly now: built-in RTSP, built-in
    # chamber-image, and external RTSP/MJPEG/snapshot are all go2rtc-backed.
    buffered = try_get_active_buffered_frame(printer_id)
    if buffered:
        return Response(
            content=buffered,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Disposition": f'inline; filename="snapshot_{printer_id}.jpg"',
            },
        )

    # No active stream — capture fresh. External cameras go through
    # external_camera.py's one-shot capture (same as before); built-in
    # cameras use the direct Bambu protocol capture.
    if printer.external_camera_enabled and printer.external_camera_url:
        from backend.app.services.external_camera import capture_frame

        frame_data = await capture_frame(
            printer.external_camera_url,
            printer.external_camera_type,
            timeout=15,
            snapshot_url=printer.external_camera_snapshot_url,
        )
        if not frame_data:
            raise HTTPException(
                status_code=503,
                detail="Failed to capture frame from external camera.",
            )
        return Response(
            content=frame_data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Disposition": f'inline; filename="snapshot_{printer_id}.jpg"',
            },
        )

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

        return Response(
            content=image_data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Disposition": f'inline; filename="snapshot_{printer_id}.jpg"',
            },
        )
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.get("/{printer_id}/camera/test")
async def test_camera(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Test camera connection for a printer.

    Returns success status and any error message.
    """
    printer = await get_printer_or_404(printer_id, db)

    result = await test_camera_connection(
        ip_address=printer.ip_address,
        access_code=printer.access_code,
        model=printer.model,
    )

    return result


@router.post("/{printer_id}/camera/diagnose")
async def diagnose_camera_route(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
):
    """Run staged diagnostics for a printer's camera path.

    Returns a structured result the frontend renders inline so users can
    self-diagnose "connection lost" before opening a ticket. See
    ``camera_diagnose`` for stage details and the live-stream shortcut.
    """
    from backend.app.services.camera_diagnose import diagnose_camera

    printer = await get_printer_or_404(printer_id, db)

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
    # Check if there's an active stream for this printer
    has_active_stream = False

    # Check external camera streams
    if printer_id in _active_external_streams:
        has_active_stream = True

    # Built-in cameras (RTSP via go2rtc, and chamber-image) — see
    # is_stream_active() for why this can't just look at _active_streams.
    if not has_active_stream and is_stream_active(printer_id):
        has_active_stream = True

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
    db: AsyncSession = Depends(get_db),
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
        "active": is_stream_active(printer_id) or printer_id in _active_external_streams,
    }


@router.post("/{printer_id}/camera/external/test")
async def test_external_camera(
    printer_id: int,
    url: str,
    camera_type: str,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
):
    """Test external camera connection.

    Args:
        printer_id: Printer ID (for authorization)
        url: Camera URL or USB device path to test
        camera_type: Camera type ("mjpeg", "rtsp", "snapshot", "usb")

    Returns:
        Dict with {success: bool, error?: str, resolution?: str}
    """
    # Verify printer exists (for authorization)
    await get_printer_or_404(printer_id, db)

    from backend.app.services.external_camera import test_connection

    return await test_connection(url, camera_type)


@router.get("/{printer_id}/camera/check-plate")
async def check_plate_empty(
    printer_id: int,
    plate_type: str | None = None,
    use_external: bool | None = None,
    include_debug_image: bool = False,
    db: AsyncSession = Depends(get_db),
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
        - light_warning: bool - True if chamber light is off
    """
    from backend.app.services.plate_detection import (
        check_plate_empty as do_check,
        is_plate_detection_available,
    )
    from backend.app.services.printer_manager import printer_manager

    # Check printer exists first (before OpenCV check)
    printer = await get_printer_or_404(printer_id, db)

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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CAMERA_VIEW),
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


def _scan_bambu_ffmpeg_pids() -> list[int]:
    """Scan /proc for ffmpeg processes that are ours.

    Matches Bambu RTSP streams and PrintOps-spawned external USB streams.
    This catches orphans that survive app restarts and are not in any tracking dict.
    """
    import os

    pids = []
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    cmdline = f.read()
                if b"ffmpeg" not in cmdline:
                    continue
                pid = int(entry)
                # Match both rtsp:// (via TLS proxy) and rtsps:// (direct).
                # For USB/v4l2 streams, only touch PIDs PrintOps spawned in
                # this session; a generic `ffmpeg -f v4l2` may belong to
                # another host application.
                if b"rtsp://bblp:" in cmdline or b"rtsps://bblp:" in cmdline or pid in _spawned_ffmpeg_pids:
                    pids.append(pid)
            except (OSError, PermissionError, ValueError):
                continue
    except OSError:
        pass
    return pids


async def cleanup_orphaned_streams():
    """Clean up orphaned ffmpeg processes and stale stream entries.

    Called periodically from the background task loop in main.py.

    Three-layer cleanup:
    1. /proc scan — finds ALL Bambu ffmpeg processes on the system, even those
       from previous app sessions. This is the nuclear safety net.
    2. _spawned_ffmpeg_pids — tracks PIDs spawned this session, catches orphans
       that were removed from _active_streams but not killed.
    3. _active_streams — kills stale entries with no recent frames.
    """
    import signal

    cleaned = 0
    now = time.time()
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)

    # Collect PIDs that are legitimately in-use (active stream, process alive)
    active_pids = {proc.pid for proc in _active_streams.values() if proc.returncode is None}

    # Also exclude PIDs from one-shot snapshot captures (Obico detection, finish photos, etc.)
    from backend.app.services.camera import _active_capture_pids

    active_pids |= _active_capture_pids

    # 1. /proc scan — catch ALL orphaned Bambu ffmpeg processes on the system.
    #    Any ffmpeg with rtsp(s)://bblp: that is NOT in an active stream is orphaned.
    for pid in _scan_bambu_ffmpeg_pids():
        if pid in active_pids:
            continue
        logger.info("Killing orphaned ffmpeg process found via /proc (pid=%d)", pid)
        try:
            os.kill(pid, kill_signal)
        except (ProcessLookupError, OSError):
            pass
        _spawned_ffmpeg_pids.pop(pid, None)
        cleaned += 1

    # 2. Clean up _spawned_ffmpeg_pids entries for dead processes
    for pid in list(_spawned_ffmpeg_pids):
        try:
            os.kill(pid, 0)  # existence check
        except (ProcessLookupError, OSError):
            _spawned_ffmpeg_pids.pop(pid, None)

    # 3. Clean up _active_streams entries with dead processes
    dead_streams = [sid for sid, proc in _active_streams.items() if proc.returncode is not None]
    for sid in dead_streams:
        proc = _active_streams.pop(sid, None)
        if proc:
            _spawned_ffmpeg_pids.pop(proc.pid, None)
        cleaned += 1

    # 4. Kill stale active streams (alive but no frames for >30s)
    # Uses per-stream timestamps to avoid false "fresh" readings from newer streams
    for sid, proc in list(_active_streams.items()):
        if proc.returncode is not None:
            continue
        # Per-stream frame time is authoritative; fall back to per-printer
        stream_last_frame = _stream_last_frame_times.get(sid)
        if stream_last_frame is None:
            try:
                printer_id = int(sid.split("-", 1)[0])
            except (ValueError, IndexError):
                continue
            stream_last_frame = _last_frame_times.get(printer_id)
        spawn_time = _spawned_ffmpeg_pids.get(proc.pid, now)
        if stream_last_frame is None:
            stream_last_frame = spawn_time
        if now - spawn_time > 60 and now - stream_last_frame > 30:
            logger.info("Killing stale ffmpeg stream %s (no frames for %.0fs)", sid, now - stream_last_frame)
            # Signal the generator to stop reconnecting
            event = _disconnect_events.get(sid)
            if event:
                event.set()
            try:
                proc.kill()
                await proc.wait()
            except (ProcessLookupError, OSError):
                pass
            _active_streams.pop(sid, None)
            _disconnect_events.pop(sid, None)
            _stream_last_frame_times.pop(sid, None)
            _spawned_ffmpeg_pids.pop(proc.pid, None)
            cleaned += 1

    if cleaned:
        logger.info("Cleaned up %d orphaned camera stream(s)", cleaned)
