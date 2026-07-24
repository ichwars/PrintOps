"""Commercial-document lifecycle API with command-specific authorization."""

from __future__ import annotations

import re
from dataclasses import asdict
from hashlib import sha256
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import (
    RequireAnyPermissionIfAuthEnabled,
    RequirePermissionIfAuthEnabled,
)
from backend.app.core.database import get_db
from backend.app.core.paths import resolve_data_dir, safe_join
from backend.app.core.permissions import Permission
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.models.user import User
from backend.app.schemas.commercial_document import (
    CommercialDocumentArtifactRead,
    CommercialDocumentDraft,
    CommercialDocumentLineRead,
    CommercialDocumentRead,
    DocumentAuditEventRead,
    IssueDocumentCommand,
    ReasonedDocumentCommand,
    SuccessorDocumentCommand,
    TaxOverrideDocumentCommand,
    UpdateCommercialDocumentCommand,
    VersionedDocumentCommand,
)
from backend.app.services.commercial_documents import (
    DocumentValidationFailed,
    EInvoiceValidationFailed,
    InvalidDocumentTransition,
    IssuanceConflict,
    cancel_document,
    correct_document,
    create_draft,
    create_successor,
    issue_document,
    mark_ready,
    update_draft,
    validate_draft,
)
from backend.app.services.document_audit import append_audit
from backend.app.services.document_snapshot import IssuedPdfError
from backend.app.services.order_errors import (
    OrderDomainError,
    ResourceNotFoundError,
    VersionConflictError,
)

router = APIRouter(prefix="/commercial-documents", tags=["commercial-documents"])

_LOAD_OPTIONS = (
    selectinload(CommercialDocument.lines),
    selectinload(CommercialDocument.artifacts),
    selectinload(CommercialDocument.snapshot),
)


def _actor_id(actor: User | None) -> int | None:
    return actor.id if actor is not None else None


def _correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    if existing and 1 <= len(str(existing)) <= 128:
        return str(existing)
    return str(uuid4())


def _read(document: CommercialDocument) -> CommercialDocumentRead:
    return CommercialDocumentRead(
        id=document.id,
        document_type=document.document_type,
        business_profile_id=document.business_profile_id,
        customer_id=document.customer_id,
        number=document.number,
        external_issuer_number=document.external_issuer_number,
        technical_status=document.technical_status,
        business_status=document.business_status,
        payment_status=document.payment_status,
        issue_date=document.issue_date,
        service_date=document.service_date,
        due_date=document.due_date,
        language=document.language,
        currency=document.currency,
        subtotal_amount=document.subtotal_amount,
        tax_amount=document.tax_amount,
        total_amount=document.total_amount,
        open_amount=document.open_amount,
        content_options=dict(document.content_options or {}),
        tax_decision=dict(document.tax_decision or {}),
        lock_version=document.lock_version,
        created_at=document.created_at,
        updated_at=document.updated_at,
        lines=[CommercialDocumentLineRead.model_validate(item) for item in document.lines],
        artifacts=[_artifact_read(item) for item in document.artifacts],
        snapshot_sha256=document.snapshot.sha256 if document.snapshot is not None else None,
    )


def _artifact_role(artifact: DocumentArtifact) -> str:
    if artifact.kind == "xrechnung_xml":
        return "original"
    if artifact.kind == "pdf":
        return str((artifact.render_receipt or {}).get("original_role") or "original")
    return "component"


def _artifact_read(artifact: DocumentArtifact) -> CommercialDocumentArtifactRead:
    return CommercialDocumentArtifactRead(
        id=artifact.id,
        kind=artifact.kind,
        content_type=artifact.content_type,
        sha256=artifact.sha256,
        validation_status=artifact.validation_status,
        rule_versions=dict(artifact.rule_versions or {}),
        original_role=_artifact_role(artifact),
        layout_configuration_id=artifact.layout_configuration_id,
        layout_version=artifact.layout_version,
        layout_effective_sha256=artifact.layout_effective_sha256,
        renderer_version=artifact.renderer_version,
        validator_version=artifact.validator_version,
        export_manifest=dict((artifact.render_receipt or {}).get("export_manifest") or {}),
        created_at=artifact.created_at,
    )


async def _load(db: AsyncSession, document_id: int, *, lock: bool = False) -> CommercialDocument:
    statement = select(CommercialDocument).where(CommercialDocument.id == document_id).options(*_LOAD_OPTIONS)
    if lock:
        statement = statement.with_for_update()
    document = await db.scalar(statement)
    if document is None:
        raise ResourceNotFoundError(f"Commercial document {document_id} was not found")
    return document


