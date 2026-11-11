"""External camera service.

Supports MJPEG streams, RTSP streams (via ffmpeg), HTTP snapshot URLs, and USB cameras.

Security Note: This service intentionally makes requests to user-configured camera URLs.
This is necessary functionality for external camera integration. URLs are validated
to ensure they are well-formed before use.
"""

import asyncio
import logging
import re
import shutil
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from pathlib import Path
from time import monotonic

import aiohttp

from backend.app.core.logging_filters import redact_camera_url, redact_url_credentials
from backend.app.services.camera import JPEG_END, parse_jpeg_dimensions
from backend.app.services.camera_source_security import (
    prepare_external_camera_url,
    safe_usb_device_path,
    sanitize_camera_url,
)
from backend.app.services.frozen_frame_watchdog import FrozenFrameWatchdog
from backend.app.utils.ffmpeg_limits import reap_ffmpeg

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024
_RTSP_PROTOCOL_WHITELIST = "rtsp,rtp,udp,tcp,tls,crypto"


def _url_preview(url: str | None) -> str:
    return (redact_camera_url(url) or "None")[:50]


def _stderr_preview(stderr: bytes, limit: int) -> str:
    text = stderr.decode(errors="replace")
    return (redact_url_credentials(text) or "")[:limit]


def _sanitize_camera_url(url: str, allowed_schemes: tuple[str, ...] = ("http", "https", "rtsp")) -> str | None:
    """Validate and sanitize camera URL, returning a safe reconstructed URL.

    This validates that the URL is well-formed, uses an allowed scheme,
    does not target cloud metadata services, and returns a reconstructed
    URL from validated components.

    Note: This intentionally allows user-provided URLs as that is the
    purpose of external camera configuration. Local network IPs are
    allowed since cameras are typically on the same LAN.

    Args:
        url: URL to validate and sanitize
        allowed_schemes: Tuple of allowed URL schemes

    Returns:
        Sanitized URL string if valid, None otherwise
    """
    return sanitize_camera_url(url, allowed_schemes)


def _validate_camera_url(url: str, allowed_schemes: tuple[str, ...] = ("http", "https", "rtsp")) -> bool:
    """Validate camera URL format (legacy wrapper).

    Args:
        url: URL to validate
        allowed_schemes: Tuple of allowed URL schemes

    Returns:
        True if URL is valid, False otherwise
    """
    return _sanitize_camera_url(url, allowed_schemes) is not None


_USB_VIDEO_NAME = re.compile(r"video(?:[0-9]|[1-9][0-9])")


