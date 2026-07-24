"""Database-coordinated, bounded preview job lifecycle and protected result storage."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.document_layout import DocumentPreviewJob


class PreviewJobError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DocumentPreviewJobService:
    def __init__(self, *, storage_root: Path | None = None, ttl_seconds: int | None = None):
        self._root = Path(storage_root or settings.document_render_cache_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._ttl_seconds = ttl_seconds or settings.document_render_cache_ttl_seconds

    @staticmethod
    def cache_key(
        *,
        configuration_id: int,
        layout_lock_version: int,
        source_type: str,
        source_reference: str,
    ) -> str:
        material = json.dumps(
            {
                "configuration_id": configuration_id,
                "layout_lock_version": layout_lock_version,
                "source_reference": source_reference,
                "source_type": source_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    async def enqueue(
        self,
        session: AsyncSession,
        *,
        actor_id: int | None,
        business_profile_id: int,
        configuration_id: int,
        layout_lock_version: int,
        source_type: str,
        source_reference: str,
        now: datetime | None = None,
    ) -> tuple[DocumentPreviewJob, bool]:
        now = now or datetime.now(UTC)
        key = self.cache_key(
            configuration_id=configuration_id,
            layout_lock_version=layout_lock_version,
            source_type=source_type,
            source_reference=source_reference,
        )
        cached = await session.scalar(
            select(DocumentPreviewJob)
            .where(
                DocumentPreviewJob.actor_id == actor_id,
                DocumentPreviewJob.business_profile_id == business_profile_id,
                DocumentPreviewJob.cache_key == key,
                DocumentPreviewJob.status == "ready",
                DocumentPreviewJob.expires_at > now,
            )
            .order_by(DocumentPreviewJob.completed_at.desc())
            .limit(1)
        )
        if cached is not None:
            try:
                self.read_result(cached)
                return cached, True
            except PreviewJobError:
                cached.status = "failed"
                cached.findings = {"code": "PREVIEW_CACHE_INVALID"}

        job = DocumentPreviewJob(
            actor_id=actor_id,
            business_profile_id=business_profile_id,
            configuration_id=configuration_id,
            layout_lock_version=layout_lock_version,
            source_type=source_type,
            source_reference=source_reference,
            cache_key=key,
            status="queued",
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        session.add(job)
        await session.flush()
        return job, False

    async def claim(self, session: AsyncSession, public_id: str) -> DocumentPreviewJob:
        result = await session.execute(
            update(DocumentPreviewJob)
            .where(
                DocumentPreviewJob.public_id == public_id,
                DocumentPreviewJob.status == "queued",
            )
            .values(status="running")
        )
        if result.rowcount != 1:
            raise PreviewJobError("PREVIEW_NOT_QUEUED")
        await session.flush()
        job = await session.scalar(
            select(DocumentPreviewJob).where(DocumentPreviewJob.public_id == public_id)
        )
        if job is None:
            raise PreviewJobError("PREVIEW_NOT_FOUND")
        return job

    async def complete(
        self,
        session: AsyncSession,
        job: DocumentPreviewJob,
        content: bytes,
        *,
        findings: dict | None = None,
        now: datetime | None = None,
    ) -> DocumentPreviewJob:
        if job.status != "running" or not content.startswith(b"%PDF-"):
            raise PreviewJobError("PREVIEW_RESULT_INVALID")
        now = now or datetime.now(UTC)
        digest = hashlib.sha256(content).hexdigest()
        target = self._result_path(job.public_id)
        job_id = job.id
        self._atomic_write(target, content)
        result = await session.execute(
            update(DocumentPreviewJob)
            .where(DocumentPreviewJob.id == job.id, DocumentPreviewJob.status == "running")
            .values(
                status="ready",
                result_storage_key=target.name,
                result_sha256=digest,
                findings=findings or {},
                completed_at=now,
            )
        )
        if result.rowcount != 1:
            target.unlink(missing_ok=True)
            raise PreviewJobError("PREVIEW_STATE_CONFLICT")
        await session.flush()
        session.expire(job)
        refreshed = await session.get(DocumentPreviewJob, job_id)
        if refreshed is None:
            raise PreviewJobError("PREVIEW_NOT_FOUND")
        return refreshed

    async def fail(
        self,
        session: AsyncSession,
        job_id: int,
        *,
        code: str,
        now: datetime | None = None,
    ) -> None:
        await session.execute(
            update(DocumentPreviewJob)
            .where(
                DocumentPreviewJob.id == job_id,
                DocumentPreviewJob.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                findings={"code": code},
                completed_at=now or datetime.now(UTC),
            )
        )

    async def expire(self, session: AsyncSession, *, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        jobs = (
            await session.scalars(
                select(DocumentPreviewJob).where(
                    DocumentPreviewJob.expires_at <= now,
                    DocumentPreviewJob.status.in_(("queued", "running", "ready", "failed")),
                )
            )
        ).all()
        for job in jobs:
            if job.result_storage_key:
                self._safe_storage_path(job.result_storage_key).unlink(missing_ok=True)
            job.status = "expired"
        await session.flush()
        return len(jobs)

    async def recover_interrupted(self, session: AsyncSession) -> int:
        result = await session.execute(
            update(DocumentPreviewJob)
            .where(DocumentPreviewJob.status == "running")
            .values(
                status="failed",
                findings={"code": "PREVIEW_INTERRUPTED"},
                completed_at=datetime.now(UTC),
            )
        )
        return int(result.rowcount or 0)

    def read_result(self, job: DocumentPreviewJob) -> bytes:
        if job.status != "ready" or not job.result_storage_key or not job.result_sha256:
            raise PreviewJobError("PREVIEW_NOT_READY")
        path = self._safe_storage_path(job.result_storage_key)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PreviewJobError("PREVIEW_RESULT_UNAVAILABLE") from exc
        if hashlib.sha256(content).hexdigest() != job.result_sha256:
            raise PreviewJobError("PREVIEW_CACHE_INVALID")
        return content

    def _result_path(self, public_id: str) -> Path:
        if not public_id or any(char not in "0123456789abcdef-" for char in public_id.lower()):
            raise PreviewJobError("PREVIEW_ID_INVALID")
        return self._safe_storage_path(f"preview-{public_id}.pdf")

    def _safe_storage_path(self, key: str) -> Path:
        target = (self._root / key).resolve()
        if target.parent != self._root or target.suffix.lower() != ".pdf":
            raise PreviewJobError("PREVIEW_STORAGE_INVALID")
        return target

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = ["DocumentPreviewJobService", "PreviewJobError"]
