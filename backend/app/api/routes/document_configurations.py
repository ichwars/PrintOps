"""Versioned document-configuration settings API."""

from __future__ import annotations

from dataclasses import asdict
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.models.document_configuration import DocumentConfiguration
from backend.app.models.user import User
from backend.app.schemas.commercial_document import DocumentAuditEventRead
from backend.app.schemas.document_configuration import (
    CreateConfigurationCommand,
    DocumentCatalogItem,
    DocumentCatalogResponse,
    DocumentConfigurationDetail,
    DocumentConfigurationSummary,
    EffectiveDocumentPolicy,
    EffectivePolicyRequest,
    PlaceholderCatalogResponse,
    PublishConfigurationRequest,
    UpdateConfigurationCommand,
    WithdrawConfigurationCommand,
)
from backend.app.services.document_audit import append_audit
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, PLACEHOLDERS, TEXT_BLOCK_PURPOSES, DocumentType
from backend.app.services.document_configuration import (
    clone_version,
    create_draft,
    load_configuration,
    publish,
    resolve_effective,
    to_draft_schema,
    update_draft,
    withdraw_scheduled,
)
from backend.app.services.document_policy_validation import ConfigurationNotReady, validate_policy
from backend.app.services.document_readiness import ReadinessReport, check_configuration
from backend.app.services.einvoice.validator import pinned_rule_versions
from backend.app.services.order_errors import (
    InvalidStateConflictError,
    OrderDomainError,
    ResourceNotFoundError,
    VersionConflictError,
)
from backend.app.services.tax_decision import TAX_RULES_2026_1

router = APIRouter(prefix="/document-configurations", tags=["document-configurations"])


def _actor_id(actor: User | None) -> int | None:
    return actor.id if actor is not None else None


def _summary(configuration: DocumentConfiguration) -> DocumentConfigurationSummary:
    publication = configuration.publication
    return DocumentConfigurationSummary(
        id=configuration.id,
        business_profile_id=configuration.business_profile_id,
        document_type=configuration.document_type,
        language=configuration.language,
        version=configuration.version,
        status=configuration.status,
        effective_from=configuration.effective_from,
        lock_version=configuration.lock_version,
        change_reason=configuration.change_reason,
        created_by_id=configuration.created_by_id,
        published_by_id=configuration.published_by_id,
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
        published_at=configuration.published_at,
        publication_validation_status=(publication.validation_status if publication is not None else None),
        rule_versions=(dict(publication.rule_versions or {}) if publication is not None else {}),
    )


def _detail(configuration: DocumentConfiguration) -> DocumentConfigurationDetail:
    try:
        policy = to_draft_schema(configuration)
        findings = [asdict(item) for item in validate_policy(policy)]
    except InvalidStateConflictError:
        policy = None
        findings = []
    return DocumentConfigurationDetail(**_summary(configuration).model_dump(), policy=policy, validation_findings=findings)


def _raise_domain_error(error: OrderDomainError) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "not_found"
    elif isinstance(error, VersionConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "version_conflict"
    elif isinstance(error, InvalidStateConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "invalid_state"
    else:
        raise error
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": str(error),
            "field_path": None,
            "correction": "Reload the configuration and correct the highlighted fields",
            "rule_id": None,
            "correlation_id": str(uuid4()),
        },
    )


def _raise_not_ready(findings) -> NoReturn:
    primary = findings[0] if findings else None
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "configuration_not_ready",
            "message": "Document configuration is not ready for publication",
            "field_path": primary.field_path if primary else None,
            "correction": getattr(primary, "correction", "Correct all blocking findings") if primary else None,
            "rule_id": primary.rule_id if primary else None,
            "correlation_id": str(uuid4()),
            "findings": [item.model_dump() if hasattr(item, "model_dump") else asdict(item) for item in findings],
        },
    )


def _correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    if existing and 1 <= len(str(existing)) <= 128:
        return str(existing)
    return str(uuid4())


