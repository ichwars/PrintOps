"""Layer-based timelapse for external cameras.

Captures a frame on each layer change and stitches them into a video on print completion.
"""

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backend.app.core.config import settings
from backend.app.services.camera import apply_camera_rotation
from backend.app.services.external_camera import capture_frame
from backend.app.services.subprocess_deadline import StepDeadlineExceeded, communicate_with_deadline
from backend.app.utils.ffmpeg_limits import STITCH_SCALE_FILTER, X264_BOUNDED_ARGS, reap_ffmpeg

logger = logging.getLogger(__name__)

# Active timelapse sessions: {printer_id: TimelapseSession}
_active_sessions: dict[int, "TimelapseSession"] = {}
_finalizing_dirs: set[Path] = set()
KEPT_FRAMES_MARKER = "STITCH_FAILED"
KEEP_FAILED_FRAMES_SECONDS = 24 * 60 * 60


def stitch_timeout(frame_count: int) -> float:
    return min(max(300.0, frame_count * 0.5), 3600.0)


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


@dataclass
class TimelapseSession:
    """Active timelapse recording session."""

    printer_id: int
    archive_id: int | None
    camera_url: str
    camera_type: str
    snapshot_url: str | None = None  # Optional single-frame override; #1177
    rotation: int = 0
    last_layer: int = -1
    frame_count: int = 0
    session_id: str = field(default_factory=lambda: f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex}")
    frames_dir: Path = field(init=False)
    stitch_started: bool = field(default=False, init=False)

    def __post_init__(self):
        self.frames_dir = settings.base_dir / "timelapse_frames" / str(self.printer_id) / self.session_id
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created timelapse session %s for printer %s", self.session_id, self.printer_id)

    async def capture_layer(self, layer_num: int) -> bool:
        """Capture frame if layer changed.

        Args:
            layer_num: Current layer number from printer

        Returns:
            True if frame was captured, False otherwise
        """
        # Only capture if layer increased
        if layer_num <= self.last_layer:
            return False

        self.last_layer = layer_num

        try:
            frame_data = await capture_frame(
                self.camera_url, self.camera_type, snapshot_url=self.snapshot_url, printer_id=self.printer_id
            )
            if frame_data:
                if self.rotation:
                    frame_data = await asyncio.to_thread(apply_camera_rotation, frame_data, self.rotation, logger)
                frame_path = self.frames_dir / f"layer_{layer_num:05d}.jpg"
                await asyncio.to_thread(frame_path.write_bytes, frame_data)
                self.frame_count += 1
                logger.debug(
                    "Captured layer %s for printer %s (frame %s)", layer_num, self.printer_id, self.frame_count
                )
                return True
            else:
                logger.warning("Failed to capture frame for layer %s", layer_num)
                return False
        except Exception as e:
            logger.error("Error capturing timelapse frame: %s", e)
            return False

    async def stitch(self, output_path: Path, fps: int = 30) -> bool:
        """Create MP4 from captured frames using ffmpeg.

        Args:
            output_path: Path for output video file
            fps: Frames per second for output video

        Returns:
            True if stitching succeeded, False otherwise
        """
        if self.frame_count == 0:
            logger.warning("No frames to stitch")
            return False

        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            logger.error("ffmpeg not found - required for timelapse stitching")
            return False

        # Find all frame files and create a sequential list
        # This handles gaps in layer numbers (e.g., if some captures failed)
        frame_files = sorted(frame for frame in self.frames_dir.glob("layer_*.jpg") if frame.stem[6:].isdigit())
        if not frame_files:
            logger.warning("No frame files found in timelapse directory")
            return False

        # Create a concat file listing all frames
        concat_file = self.frames_dir / "frames.txt"
        try:
            with open(concat_file, "w") as f:
                for frame in frame_files:
                    # Each frame shown for 1/fps duration
                    f.write(f"file '{frame.name}'\n")
                    f.write(f"duration {1.0 / fps}\n")
                # Add last frame again (required by concat demuxer)
                if frame_files:
                    f.write(f"file '{frame_files[-1].name}'\n")
        except Exception as e:
            logger.error("Failed to create concat file: %s", e)
            return False

        # Use ffmpeg concat demuxer for variable-gap frame sequences
        cmd = [
            ffmpeg,
            "-y",  # Overwrite output
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(concat_file),
            "-vf",
            STITCH_SCALE_FILTER,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "23",
            *X264_BOUNDED_ARGS,
            str(output_path),
        ]

        self.mark_kept()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.frames_dir),  # Run in frames dir so relative paths work
            )

            self.stitch_started = True
            _, stderr = await communicate_with_deadline(
                process, timeout=stitch_timeout(len(frame_files)), step="Timelapse stitching"
            )

            if process.returncode != 0:
                logger.error("ffmpeg timelapse stitch failed: %s", stderr.decode()[:500])
                return False

            logger.info("Created timelapse video: %s (%s frames)", output_path, self.frame_count)
            return True

        except StepDeadlineExceeded as error:
            logger.error("%s (%s frames)", error, len(frame_files))
            return False
        except Exception as e:
            logger.error("Timelapse stitch failed: %s", e)
            return False
        finally:
            await reap_ffmpeg(process)

    def mark_kept(self) -> None:
        try:
            marker = self.frames_dir / KEPT_FRAMES_MARKER  # SEC-PATH-OK: fixed internal basename.
            marker.write_text("Frames retained for 24 hours. Use frames.txt to encode them again.\n", encoding="utf-8")
        except OSError as error:
            logger.warning("Could not mark timelapse frames for retention: %s", error)

    def cleanup(self):
        """Remove temporary frames directory."""
        try:
            if self.frames_dir.exists():
                shutil.rmtree(self.frames_dir, ignore_errors=True)
                logger.info("Cleaned up timelapse frames for session %s", self.session_id)
        except Exception as e:
            logger.warning("Failed to cleanup timelapse frames: %s", e)


