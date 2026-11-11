"""Cancellable timelapse edits with optimistic media-version checks."""

import asyncio
import hashlib
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

from sqlalchemy import select

from backend.app.core import database
from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.schemas.timelapse import ProcessResponse, TimelapseJobResponse
from backend.app.services.archive_merge import finish_archive_media_edit, start_archive_media_edit
from backend.app.services.timelapse_processor import TimelapseProcessor
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

logger = logging.getLogger(__name__)
_JOB_RETENTION_SECONDS = 3600
Scope = tuple[str, int]
JobStatus = Literal["running", "completed", "failed", "cancelled"]


class TimelapseConflict(Exception):
    pass


def timelapse_source(relative_path: str) -> Path:
    return safe_join_under(settings.base_dir, relative_path, http=False)


def source_version(path: Path) -> str:
    metadata = path.stat()
    if not path.is_file():
        raise FileNotFoundError
    revision = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)
    return hashlib.sha256(repr(revision).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class EditSpec:
    archive_id: int
    relative_path: str
    source: Path
    version: str
    trim_start: float
    trim_end: float | None
    speed: float
    destination: Path
    replace: bool
    audio_suffix: str | None


@dataclass(slots=True)
class TimelapseJob:
    archive_id: int
    owner: Scope
    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = "running"
    progress: float | None = None
    output_path: str | None = None
    message: str | None = None
    finished_at: float | None = None
    cancellation_requested: bool = False
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    def update_progress(self, value: float) -> None:
        if math.isfinite(value):
            self.progress = max(self.progress or 0.0, min(0.99, value))

    def response(self) -> TimelapseJobResponse:
        return TimelapseJobResponse(
            job_id=self.job_id,
            status=self.status,
            progress=self.progress,
            output_path=self.output_path,
            message=self.message,
        )


_jobs: dict[int, TimelapseJob] = {}


async def _verify_source(spec: EditSpec) -> None:
    async with database.async_session() as session:
        relative_path = await session.scalar(
            select(PrintArchive.timelapse_path).where(
                PrintArchive.id == spec.archive_id, PrintArchive.deleted_at.is_(None)
            )
        )
    try:
        source = timelapse_source(relative_path) if relative_path == spec.relative_path else None
        if source == spec.source and source_version(source) == spec.version:
            return
    except (OSError, PathTraversalError):
        pass
    raise TimelapseConflict("The timelapse changed. Reopen the editor and try again.")


async def render_edit(spec: EditSpec, audio: bytes | None, job: TimelapseJob | None = None) -> ProcessResponse:
    await _verify_source(spec)
    # The temporary file lives beside the source to permit an atomic replace.
    with tempfile.TemporaryDirectory(prefix=".timelapse-edit-", dir=spec.source.parent) as directory:
        scratch = Path(directory)
        audio_path = None
        if audio is not None and spec.audio_suffix is not None:
            audio_path = safe_join_under(scratch, f"audio{spec.audio_suffix}", http=False)
            audio_path.write_bytes(audio)
        encoded = scratch / "output.mp4"
        processed = await TimelapseProcessor(spec.source).process(
            output_path=encoded,
            trim_start=spec.trim_start,
            trim_end=spec.trim_end,
            speed=spec.speed,
            audio_path=audio_path,
            on_progress=job.update_progress if job else None,
        )
        if not processed:
            raise RuntimeError("Video processing failed")
        await _verify_source(spec)
        if spec.replace:
            os.replace(encoded, spec.source)
            message = "Timelapse replaced successfully"
        else:
            try:
                # A new edit never overwrites a file created after the initial check.
                os.link(encoded, spec.destination)
            except FileExistsError as exc:
                raise TimelapseConflict("A timelapse with this filename already exists.") from exc
            message = f"Saved as {spec.destination.name}"

    return ProcessResponse(
        status="completed",
        output_path=str(spec.destination.relative_to(settings.base_dir.resolve())),
        message=message,
    )


def get_job(archive_id: int, owner: Scope, job_id: str | None = None) -> TimelapseJob | None:
    job = _jobs.get(archive_id)
    if job and job.owner == owner and (job_id is None or job.job_id == job_id):
        return job
    return None


def start_job(spec: EditSpec, audio: bytes | None, owner: Scope) -> TimelapseJob:
    for archive_id, job in list(_jobs.items()):
        if job.finished_at is not None and monotonic() - job.finished_at > _JOB_RETENTION_SECONDS:
            del _jobs[archive_id]
    if not start_archive_media_edit(spec.archive_id):
        raise TimelapseConflict("Archive media is already being changed")
    job = TimelapseJob(spec.archive_id, owner)
    _jobs[spec.archive_id] = job
    job.task = asyncio.create_task(_run_job(job, spec, audio))
    job.task.add_done_callback(lambda task: _finish_job(job, task))
    return job


async def _run_job(job: TimelapseJob, spec: EditSpec, audio: bytes | None) -> None:
    try:
        result = await render_edit(spec, audio, job)
    except TimelapseConflict as exc:
        job.status = "failed"
        job.message = str(exc)
    except TimeoutError:
        job.status = "failed"
        job.message = "Timelapse processing timed out."
    except Exception:
        logger.exception("Timelapse processing failed for archive %s", spec.archive_id)
        job.status = "failed"
        job.message = "Timelapse processing failed."
    else:
        job.status = "completed"
        job.progress = 1.0
        job.message = result.message
        job.output_path = result.output_path


def _finish_job(job: TimelapseJob, task: asyncio.Task[None]) -> None:
    if task.cancelled():
        job.status = "cancelled"
    job.finished_at = monotonic()
    job.task = None
    finish_archive_media_edit(job.archive_id)


async def cancel_job(job: TimelapseJob) -> None:
    if (task := job.task) is not None and not task.done():
        if not job.cancellation_requested:
            job.cancellation_requested = True
            task.cancel()
        await asyncio.shield(asyncio.gather(task, return_exceptions=True))


async def cancel_all() -> None:
    await asyncio.gather(*(cancel_job(job) for job in list(_jobs.values())))
    _jobs.clear()