def list_usb_cameras(dev_dir: Path = Path("/dev")) -> list[dict]:
    """List usable Linux V4L2 capture nodes visible to this process."""
    import subprocess

    tool = shutil.which("v4l2-ctl")
    candidates = sorted(
        (device for device in dev_dir.glob("video*") if _USB_VIDEO_NAME.fullmatch(device.name)),
        key=lambda device: int(device.name.removeprefix("video")),
    )
    cameras = []
    for device in candidates:
        info = {"device": f"/dev/{device.name}", "name": device.name, "capabilities": []}
        fallback = int(device.name.removeprefix("video")) % 2 == 0
        if tool:
            try:
                formats = subprocess.run(
                    [tool, "-d", str(device), "--list-formats"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if formats.returncode == 0:
                    values = sorted(set(re.findall(r"'(\w+)'", formats.stdout)))
                    if not values:
                        continue
                    info.update(capabilities=["capture"], formats=values)
                    fallback = True
                    details = subprocess.run(
                        [tool, "-d", str(device), "--info"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if details.returncode == 0:
                        for line in details.stdout.splitlines():
                            label, _, value = line.partition(":")
                            if label.strip() == "Card type" and value.strip():
                                info["name"] = value.strip()
                            elif label.strip() == "Driver name" and value.strip():
                                info["driver"] = value.strip()
            except (OSError, subprocess.TimeoutExpired):
                logger.debug("V4L2 device query failed for %s", device.name)
        if fallback:
            cameras.append(info)
    return cameras


def get_ffmpeg_path() -> str | None:
    """Get the path to ffmpeg executable."""
    # Try shutil.which first
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Check common locations (systemd services may have limited PATH)
    for common_path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if Path(common_path).exists():
            return common_path
    return None


async def capture_frame(
    url: str,
    camera_type: str,
    timeout: int = 15,
    snapshot_url: str | None = None,
    *,
    printer_id: int | None = None,
) -> bytes | None:
    """Capture single frame from external camera.

    Args:
        url: Live-stream URL (MJPEG stream, RTSP URL, HTTP snapshot URL, or USB device path).
        camera_type: "mjpeg", "rtsp", "snapshot", or "usb".
        timeout: Connection timeout in seconds.
        snapshot_url: Optional override for single-frame capture. When set, fetched
            via plain HTTP GET regardless of `camera_type`. Bypasses MJPEG warm-up
            handling on sources that expose a dedicated frame endpoint (e.g. go2rtc's
            `/api/frame.jpeg` reliably returns a clean image while the MJPEG stream's
            first frame is often the encoder's stale keyframe). #1177.
        printer_id: Reuse this printer's live camera when it owns the source.

    Returns:
        JPEG bytes or None on failure
    """
    if snapshot_url:
        logger.debug("capture_frame using snapshot override url=%s...", _url_preview(snapshot_url))
        return await _capture_snapshot(snapshot_url, timeout)
    if printer_id is not None:
        from backend.app.api.routes.camera import live_frame_for_capture

        watched, frame = await live_frame_for_capture(printer_id, external_source=(camera_type, url))
        if watched:
            return frame
    logger.debug("capture_frame called: type=%s, url=%s...", camera_type, _url_preview(url))
    if camera_type == "mjpeg":
        return await _capture_mjpeg_frame(url, timeout)
    elif camera_type == "rtsp":
        return await _capture_rtsp_frame(url, timeout)
    elif camera_type == "snapshot":
        return await _capture_snapshot(url, timeout)
    elif camera_type == "usb":
        return await _capture_usb_frame(url, timeout)
    else:
        logger.warning("Unknown camera type: %s", camera_type)
        return None


async def _capture_usb_frame(device: str, timeout: int) -> bytes | None:
    """Capture frame from USB camera using ffmpeg."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.error("ffmpeg not found - required for USB camera capture")
        return None

    safe_device = safe_usb_device_path(device)
    if safe_device is None:
        logger.error("Invalid or missing USB device path: %s", device)
        return None
    device = safe_device

    # Use ffmpeg to grab a single frame from USB camera
    cmd = [
        ffmpeg,
        "-f",
        "v4l2",
        "-i",
        device,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "2",
        "-",
    ]

    process = None
    try:
        logger.debug("Running USB capture: %s", " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        if process.returncode != 0:
            logger.error("ffmpeg USB capture failed: %s", stderr.decode()[:200])
            return None

        if not stdout or len(stdout) < 100:
            logger.error("ffmpeg returned empty or too small frame from USB camera")
            return None

        return stdout

    except TimeoutError:
        logger.warning("USB frame capture timed out after %ss", timeout)
        return None
    except OSError as e:
        logger.error("USB frame capture failed: %s", e)
        return None
    finally:
        await reap_ffmpeg(process)


async def _capture_mjpeg_frame(url: str, timeout: int) -> bytes | None:
    """Extract a single representative frame from an MJPEG stream.

    Many MJPEG sources — go2rtc most notably (#1177), and several IP cameras —
    emit a "warm-up" frame on the byte that follows connection accept: usually
    the last keyframe held in the encoder, which is often black or stale until
    the encoder catches up to live content. To return a frame that's actually
    representative of the scene we read past the first frame and return the
    second; if the connection closes / times out / hits the buffer cap before
    a second frame ever arrives we fall back to the first so callers still
    get *something* (better than degrading slow / single-frame streams to None,
    which would regress every code path that consumed pre-fix behaviour).

    Note: this function intentionally makes requests to user-configured URLs.
    External camera support requires connecting to user-specified camera
    endpoints. URL is sanitized and dangerous destinations are blocked.
    """
    prepared = await prepare_external_camera_url(url, ("http", "https"))
    if prepared is None:
        logger.error("Invalid MJPEG URL: %s...", _url_preview(url))
        return None

    jpeg_start = b"\xff\xd8"
    jpeg_end = b"\xff\xd9"
    first_frame: bytes | None = None  # warm-up frame; fallback if no second arrives
    buffer = b""

    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session,
            session.get(prepared.url, allow_redirects=False) as response,
        ):
            if response.status != 200:
                logger.error("MJPEG stream returned status %s", response.status)
                return None

            async for chunk in response.content.iter_chunked(8192):
                buffer += chunk

                # A single chunk can carry multiple frames (e.g. high-FPS sources)
                # or a partial frame. Drain every complete frame we already have
                # before pulling the next chunk.
                while True:
                    start_idx = buffer.find(jpeg_start)
                    if start_idx == -1:
                        # No frame start yet — drop trailing garbage, keep waiting.
                        break
                    end_idx = buffer.find(jpeg_end, start_idx + 2)
                    if end_idx == -1:
                        # Partial frame; trim already-discarded prefix so the
                        # buffer stays bounded across long-running streams.
                        if start_idx > 0:
                            buffer = buffer[start_idx:]
                        break
                    frame = buffer[start_idx : end_idx + 2]
                    buffer = buffer[end_idx + 2 :]
                    if first_frame is None:
                        first_frame = frame  # warm-up; keep but don't return yet
                        continue
                    return frame  # representative second frame

                if len(buffer) > 5 * 1024 * 1024:  # 5MB limit
                    logger.warning("MJPEG buffer exceeded 5MB without finding frame")
                    break  # exit chunk loop, fall through to first_frame fallback

    except TimeoutError:
        logger.warning("MJPEG frame capture timed out after %ss", timeout)
    except (aiohttp.ClientError, OSError) as e:
        logger.error("MJPEG frame capture failed: %s", e)
    finally:
        await prepared.close()

    # Stream ended / timed out / buffer cap before a second frame arrived.
    # Return whatever warm-up frame we managed to read; better an iffy frame
    # than None for callers that need *some* image (snapshot UX, plate-detect
    # CV, finish photo). None only if no frame ever arrived at all.
    return first_frame


async def _capture_rtsp_frame(url: str, timeout: int) -> bytes | None:
    """Capture frame from RTSP using ffmpeg.

    For rtsps:// URLs, a local TLS proxy is used to avoid GnuTLS issues.
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.error("ffmpeg not found - required for RTSP capture")
        return None

    prepared = await prepare_external_camera_url(url, ("rtsp", "rtsps"))
    if prepared is None:
        logger.error("Invalid RTSP URL: %s...", _url_preview(url))
        return None

    cmd = [
        ffmpeg,
        "-rtsp_transport",
        "tcp",
        "-protocol_whitelist",
        _RTSP_PROTOCOL_WHITELIST,
        "-i",
        prepared.url,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "2",
        "-",
    ]

    process = None
    try:
        logger.debug("Running ffmpeg RTSP capture...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        logger.debug(
            "ffmpeg returned: code=%s, stdout=%s bytes, stderr=%s bytes",
            process.returncode,
            len(stdout),
            len(stderr),
        )

        if process.returncode != 0:
            logger.error("ffmpeg RTSP capture failed: %s", _stderr_preview(stderr, 200))
            return None

        if not stdout or len(stdout) < 100:
            logger.error("ffmpeg returned empty or too small frame")
            return None

        return stdout

    except TimeoutError:
        logger.warning("RTSP frame capture timed out after %ss", timeout)
        return None
    except OSError as e:
        logger.error("RTSP frame capture failed: %s", e)
        return None
    finally:
        await reap_ffmpeg(process)
        await prepared.close()


def _transcode_to_jpeg(data: bytes) -> bytes | None:
    """Decode an arbitrary still image (PNG/WebP/BMP/GIF/...) and re-encode as JPEG.

    Some camera/proxy snapshot endpoints serve stills as PNG or WebP rather than
    JPEG. A browser opened directly at the URL renders those fine, but our MJPEG
    ``multipart/x-mixed-replace`` stream hard-labels every part
    ``Content-Type: image/jpeg`` — so a non-JPEG payload makes the browser reject
    the frame and drop the whole stream ("connection lost", #1902). Transcoding to
    JPEG keeps the stream genuinely MJPEG and also keeps the JPEG-only downstream
    (plate detection, Obico, finish photo) working.

    Returns None if the bytes cannot be decoded or the imaging libraries are unavailable.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        return buf.tobytes()
    except Exception as e:  # cv2 raises cv2.error (a subclass of Exception) on bad input
        logger.debug("Snapshot transcode to JPEG failed: %s", e)
        return None


async def _capture_snapshot(url: str, timeout: int) -> bytes | None:
    """Fetch snapshot from HTTP URL.

    Note: This function intentionally makes requests to user-configured URLs.
    External camera support requires connecting to user-specified camera endpoints.
    URL is sanitized and dangerous destinations are blocked.
    """
    prepared = await prepare_external_camera_url(url, ("http", "https"))
    if prepared is None:
        logger.error("Invalid snapshot URL: %s...", _url_preview(url))
        return None

    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session,
            session.get(prepared.url, allow_redirects=False) as response,
        ):
            if response.status != 200:
                logger.error("Snapshot URL returned status %s", response.status)
                return None
            if response.content_length is not None and response.content_length > MAX_SNAPSHOT_BYTES:
                logger.warning("Snapshot response exceeds %s-byte limit", MAX_SNAPSHOT_BYTES)
                return None

            body = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                if len(body) + len(chunk) > MAX_SNAPSHOT_BYTES:
                    logger.warning("Snapshot response exceeds %s-byte limit", MAX_SNAPSHOT_BYTES)
                    return None
                body.extend(chunk)
            data = bytes(body)
    except TimeoutError:
        logger.warning("Snapshot capture timed out after %ss", timeout)
        return None
    except (aiohttp.ClientError, OSError) as e:
        logger.error("Snapshot capture failed: %s", e)
        return None
    finally:
        await prepared.close()

    # Keep the JPEG fast path for responses with dimensions and an end marker.
    if data.endswith(JPEG_END) and parse_jpeg_dimensions(data) is not None:
        return data

    # Not JPEG. Many snapshot endpoints serve PNG/WebP/BMP — transcode to JPEG so
    # the browser's MJPEG stream (and JPEG-only downstream) keep working instead of
    # dropping the connection (#1902). Run off the event loop: cv2 decode/encode is
    # CPU-bound and this can be polled at up to 15 fps while a camera view is open.
    transcoded = await asyncio.to_thread(_transcode_to_jpeg, data)
    if transcoded is not None:
        logger.debug(
            "Transcoded non-JPEG snapshot (%d bytes, header %s) to JPEG",
            len(data),
            data[:4].hex(),
        )
        return transcoded

    logger.warning("External camera snapshot is not a decodable image (%d bytes)", len(data))
    return None


def jpeg_resolution(frame: bytes) -> str | None:
    dimensions = parse_jpeg_dimensions(frame)
    return f"{dimensions[0]}x{dimensions[1]}" if dimensions is not None else None


async def test_connection(url: str, camera_type: str) -> dict:
    """Test camera connection.

    Returns:
        Dict with {success: bool, error?: str, resolution?: str}
    """
    logger.info("Testing camera connection: type=%s, url=%s...", camera_type, _url_preview(url))
    try:
        frame = await capture_frame(url, camera_type, timeout=10)
        logger.info("Capture result: %s bytes", len(frame) if frame else 0)

        if frame:
            return {"success": True, "resolution": jpeg_resolution(frame)}
        else:
            return {"success": False, "error": "Failed to capture frame from camera"}

    except Exception as e:
        # Sanitize error message - don't expose internal details
        error_type = type(e).__name__
        logger.error("Camera connection test failed: %s", e)
        return {"success": False, "error": f"Connection failed: {error_type}"}


async def generate_mjpeg_stream(
    url: str,
    camera_type: str,
    fps: int = 10,
    *,
    on_process: Callable[[asyncio.subprocess.Process], None] | None = None,
    on_frame: Callable[[bytes], None] | None = None,
    stop_event: asyncio.Event | None = None,
) -> AsyncGenerator[bytes, None]:
    """Generator yielding MJPEG frames for streaming.

    Args:
        url: Camera URL or USB device path
        camera_type: "mjpeg", "rtsp", "snapshot", or "usb"
        fps: Target frames per second
        on_process: Called with spawned ffmpeg processes so callers can register
            external RTSP/USB streams for explicit stop and orphan cleanup.
        on_frame: Receives the JPEG before it is wrapped in the multipart boundary.
        stop_event: Stops reconnect loops after an explicit stop/client cleanup.

    Yields:
        MJPEG frame data with HTTP multipart boundaries
    """
    frame_interval = 1.0 / max(fps, 1)
    last_frame_time = 0.0

    def publish(frame: bytes) -> bytes:
        if on_frame is not None:
            on_frame(frame)
        return _format_mjpeg_frame(frame)

    if camera_type in ("mjpeg", "rtsp"):
        freeze = FrozenFrameWatchdog(adaptive=True)

        def open_session() -> AsyncGenerator[bytes, None]:
            if camera_type == "rtsp":
                return _stream_rtsp(url, fps, on_process=on_process, freeze=freeze)
            return _stream_mjpeg(url)

        async with aclosing(_reconnecting_frames(open_session, camera_type, stop_event)) as frames:
            async for frame in frames:
                current_time = monotonic()
                if camera_type == "rtsp" or current_time - last_frame_time >= frame_interval:
                    last_frame_time = current_time
                    yield publish(frame)

    elif camera_type == "usb":
        # Use ffmpeg to stream from USB camera
        async with aclosing(_stream_usb(url, fps, on_process=on_process)) as frames:
            async for frame in frames:
                yield publish(frame)

    elif camera_type == "snapshot":
        # Poll snapshot URL at interval
        while True:
            try:
                frame = await _capture_snapshot(url, timeout=10)
                if frame:
                    yield publish(frame)
                await asyncio.sleep(frame_interval)
            except asyncio.CancelledError:
                break
            except (aiohttp.ClientError, OSError) as e:
                logger.warning("Snapshot poll failed: %s", e)
                await asyncio.sleep(frame_interval)


async def _reconnecting_frames(
    open_session: Callable[[], AsyncGenerator[bytes, None]], camera_type: str, stop_event: asyncio.Event | None
) -> AsyncGenerator[bytes, None]:
    """Reconnect after a session delivered frames, until a session fails to start."""
    task = asyncio.current_task()
    while stop_event is None or not stop_event.is_set():
        frame_yielded = False
        async with aclosing(open_session()) as frames:
            async for frame in frames:
                frame_yielded = True
                yield frame
        if not frame_yielded or (task is not None and task.cancelling()):
            return
        if stop_event is not None and stop_event.is_set():
            return
        logger.info("External %s stream ended, reconnecting", camera_type)
        await asyncio.sleep(2)


def _format_mjpeg_frame(frame: bytes) -> bytes:
    """Format frame for MJPEG HTTP response."""
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
        b"\r\n" + frame + b"\r\n"
    )


async def _stream_mjpeg(url: str) -> AsyncGenerator[bytes, None]:
    """Stream frames from MJPEG URL.

    Note: This function intentionally makes requests to user-configured URLs.
    External camera support requires connecting to user-specified camera endpoints.
    URL is sanitized and dangerous destinations are blocked.
    """
    prepared = await prepare_external_camera_url(url, ("http", "https"))
    if prepared is None:
        logger.error("Invalid MJPEG stream URL: %s...", _url_preview(url))
        return

    try:
        timeout = aiohttp.ClientTimeout(total=None, sock_read=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(prepared.url, allow_redirects=False) as response,
        ):
            if response.status != 200:
                logger.error("MJPEG stream returned status %s", response.status)
                return

            buffer = b""
            jpeg_start = b"\xff\xd8"
            jpeg_end = b"\xff\xd9"

            async for chunk in response.content.iter_chunked(8192):
                buffer += chunk

                # Extract complete frames from buffer
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
                    yield frame

    except asyncio.CancelledError:
        logger.info("MJPEG stream cancelled")
    except (aiohttp.ClientError, OSError) as e:
        logger.error("MJPEG stream error: %s", e)
    finally:
        await prepared.close()


async def _stream_rtsp(
    url: str,
    fps: int,
    *,
    on_process: Callable[[asyncio.subprocess.Process], None] | None = None,
    freeze: FrozenFrameWatchdog | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream frames from RTSP URL via ffmpeg.

    For rtsps:// URLs, a local TLS proxy (Python OpenSSL) is used instead
    of relying on ffmpeg's GnuTLS backend, which has compatibility issues
    with some printer firmwares.
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.error("ffmpeg not found - required for RTSP streaming")
        return

    from backend.app.services.camera import rtsp_socket_timeout_flag

    prepared = await prepare_external_camera_url(url, ("rtsp", "rtsps"))
    if prepared is None:
        logger.error("Invalid RTSP stream URL: %s...", _url_preview(url))
        return

    cmd = [
        ffmpeg,
        "-rtsp_transport",
        "tcp",
        "-protocol_whitelist",
        _RTSP_PROTOCOL_WHITELIST,
        "-rtsp_flags",
        "prefer_tcp",
        # Socket I/O timeout name varies by ffmpeg version (#1504); see
        # `rtsp_socket_timeout_flag()` in services.camera.
        f"-{rtsp_socket_timeout_flag()}",
        "30000000",
        "-buffer_size",
        "1024000",
        "-max_delay",
        "500000",
        "-probesize",
        "32",
        "-analyzeduration",
        "0",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-i",
        prepared.url,
        "-f",
        "mjpeg",
        "-q:v",
        "5",
        "-r",
        str(fps),
        "-an",
        "-",
    ]

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if on_process is not None:
            on_process(process)

        # Brief check for immediate startup failures
        await asyncio.sleep(0.1)
        if process.returncode is not None:
            stderr = await process.stderr.read()
            logger.error("ffmpeg RTSP stream failed immediately: %s", _stderr_preview(stderr, 300))
            return

        buffer = b""
        jpeg_start = b"\xff\xd8"
        jpeg_end = b"\xff\xd9"
        if freeze is not None:
            freeze.begin_session()

        while True:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(8192), timeout=30.0)

                if not chunk:
                    break

                buffer += chunk

                # Extract complete frames
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
                    if freeze is not None and freeze.observe(frame, monotonic()):
                        logger.info("Rechecking external RTSP picture after %.0fs unchanged", freeze.unchanged_for)
                        return
                    yield frame

            except TimeoutError:
                logger.warning("RTSP stream read timeout")
                break

    except asyncio.CancelledError:
        logger.info("RTSP stream cancelled")
    except OSError as e:
        logger.error("RTSP stream error: %s", e)
    finally:
        try:
            if process is not None and process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
        except (TimeoutError, OSError):
            await reap_ffmpeg(process)
        finally:
            await prepared.close()


async def _stream_usb(
    device: str,
    fps: int,
    *,
    on_process: Callable[[asyncio.subprocess.Process], None] | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream frames from USB camera via ffmpeg."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.error("ffmpeg not found - required for USB camera streaming")
        return

    safe_device = safe_usb_device_path(device)
    if safe_device is None:
        logger.error("Invalid or missing USB device path: %s", device)
        return
    device = safe_device

    # ffmpeg command to stream from USB camera (v4l2)
    cmd = [
        ffmpeg,
        "-f",
        "v4l2",
        "-framerate",
        str(fps),
        "-i",
        device,
        "-f",
        "mjpeg",
        "-q:v",
        "5",
        "-r",
        str(fps),
        "-",
    ]

    process = None
    try:
        logger.info("Starting USB camera stream from %s at %s fps", device, fps)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if on_process is not None:
            on_process(process)

        # Give ffmpeg a moment to start and check for immediate failures
        await asyncio.sleep(0.5)
        if process.returncode is not None:
            stderr = await process.stderr.read()
            logger.error("ffmpeg USB stream failed immediately: %s", stderr.decode()[:300])
            return

        buffer = b""
        jpeg_start = b"\xff\xd8"
        jpeg_end = b"\xff\xd9"

        while True:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(8192), timeout=30.0)

                if not chunk:
                    break

                buffer += chunk

                # Extract complete frames
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
                    yield frame

            except TimeoutError:
                logger.warning("USB stream read timeout")
                break

    except asyncio.CancelledError:
        logger.info("USB stream cancelled")
    except OSError as e:
        logger.error("USB stream error: %s", e)
    finally:
        if process is not None and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except (TimeoutError, OSError):
                await reap_ffmpeg(process)