def start_session(
    printer_id: int,
    archive_id: int | None,
    url: str,
    cam_type: str,
    snapshot_url: str | None = None,
    rotation: int = 0,
) -> TimelapseSession:
    """Start new timelapse session for a printer.

    Args:
        printer_id: The printer ID
        archive_id: Associated print archive ID (optional)
        url: External camera URL
        cam_type: Camera type ("mjpeg", "rtsp", "snapshot")
        snapshot_url: Optional single-frame URL override; when set, layer captures
            fetch from it directly instead of opening the live stream. #1177.

    Returns:
        The new TimelapseSession
    """
    # Cancel any existing session
    cancel_session(printer_id)

    session = TimelapseSession(
        printer_id=printer_id,
        archive_id=archive_id,
        camera_url=url,
        camera_type=cam_type,
        snapshot_url=snapshot_url,
        rotation=rotation,
    )
    _active_sessions[printer_id] = session
    logger.info("Started timelapse session for printer %s", printer_id)
    return session


def get_session(printer_id: int) -> TimelapseSession | None:
    """Get active timelapse session for a printer."""
    return _active_sessions.get(printer_id)


async def on_layer_change(printer_id: int, layer_num: int):
    """Called on layer change - captures frame if session active.

    Args:
        printer_id: The printer ID
        layer_num: Current layer number
    """
    session = get_session(printer_id)
    if session:
        await session.capture_layer(layer_num)


async def on_print_complete(printer_id: int, *, expected_session: TimelapseSession | None = None) -> Path | None:
    """Stitch timelapse and return path. Cleans up session.

    Args:
        printer_id: The printer ID

    Returns:
        Path to stitched video, or None if no session or stitching failed
    """
    session = _active_sessions.get(printer_id)
    if session is None or (expected_session is not None and session is not expected_session):
        return None
    _finalizing_dirs.add(session.frames_dir)
    _active_sessions.pop(printer_id, None)
    output_path = session.frames_dir.parent / f"timelapse_{session.session_id}.mp4"
    success = False
    try:
        if not session.frame_count:
            return None
        success = await session.stitch(output_path)
        if success:
            return output_path
        return None
    except Exception as e:
        logger.error("Timelapse completion failed: %s", e)
        return None
    finally:
        try:
            if success or not session.stitch_started:
                session.cleanup()
            else:
                session.mark_kept()
            if not success:
                output_path.unlink(missing_ok=True)
        finally:
            _finalizing_dirs.discard(session.frames_dir)


def cancel_session(printer_id: int, *, expected_session: TimelapseSession | None = None):
    """Cancel and cleanup timelapse session (on print fail/cancel).

    Args:
        printer_id: The printer ID
    """
    session = _active_sessions.get(printer_id)
    if session is not None and (expected_session is None or session is expected_session):
        _active_sessions.pop(printer_id, None)
        session.cleanup()
        logger.info("Cancelled timelapse session for printer %s", printer_id)


def get_active_sessions() -> dict[int, TimelapseSession]:
    """Get all active timelapse sessions."""
    return _active_sessions.copy()


def cleanup_orphaned_timelapse_sessions(min_age_seconds: float = 300) -> int:
    root = settings.base_dir / "timelapse_frames"
    if not root.is_dir():
        return 0
    in_use = {session.frames_dir for session in _active_sessions.copy().values()} | _finalizing_dirs.copy()
    outputs = {folder.parent / f"timelapse_{folder.name}.mp4" for folder in in_use}
    now = time.time()
    removed = 0
    for printer_folder in root.iterdir():
        if not printer_folder.name.isdigit() or printer_folder.is_symlink() or not printer_folder.is_dir():
            continue
        for path in printer_folder.iterdir():
            if path in in_use or path in outputs or path.is_symlink():
                continue
            try:
                if path.is_dir():
                    marker = path / KEPT_FRAMES_MARKER
                    timestamp, retention = (
                        (marker.stat().st_mtime, KEEP_FAILED_FRAMES_SECONDS)
                        if marker.is_file()
                        else (path.stat().st_mtime, min_age_seconds)
                    )
                    if now - timestamp < retention:
                        continue
                    shutil.rmtree(path)
                elif path.name.startswith("timelapse_") and path.suffix == ".mp4":
                    if now - path.stat().st_mtime < min_age_seconds:
                        continue
                    path.unlink()
                else:
                    continue
                removed += 1
            except FileNotFoundError:
                continue
    return removed
