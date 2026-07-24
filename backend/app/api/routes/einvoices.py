"""Protected E-invoice metadata, validation report, and verified downloads."""

from __future__ import annotations

import re
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.paths import resolve_data_dir
from backend.app.core.permissions import Permission
from backend.app.models.commercial_document import DocumentArtifact
from backend.app.models.user import User
from backend.app.services.document_audit import append_audit

router = APIRouter(prefix="/einvoices", tags=["einvoices"])


class EInvoiceArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    document_number: str | None
    kind: str
    content_type: str
    sha256: str
    validation_status: str
    rule_versions: dict
    original_role: str
    export_manifest: dict
    created_at: datetime


def _actor_id(actor: User | None) -> int | None:
    return actor.id if actor is not None else None


def _correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    if existing and 1 <= len(str(existing)) <= 128:
        return str(existing)
    return str(uuid4())


def _error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    correction: str,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "area": "einvoices",
            "message": message,
            "field_path": None,
            "correction": correction,
            "rule_id": None,
            "correlation_id": _correlation_id(request),
        },
    )


async def _load_artifact(
    db: AsyncSession,
    artifact_id: int,
    request: Request,
) -> DocumentArtifact:
    artifact = await db.scalar(
        select(DocumentArtifact)
        .where(DocumentArtifact.id == artifact_id)
        .options(selectinload(DocumentArtifact.document))
    )
    if artifact is None:
        _error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="einvoice_not_found",
            message=f"Electronic invoice artifact {artifact_id} was not found",
            correction="Reload the document artifacts",
        )
    return artifact


def _metadata(artifact: DocumentArtifact) -> EInvoiceArtifactRead:
    return EInvoiceArtifactRead(
        id=artifact.id,
        document_id=artifact.document_id,
        document_number=artifact.document.number if artifact.document is not None else None,
        kind=artifact.kind,
        content_type=artifact.content_type,
        sha256=artifact.sha256,
        validation_status=artifact.validation_status,
        rule_versions=dict(artifact.rule_versions or {}),
        original_role=("original" if artifact.kind == "xrechnung_xml" else "component"),
        export_manifest=dict((artifact.render_receipt or {}).get("export_manifest") or {}),
        created_at=artifact.created_at,
    )


def _open_artifact(
    artifact: DocumentArtifact,
    request: Request,
) -> tuple[BinaryIO, int]:
    if artifact.validation_status != "valid":
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="artifact_not_valid",
            message="Only successfully validated electronic invoices can be downloaded",
            correction="Correct and issue the electronic invoice again",
        )

    handle: BinaryIO
    if artifact.storage_path:
        relative = Path(artifact.storage_path)
        root = resolve_data_dir().resolve()
        target = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or (target != root and root not in target.parents):
            _error(
                request,
                status_code=status.HTTP_409_CONFLICT,
                code="artifact_integrity_failed",
                message="The stored artifact path is invalid",
                correction="Restore the artifact from a verified backup",
            )
        try:
            handle = target.open("rb")
        except OSError:
            _error(
                request,
                status_code=status.HTTP_404_NOT_FOUND,
                code="artifact_file_unavailable",
                message="The electronic invoice file is unavailable",
                correction="Restore the artifact from a verified backup",
            )
    elif artifact.content is not None:
        handle = BytesIO(artifact.content)
    else:
        _error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="artifact_file_unavailable",
            message="The electronic invoice file is unavailable",
            correction="Restore the artifact from a verified backup",
        )

    digest = sha256()
    size = 0
    try:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
            size += len(chunk)
        expected_size = (artifact.validation_report or {}).get("byte_size")
        try:
            size_matches = expected_size is None or int(expected_size) == size
        except (TypeError, ValueError):
            size_matches = False
        if digest.hexdigest() != artifact.sha256 or not size_matches:
            handle.close()
            _error(
                request,
                status_code=status.HTTP_409_CONFLICT,
                code="artifact_integrity_failed",
                message="The electronic invoice file no longer matches its immutable metadata",
                correction="Restore the artifact from a verified backup",
            )
        handle.seek(0)
        return handle, size
    except Exception:
        if not handle.closed:
            handle.close()
        raise


def _filename(artifact: DocumentArtifact) -> str:
    number = artifact.document.number if artifact.document is not None else None
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", number or str(artifact.document_id)).strip("-.")
    prefix = "XRechnung" if artifact.kind == "xrechnung_xml" else "ZUGFeRD"
    return f"{prefix}_{safe_number or artifact.id}.xml"


def _stream(handle: BinaryIO):
    try:
        while chunk := handle.read(64 * 1024):
            yield chunk
    finally:
        handle.close()


@router.get("/{artifact_id}", response_model=EInvoiceArtifactRead)
async def get_einvoice(
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> EInvoiceArtifactRead:
    return _metadata(await _load_artifact(db, artifact_id, request))


@router.get("/{artifact_id}/validation")
async def get_einvoice_validation(
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> dict:
    artifact = await _load_artifact(db, artifact_id, request)
    return {
        **dict(artifact.validation_report or {}),
        "artifact_id": artifact.id,
        "sha256": artifact.sha256,
        "rule_versions": dict(artifact.rule_versions or {}),
    }


@router.get("/{artifact_id}/manifest")
async def get_einvoice_manifest(
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> dict:
    artifact = await _load_artifact(db, artifact_id, request)
    return {
        "artifact": _metadata(artifact).model_dump(mode="json"),
        "export_manifest": dict((artifact.render_receipt or {}).get("export_manifest") or {}),
    }


@router.get("/{artifact_id}/download")
async def download_einvoice(
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_EXPORT),
) -> StreamingResponse:
    artifact = await _load_artifact(db, artifact_id, request)
    handle, size = _open_artifact(artifact, request)
    try:
        await append_audit(
            db,
            action="export",
            object_type="commercial_document",
            object_id=artifact.document_id,
            actor_id=_actor_id(actor),
            reason="Electronic invoice downloaded",
            before=None,
            after={"artifact_id": artifact.id, "sha256": artifact.sha256},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
    except Exception:
        handle.close()
        await db.rollback()
        raise

    filename = _filename(artifact)
    return StreamingResponse(
        _stream(handle),
        media_type=artifact.content_type or "application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(size),
            "ETag": f'"{artifact.sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