def _error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    field_path: str | None = None,
    correction: str | None = None,
    rule_id: str | None = None,
    findings: list[dict] | None = None,
    current_version: int | None = None,
) -> NoReturn:
    detail = {
        "code": code,
        "area": "commercial_documents",
        "message": message,
        "field_path": field_path,
        "correction": correction,
        "rule_id": rule_id,
        "correlation_id": _correlation_id(request),
    }
    if findings is not None:
        detail["findings"] = findings
    if current_version is not None:
        detail["current_version"] = current_version
    raise HTTPException(status_code=status_code, detail=detail)


async def _raise_domain_error(
    request: Request,
    error: Exception,
    *,
    db: AsyncSession | None = None,
    document_id: int | None = None,
) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        _error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="document_not_found",
            message=str(error),
            correction="Reload the document list",
        )
    if isinstance(error, VersionConflictError):
        current_version = None
        if db is not None and document_id is not None:
            current_version = await db.scalar(
                select(CommercialDocument.lock_version).where(CommercialDocument.id == document_id)
            )
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="document_version_conflict",
            message=str(error),
            correction="Reload the document and repeat the command",
            current_version=current_version,
        )
    if isinstance(error, DocumentValidationFailed):
        findings = [asdict(item) for item in error.findings]
        primary = findings[0] if findings else {}
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="document_not_ready",
            message="The commercial document is not ready",
            field_path=primary.get("field_path"),
            correction="Correct all blocking document findings",
            rule_id=primary.get("code"),
            findings=findings,
        )
    if isinstance(error, EInvoiceValidationFailed):
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="einvoice_invalid",
            message=str(error),
            correction="Correct the E-invoice master data and validate again",
        )
    if isinstance(error, IssuedPdfError):
        status_code = status.HTTP_424_FAILED_DEPENDENCY
        if error.code == "RENDER_TIMEOUT":
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        elif error.code in {"RENDER_PAGE_LIMIT", "RENDER_MEMORY_LIMIT"}:
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        _error(
            request,
            status_code=status_code,
            code=error.code,
            message="The immutable PDF could not be produced",
            correction="Correct the reported layout/runtime prerequisite and retry issuance",
        )
    if isinstance(error, (InvalidDocumentTransition, IssuanceConflict, OrderDomainError)):
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="document_state_conflict",
            message=str(error),
            correction="Reload the document and check its current status",
        )
    if isinstance(error, ValueError):
        _error(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="document_command_invalid",
            message=str(error),
            correction="Correct the command fields",
        )
    raise error


def _reject_inline_tax_override(request: Request, document: CommercialDocumentDraft) -> None:
    if (document.tax_decision or {}).get("manual_override"):
        _error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="tax_override_command_required",
            message="Manual tax decisions require the dedicated tax override command",
            field_path="tax_decision.manual_override",
            correction="Use the tax-override endpoint with a reason",
        )