async def _append_configuration_audit(
    db: AsyncSession,
    request: Request,
    *,
    action: str,
    configuration: DocumentConfiguration,
    actor_id: int | None,
    reason: str | None,
    before: dict | None,
) -> None:
    await append_audit(
        db,
        action=action,
        object_type="document_configuration",
        object_id=configuration.id,
        actor_id=actor_id,
        reason=reason,
        before=before,
        after=_summary(configuration).model_dump(mode="json"),
        correlation_id=_correlation_id(request),
    )
    await db.flush()


@router.get("/catalog", response_model=DocumentCatalogResponse)
async def get_catalog(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> DocumentCatalogResponse:
    return DocumentCatalogResponse(
        tax_rule_version=TAX_RULES_2026_1.version,
        einvoice_rule_versions=pinned_rule_versions(),
        document_types=[
            DocumentCatalogItem(
                key=document_type.value,
                einvoice=capability.einvoice,
                issuer_role=capability.issuer_role,
                has_payment_terms=capability.has_payment_terms,
                has_tax=capability.has_tax,
                allowed_successors=sorted(item.value for item in capability.allowed_successors),
            )
            for document_type, capability in DOCUMENT_CAPABILITIES.items()
        ]
    )


@router.get("/placeholders", response_model=PlaceholderCatalogResponse)
async def get_placeholders(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> PlaceholderCatalogResponse:
    return PlaceholderCatalogResponse(
        placeholders=sorted(PLACEHOLDERS),
        text_block_purposes=list(TEXT_BLOCK_PURPOSES),
    )


@router.post("/effective", response_model=EffectiveDocumentPolicy)
async def get_effective_policy(
    command: EffectivePolicyRequest,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> EffectiveDocumentPolicy:
    try:
        return await resolve_effective(
            db,
            command.business_profile_id,
            command.customer_id,
            command.document_type.value,
            command.language,
            command.document_overrides,
        )
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.get("/", response_model=list[DocumentConfigurationSummary])
async def list_configurations(
    business_profile_id: int | None = Query(default=None, gt=0),
    document_type: DocumentType | None = None,
    language: str | None = None,
    configuration_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> list[DocumentConfigurationSummary]:
    statement = select(DocumentConfiguration)
    if business_profile_id is not None:
        statement = statement.where(DocumentConfiguration.business_profile_id == business_profile_id)
    if document_type is not None:
        statement = statement.where(DocumentConfiguration.document_type == document_type.value)
    if language is not None:
        statement = statement.where(DocumentConfiguration.language == language)
    if configuration_status is not None:
        statement = statement.where(DocumentConfiguration.status == configuration_status)
    rows = (
        await db.scalars(
            statement.order_by(
                DocumentConfiguration.business_profile_id,
                DocumentConfiguration.document_type,
                DocumentConfiguration.language,
                DocumentConfiguration.version.desc(),
            )
        )
    ).all()
    return [_summary(row) for row in rows]


@router.post("/", response_model=DocumentConfigurationDetail, status_code=status.HTTP_201_CREATED)
async def create_configuration(
    command: CreateConfigurationCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_MANAGE),
) -> DocumentConfigurationDetail:
    try:
        configuration = await create_draft(db, command, _actor_id(actor))
        await _append_configuration_audit(
            db,
            request,
            action="create",
            configuration=configuration,
            actor_id=_actor_id(actor),
            reason=command.change_reason,
            before=None,
        )
        await db.commit()
        return _detail(configuration)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.get("/{configuration_id}", response_model=DocumentConfigurationDetail)
async def get_configuration(
    configuration_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> DocumentConfigurationDetail:
    try:
        return _detail(await load_configuration(db, configuration_id))
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.patch("/{configuration_id}", response_model=DocumentConfigurationDetail)
async def patch_configuration(
    configuration_id: int,
    command: UpdateConfigurationCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_MANAGE),
) -> DocumentConfigurationDetail:
    try:
        configuration = await update_draft(
            db,
            configuration_id,
            command.expected_version,
            command.patch,
            _actor_id(actor),
        )
        await _append_configuration_audit(
            db,
            request,
            action="update",
            configuration=configuration,
            actor_id=_actor_id(actor),
            reason=str(command.patch.get("change_reason") or "") or None,
            before={"lock_version": command.expected_version},
        )
        await db.commit()
        return _detail(configuration)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.post("/{configuration_id}/clone", response_model=DocumentConfigurationDetail, status_code=status.HTTP_201_CREATED)
async def clone_configuration(
    configuration_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_MANAGE),
) -> DocumentConfigurationDetail:
    try:
        configuration = await clone_version(db, configuration_id, _actor_id(actor))
        await _append_configuration_audit(
            db,
            request,
            action="clone",
            configuration=configuration,
            actor_id=_actor_id(actor),
            reason=None,
            before={"source_configuration_id": configuration_id},
        )
        await db.commit()
        return _detail(configuration)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.get("/{configuration_id}/readiness", response_model=ReadinessReport)
async def get_readiness(
    configuration_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> ReadinessReport:
    try:
        return await check_configuration(db, configuration_id)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.post("/{configuration_id}/publish", response_model=DocumentConfigurationDetail)
async def publish_configuration(
    configuration_id: int,
    command: PublishConfigurationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_MANAGE),
) -> DocumentConfigurationDetail:
    try:
        report = await check_configuration(db, configuration_id)
        blockers = [item for item in report.findings if item.severity == "blocker"]
        if blockers:
            _raise_not_ready(blockers)
        configuration = await publish(
            db,
            configuration_id,
            command.expected_version,
            command.effective_from,
            command.reason,
            _actor_id(actor),
            {"tax": TAX_RULES_2026_1.version, **pinned_rule_versions()},
        )
        await _append_configuration_audit(
            db,
            request,
            action="publication",
            configuration=configuration,
            actor_id=_actor_id(actor),
            reason=command.reason,
            before={"status": "draft", "lock_version": command.expected_version},
        )
        await db.commit()
        return _detail(configuration)
    except ConfigurationNotReady as error:
        _raise_not_ready(error.findings)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.post("/{configuration_id}/withdraw", response_model=DocumentConfigurationDetail)
async def withdraw_configuration(
    configuration_id: int,
    command: WithdrawConfigurationCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_MANAGE),
) -> DocumentConfigurationDetail:
    try:
        configuration = await withdraw_scheduled(
            db,
            configuration_id,
            command.expected_version,
            command.reason,
            _actor_id(actor),
        )
        await _append_configuration_audit(
            db,
            request,
            action="withdraw",
            configuration=configuration,
            actor_id=_actor_id(actor),
            reason=command.reason,
            before={"status": "scheduled", "lock_version": command.expected_version},
        )
        await db.commit()
        return _detail(configuration)
    except OrderDomainError as error:
        _raise_domain_error(error)


@router.get("/{configuration_id}/history", response_model=list[DocumentConfigurationSummary])
async def get_history(
    configuration_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> list[DocumentConfigurationSummary]:
    try:
        configuration = await load_configuration(db, configuration_id)
    except OrderDomainError as error:
        _raise_domain_error(error)
    rows = (
        await db.scalars(
            select(DocumentConfiguration)
            .where(
                DocumentConfiguration.business_profile_id == configuration.business_profile_id,
                DocumentConfiguration.document_type == configuration.document_type,
                DocumentConfiguration.language == configuration.language,
            )
            .options(selectinload(DocumentConfiguration.publication))
            .order_by(DocumentConfiguration.version.desc())
        )
    ).all()
    return [_summary(row) for row in rows]


@router.get("/{configuration_id}/audit", response_model=list[DocumentAuditEventRead])
async def get_configuration_audit(
    configuration_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_TEMPLATES_READ),
) -> list[DocumentAuditEventRead]:
    try:
        configuration = await load_configuration(db, configuration_id)
    except OrderDomainError as error:
        _raise_domain_error(error)
    version_ids = select(DocumentConfiguration.id).where(
        DocumentConfiguration.business_profile_id == configuration.business_profile_id,
        DocumentConfiguration.document_type == configuration.document_type,
        DocumentConfiguration.language == configuration.language,
    )
    rows = (
        await db.scalars(
            select(DocumentAuditEvent)
            .where(
                DocumentAuditEvent.object_type == "document_configuration",
                DocumentAuditEvent.object_id.in_(version_ids),
            )
            .order_by(DocumentAuditEvent.created_at.desc(), DocumentAuditEvent.id.desc())
        )
    ).all()
    return [DocumentAuditEventRead.model_validate(row) for row in rows]