@router.get("", response_model=list[CommercialDocumentRead])
async def list_documents(
    business_profile_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    document_type: str | None = None,
    technical_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> list[CommercialDocumentRead]:
    statement = select(CommercialDocument).options(*_LOAD_OPTIONS)
    if business_profile_id is not None:
        statement = statement.where(CommercialDocument.business_profile_id == business_profile_id)
    if customer_id is not None:
        statement = statement.where(CommercialDocument.customer_id == customer_id)
    if document_type is not None:
        statement = statement.where(CommercialDocument.document_type == document_type)
    if technical_status is not None:
        statement = statement.where(CommercialDocument.technical_status == technical_status)
    rows = (await db.scalars(statement.order_by(CommercialDocument.created_at.desc()))).all()
    return [_read(row) for row in rows]


@router.post("", response_model=CommercialDocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    command: CommercialDocumentDraft,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_DRAFT),
) -> CommercialDocumentRead:
    _reject_inline_tax_override(request, command)
    try:
        document = await create_draft(db, command, actor_id=_actor_id(actor))
        await append_audit(
            db,
            action="create",
            object_type="commercial_document",
            object_id=document.id,
            actor_id=_actor_id(actor),
            reason=None,
            before=None,
            after={"technical_status": document.technical_status, "lock_version": document.lock_version},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        return _read(await _load(db, document.id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error)


@router.get("/{document_id}", response_model=CommercialDocumentRead)
async def get_document(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> CommercialDocumentRead:
    try:
        return _read(await _load(db, document_id))
    except Exception as error:
        await _raise_domain_error(request, error)


@router.get(
    "/{document_id}/artifacts",
    response_model=list[CommercialDocumentArtifactRead],
)
async def list_document_artifacts(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> list[CommercialDocumentArtifactRead]:
    try:
        document = await _load(db, document_id)
        return [_artifact_read(item) for item in document.artifacts]
    except Exception as error:
        await _raise_domain_error(request, error)


async def _artifact_for_document(
    db: AsyncSession,
    request: Request,
    document_id: int,
    artifact_id: int,
) -> DocumentArtifact:
    artifact = await db.get(DocumentArtifact, artifact_id)
    if artifact is None or artifact.document_id != document_id:
        _error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="document_artifact_not_found",
            message="The document artifact was not found",
            correction="Reload the document artifacts",
        )
    return artifact


@router.get("/{document_id}/artifacts/{artifact_id}/manifest")
async def get_document_artifact_manifest(
    document_id: int,
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> dict:
    artifact = await _artifact_for_document(db, request, document_id, artifact_id)
    return {
        "artifact": _artifact_read(artifact).model_dump(mode="json"),
        "export_manifest": dict((artifact.render_receipt or {}).get("export_manifest") or {}),
    }


@router.get("/{document_id}/artifacts/{artifact_id}/download")
async def download_document_artifact(
    document_id: int,
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_EXPORT),
) -> Response:
    artifact = await _artifact_for_document(db, request, document_id, artifact_id)
    failure_code = None
    content = b""
    if artifact.validation_status != "valid":
        failure_code = "artifact_not_valid"
    else:
        try:
            if artifact.storage_path:
                content = safe_join(resolve_data_dir(), artifact.storage_path).read_bytes()
            elif artifact.content is not None:
                content = artifact.content
            else:
                failure_code = "artifact_file_unavailable"
        except (OSError, ValueError):
            failure_code = "artifact_file_unavailable"
    if failure_code is None:
        expected_size = (artifact.validation_report or {}).get("byte_size")
        try:
            size_matches = expected_size is None or int(expected_size) == len(content)
        except (TypeError, ValueError):
            size_matches = False
        if sha256(content).hexdigest() != artifact.sha256 or not size_matches:
            failure_code = "artifact_integrity_failed"
    if failure_code is not None:
        await append_audit(
            db,
            action="integrity_failure",
            object_type="commercial_document",
            object_id=document_id,
            actor_id=_actor_id(actor),
            reason=None,
            before=None,
            after={"artifact_id": artifact.id, "code": failure_code},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code=failure_code,
            message="The immutable artifact failed its delivery integrity check",
            correction="Restore the artifact from a verified backup",
        )

    await append_audit(
        db,
        action="export",
        object_type="commercial_document",
        object_id=document_id,
        actor_id=_actor_id(actor),
        reason="Immutable document artifact downloaded",
        before=None,
        after={"artifact_id": artifact.id, "sha256": artifact.sha256},
        correlation_id=_correlation_id(request),
    )
    await db.commit()
    number = await db.scalar(select(CommercialDocument.number).where(CommercialDocument.id == document_id))
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", number or str(document_id)).strip("-.")
    extension = "pdf" if artifact.content_type == "application/pdf" else "xml"
    return Response(
        content,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_number or document_id}.{extension}"',
            "ETag": f'"{artifact.sha256}"',
            "Cache-Control": "private, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.patch("/{document_id}", response_model=CommercialDocumentRead)
async def patch_document(
    document_id: int,
    command: UpdateCommercialDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_DRAFT),
) -> CommercialDocumentRead:
    _reject_inline_tax_override(request, command.document)
    try:
        current = await _load(db, document_id, lock=True)
        before = {
            "technical_status": current.technical_status,
            "lock_version": current.lock_version,
        }
        await update_draft(db, document_id, command.expected_version, command.document)
        await append_audit(
            db,
            action="update",
            object_type="commercial_document",
            object_id=document_id,
            actor_id=_actor_id(actor),
            reason=None,
            before=before,
            after={"technical_status": "draft", "lock_version": command.expected_version + 1},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        return _read(await _load(db, document_id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.post("/{document_id}/validate")
async def validate_document(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequireAnyPermissionIfAuthEnabled(
        Permission.COMMERCIAL_DOCUMENTS_READ,
        Permission.COMMERCIAL_DOCUMENTS_DRAFT,
        Permission.COMMERCIAL_DOCUMENTS_APPROVE,
        Permission.COMMERCIAL_DOCUMENTS_ISSUE,
    ),
) -> dict:
    try:
        findings = await validate_draft(db, document_id)
    except Exception as error:
        await _raise_domain_error(request, error)
    payload = [asdict(item) for item in findings]
    if any(item.severity == "blocker" for item in findings):
        primary = payload[0]
        _error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="document_not_ready",
            message="The commercial document has blocking findings",
            field_path=primary["field_path"],
            correction="Correct all blocking document findings",
            rule_id=primary["code"],
            findings=payload,
        )
    return {"status": "ready", "findings": payload, "correlation_id": _correlation_id(request)}


@router.post("/{document_id}/ready", response_model=CommercialDocumentRead)
async def approve_document(
    document_id: int,
    command: VersionedDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_APPROVE),
) -> CommercialDocumentRead:
    try:
        current = await _load(db, document_id, lock=True)
        await mark_ready(db, document_id, command.expected_version)
        await append_audit(
            db,
            action="approve",
            object_type="commercial_document",
            object_id=document_id,
            actor_id=_actor_id(actor),
            reason=None,
            before={"technical_status": current.technical_status, "lock_version": command.expected_version},
            after={"technical_status": "ready", "lock_version": command.expected_version + 1},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        return _read(await _load(db, document_id))
    except DocumentValidationFailed as error:
        await db.commit()
        await _raise_domain_error(request, error)
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.post("/{document_id}/issue", response_model=CommercialDocumentRead)
async def issue_commercial_document(
    document_id: int,
    command: IssueDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_ISSUE),
) -> CommercialDocumentRead:
    try:
        document = await issue_document(
            db,
            document_id,
            command.expected_version,
            _actor_id(actor),
            command.idempotency_key,
            _correlation_id(request),
        )
        return _read(document)
    except Exception as error:
        await _raise_domain_error(request, error, db=db, document_id=document_id)


async def _require_version(
    db: AsyncSession,
    document_id: int,
    expected_version: int,
) -> CommercialDocument:
    document = await _load(db, document_id, lock=True)
    if document.lock_version != expected_version:
        raise VersionConflictError(f"Commercial document {document_id} has changed")
    return document


@router.post("/{document_id}/successor", response_model=CommercialDocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document_successor(
    document_id: int,
    command: SuccessorDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_CORRECT),
) -> CommercialDocumentRead:
    try:
        await _require_version(db, document_id, command.expected_version)
        successor = await create_successor(
            db,
            document_id,
            command.successor_type,
            actor_id=_actor_id(actor),
            relation_type=command.relation_type,
        )
        await append_audit(
            db,
            action="successor",
            object_type="commercial_document",
            object_id=document_id,
            actor_id=_actor_id(actor),
            reason=None,
            before=None,
            after={"successor_id": successor.id, "successor_type": command.successor_type},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        return _read(await _load(db, successor.id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.post("/{document_id}/correction", response_model=CommercialDocumentRead, status_code=status.HTTP_201_CREATED)
async def correct_commercial_document(
    document_id: int,
    command: ReasonedDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_CORRECT),
) -> CommercialDocumentRead:
    try:
        await _require_version(db, document_id, command.expected_version)
        correction = await correct_document(
            db,
            document_id,
            reason=command.reason,
            actor_id=_actor_id(actor),
        )
        await db.commit()
        return _read(await _load(db, correction.id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.post("/{document_id}/cancellation", response_model=CommercialDocumentRead, status_code=status.HTTP_201_CREATED)
async def cancel_commercial_document(
    document_id: int,
    command: ReasonedDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_CORRECT),
) -> CommercialDocumentRead:
    try:
        await _require_version(db, document_id, command.expected_version)
        cancellation = await cancel_document(
            db,
            document_id,
            reason=command.reason,
            actor_id=_actor_id(actor),
        )
        await db.commit()
        return _read(await _load(db, cancellation.id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.post("/{document_id}/tax-override", response_model=CommercialDocumentRead)
async def override_document_tax(
    document_id: int,
    command: TaxOverrideDocumentCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(
        Permission.COMMERCIAL_DOCUMENTS_DRAFT,
        Permission.COMMERCIAL_DOCUMENTS_TAX_OVERRIDE,
    ),
) -> CommercialDocumentRead:
    try:
        document = await _require_version(db, document_id, command.expected_version)
        if document.technical_status not in {"draft", "validation_failed", "ready"}:
            raise InvalidDocumentTransition("Issued tax evidence cannot be overridden")
        before = dict(document.tax_decision or {})
        document.tax_decision = {**command.tax_decision, "manual_override": True}
        document.lock_version += 1
        await append_audit(
            db,
            action="tax_override",
            object_type="commercial_document",
            object_id=document.id,
            actor_id=_actor_id(actor),
            reason=command.reason,
            before={"tax_decision": before},
            after={"tax_decision": dict(document.tax_decision)},
            correlation_id=_correlation_id(request),
        )
        await db.commit()
        return _read(await _load(db, document_id))
    except Exception as error:
        await db.rollback()
        await _raise_domain_error(request, error, db=db, document_id=document_id)


@router.get("/{document_id}/history", response_model=list[DocumentAuditEventRead])
async def get_document_history(
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_AUDIT_READ),
) -> list[DocumentAuditEventRead]:
    try:
        await _load(db, document_id)
    except Exception as error:
        await _raise_domain_error(request, error)
    rows = (
        await db.scalars(
            select(DocumentAuditEvent)
            .where(
                DocumentAuditEvent.object_type == "commercial_document",
                DocumentAuditEvent.object_id == document_id,
            )
            .order_by(DocumentAuditEvent.created_at, DocumentAuditEvent.id)
        )
    ).all()
    return [DocumentAuditEventRead.model_validate(row) for row in rows]
