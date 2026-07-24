"""Authenticated document-layout lifecycle, asset and preview API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import NoReturn
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import async_session, get_db
from backend.app.core.permissions import Permission
from backend.app.models import document_layout as orm
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.user import User
from backend.app.schemas import document_layout as dto
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.services.document_layout_assets import (
    AssetError,
    delete_unreferenced_asset,
    link_asset,
    read_asset,
    store_asset,
)
from backend.app.services.document_layout_catalog import (
    PAGE_FORMATS_MM,
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_LANGUAGES,
    TEMPLATE_DESCRIPTIONS,
    TEMPLATE_VERSIONS,
)
from backend.app.services.document_layout_samples import load_sample, sample_catalog
from backend.app.services.document_layouts import (
    LayoutConflictError,
    LayoutNotFoundError,
    LayoutReadinessError,
    LayoutStateError,
    check_readiness,
    clone_layout,
    create_draft,
    get_layout,
    patch_draft,
    publish_layout,
    resolve_effective_layout,
    withdraw_scheduled_layout,
)
from backend.app.services.document_preview_jobs import DocumentPreviewJobService, PreviewJobError
from backend.app.services.document_renderer import DocumentRenderer, DocumentRendererError, RenderInput
from backend.app.services.document_view_model import build_document_view_model

router = APIRouter(prefix="/document-layouts", tags=["document-layouts"])
_preview_jobs = DocumentPreviewJobService()


def _actor_id(actor: User | None) -> int | None:
    return actor.id if actor is not None else None


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    return str(value)[:128] if value else str(uuid4())


def _error(request: Request, status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "area": "document_layouts",
            "message": message,
            "correlation_id": _correlation_id(request),
        },
    )


def _summary(layout: orm.DocumentLayoutConfiguration) -> dto.LayoutSummary:
    return dto.LayoutSummary(
        id=layout.id,
        scope=dto.LayoutScope(
            business_profile_id=layout.business_profile_id,
            document_type=layout.document_type,
            language=layout.language,
        ),
        version=layout.version,
        status=layout.status,
        lock_version=layout.lock_version,
        effective_from=layout.effective_from,
        created_at=layout.created_at,
        updated_at=layout.updated_at,
    )


def _job_response(job: orm.DocumentPreviewJob) -> dto.PreviewJobResponse:
    return dto.PreviewJobResponse(
        public_id=job.public_id,
        status=job.status,
        layout_id=job.configuration_id,
        lock_version=job.layout_lock_version,
        expires_at=job.expires_at,
        result_sha256=job.result_sha256,
    )


async def _layout_or_404(db: AsyncSession, request: Request, layout_id: int):
    try:
        return await get_layout(db, layout_id)
    except LayoutNotFoundError as exc:
        _error(request, 404, "layout_not_found", str(exc))


async def _preview_source(
    db: AsyncSession,
    job: orm.DocumentPreviewJob,
) -> tuple[IssuedDocumentSnapshot, dict | None]:
    if job.source_type == "sample":
        return load_sample(str(job.source_reference)), None
    document_id = int(str(job.source_reference))
    document = await db.scalar(
        select(CommercialDocument)
        .where(CommercialDocument.id == document_id)
        .options(
            selectinload(CommercialDocument.snapshot),
            selectinload(CommercialDocument.artifacts),
        )
    )
    if document is None or document.business_profile_id != job.business_profile_id or document.snapshot is None:
        raise PreviewJobError("PREVIEW_SOURCE_NOT_FOUND")
    einvoice = next(
        (
            artifact
            for artifact in document.artifacts
            if artifact.kind in {"zugferd_xml", "xrechnung_xml"} and artifact.validation_status == "valid"
        ),
        None,
    )
    evidence = None
    if einvoice is not None:
        report = dict(einvoice.validation_report or {})
        pdf = next(
            (
                artifact
                for artifact in document.artifacts
                if artifact.kind == "pdf" and artifact.validation_status == "valid"
            ),
            None,
        )
        evidence = {
            "kind": "zugferd" if einvoice.kind == "zugferd_xml" else "xrechnung",
            "original": "pdf" if einvoice.kind == "zugferd_xml" else "xml",
            "profile": report.get("profile") or report.get("cius_name") or "EN16931",
            "xml_sha256": einvoice.sha256,
            "pdf_artifact_id": pdf.id if pdf is not None else None,
        }
    return IssuedDocumentSnapshot.model_validate_json(document.snapshot.canonical_json), evidence


async def _run_preview(public_id: str) -> None:
    async with async_session() as db:
        job: orm.DocumentPreviewJob | None = None
        job_id: int | None = None
        try:
            job = await _preview_jobs.claim(db, public_id)
            job_id = job.id
            layout = await get_layout(db, job.configuration_id)
            if layout.lock_version != job.layout_lock_version:
                raise PreviewJobError("PREVIEW_LAYOUT_VERSION_CONFLICT")
            snapshot, einvoice_evidence = await _preview_source(db, job)
            resolved = await resolve_effective_layout(
                db,
                business_profile_id=job.business_profile_id,
                document_type=snapshot.document_type,
                language="de" if snapshot.language.lower().startswith("de") else "en",
                draft_layout_id=layout.id if layout.status == "draft" else None,
            )
            assets = {link.asset.sha256: read_asset(link.asset) for link in layout.asset_links}
            roles = {link.role: link.asset.sha256 for link in layout.asset_links}
            rendered = DocumentRenderer().render_preview(
                RenderInput(
                    view_model=build_document_view_model(snapshot),
                    layout=resolved.effective,
                    document_timestamp=datetime.now(UTC),
                    correlation_id=f"preview-{public_id}",
                    cache_scope=f"profile:{job.business_profile_id}:actor:{job.actor_id}",
                    assets=assets,
                    asset_roles=roles,
                )
            )
            await _preview_jobs.complete(
                db,
                job,
                rendered.content,
                findings={
                    "validation_status": rendered.validation_status,
                    "warnings": list(rendered.warnings),
                    **({"einvoice": einvoice_evidence} if einvoice_evidence else {}),
                },
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            if job_id is not None:
                code = exc.code if isinstance(exc, (PreviewJobError, DocumentRendererError)) else "PREVIEW_FAILED"
                await _preview_jobs.fail(db, job_id, code=code)
                await db.commit()


@router.get("/catalog")
async def catalog(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    return {
        "templates": [
            {"key": key, "version": version, "description": TEMPLATE_DESCRIPTIONS[key]}
            for key, version in TEMPLATE_VERSIONS.items()
        ],
        "page_formats_mm": dict(PAGE_FORMATS_MM),
        "languages": list(SUPPORTED_LANGUAGES),
        "document_types": list(SUPPORTED_DOCUMENT_TYPES),
    }


@router.get("/samples")
async def samples(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    return [asdict(item) for item in sample_catalog()]


@router.get("", response_model=list[dto.LayoutSummary])
async def list_layouts(
    business_profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    rows = (
        await db.scalars(
            select(orm.DocumentLayoutConfiguration)
            .where(orm.DocumentLayoutConfiguration.business_profile_id == business_profile_id)
            .order_by(orm.DocumentLayoutConfiguration.scope_key, orm.DocumentLayoutConfiguration.version.desc())
        )
    ).all()
    return [_summary(row) for row in rows]


@router.get("/effective")
async def effective_layout(
    business_profile_id: int,
    document_type: str | None = None,
    language: str | None = None,
    draft_layout_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    resolved = await resolve_effective_layout(
        db,
        business_profile_id=business_profile_id,
        document_type=document_type,
        language=language,
        draft_layout_id=draft_layout_id,
    )
    return {
        "effective": resolved.effective,
        "sourced": resolved.sourced,
        "effective_sha256": resolved.effective_sha256,
        "configuration_ids": resolved.configuration_ids,
    }


@router.post("", response_model=dto.LayoutSummary, status_code=201)
async def create_layout(
    command: dto.CreateLayoutRequest,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    layout = await create_draft(db, command, actor_id=_actor_id(actor))
    await db.commit()
    return _summary(layout)


@router.post("/clone", response_model=dto.LayoutSummary, status_code=201)
async def clone(
    command: dto.CloneLayoutRequest,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    layout = await clone_layout(db, command, actor_id=_actor_id(actor))
    await db.commit()
    return _summary(layout)


@router.get("/{layout_id}")
async def detail(
    layout_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    layout = await _layout_or_404(db, request, layout_id)
    resolved = await resolve_effective_layout(
        db,
        business_profile_id=layout.business_profile_id,
        document_type=layout.document_type,
        language=layout.language,
        draft_layout_id=layout.id if layout.status == "draft" else None,
    )
    return {
        "summary": _summary(layout),
        "effective": resolved.effective,
        "sourced": resolved.sourced,
        "validation_status": layout.validation_status,
        "validation_report": layout.validation_report,
        "assets": [dto.LayoutAssetMetadata.model_validate(link.asset) for link in layout.asset_links],
    }


@router.patch("/{layout_id}", response_model=dto.LayoutSummary)
async def patch_layout(
    layout_id: int,
    command: dto.PatchLayoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    try:
        layout = await patch_draft(db, layout_id, command, actor_id=_actor_id(actor))
        await db.commit()
        return _summary(layout)
    except LayoutConflictError as exc:
        await db.rollback()
        _error(request, 409, "layout_version_conflict", str(exc))
    except LayoutStateError as exc:
        await db.rollback()
        _error(request, 409, "layout_state_conflict", str(exc))


@router.get("/{layout_id}/readiness", response_model=dto.LayoutReadinessReport)
async def readiness(
    layout_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    layout = await _layout_or_404(db, request, layout_id)
    return await check_readiness(
        db,
        business_profile_id=layout.business_profile_id,
        document_type=layout.document_type,
        language=layout.language,
        draft_layout_id=layout.id if layout.status == "draft" else None,
    )


@router.post("/{layout_id}/publish", response_model=dto.LayoutSummary)
async def publish(
    layout_id: int,
    command: dto.PublishLayoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    try:
        layout = await publish_layout(db, layout_id, command, actor_id=_actor_id(actor))
        await db.commit()
        return _summary(layout)
    except LayoutReadinessError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "layout_not_ready",
                "findings": exc.report.model_dump(mode="json"),
                "correlation_id": _correlation_id(request),
            },
        ) from None
    except (LayoutConflictError, LayoutStateError) as exc:
        await db.rollback()
        _error(request, 409, "layout_publish_conflict", str(exc))


@router.post("/{layout_id}/withdraw", response_model=dto.LayoutSummary)
async def withdraw(
    layout_id: int,
    command: dto.WithdrawLayoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    try:
        layout = await withdraw_scheduled_layout(db, layout_id, command, actor_id=_actor_id(actor))
        await db.commit()
        return _summary(layout)
    except LayoutStateError as exc:
        await db.rollback()
        _error(request, 409, "layout_withdraw_conflict", str(exc))


@router.get("/{layout_id}/audit", response_model=list[dto.LayoutAuditReceiptSchema])
async def audit(
    layout_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_AUDIT_READ),
):
    layout = await _layout_or_404(db, request, layout_id)
    return [
        dto.LayoutAuditReceiptSchema(
            id=item.id,
            layout_id=item.configuration_id,
            event_type=item.event_type,
            edit_session_id=item.edit_session_id,
            reason=item.reason,
            changed_field_paths=tuple(item.changed_field_paths or []),
            actor_id=item.actor_id,
            first_seen_at=item.first_seen_at,
            last_seen_at=item.last_seen_at,
        )
        for item in layout.audit_receipts
    ]


@router.post("/assets", response_model=dto.LayoutAssetMetadata, status_code=201)
async def upload_asset(
    request: Request,
    business_profile_id: int = Form(...),
    asset_type: str = Form(...),
    declared_sha256: str = Form(...),
    font_embedding_rights_confirmed: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={"code": "asset_too_large"})
    command = dto.AssetUploadRequest(
        business_profile_id=business_profile_id,
        asset_type=asset_type,
        original_name=file.filename or "asset",
        declared_mime_type=file.content_type or "application/octet-stream",
        declared_sha256=declared_sha256,
        font_embedding_rights_confirmed=font_embedding_rights_confirmed,
    )
    try:
        asset = await store_asset(db, command, content, actor_id=_actor_id(actor))
    except AssetError as exc:
        await db.rollback()
        _error(request, 422, "asset_invalid", str(exc))
    await db.commit()
    return dto.LayoutAssetMetadata.model_validate(asset)


@router.post("/{layout_id}/assets")
async def attach_asset(
    layout_id: int,
    command: dto.AssetLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    try:
        link = await link_asset(db, layout_id, command)
    except AssetError as exc:
        await db.rollback()
        _error(request, 422, "asset_link_invalid", str(exc))
    await db.commit()
    return {"layout_id": layout_id, "asset_id": link.asset_id, "role": link.role}


@router.get("/assets/{asset_id}")
async def download_asset(
    asset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    asset = await db.get(orm.DocumentLayoutAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail={"code": "asset_not_found"})
    try:
        content = read_asset(asset)
    except AssetError as exc:
        _error(request, 424, "asset_unavailable", str(exc))
    return Response(
        content,
        media_type=asset.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="asset-{asset.id}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_MANAGE),
):
    try:
        await delete_unreferenced_asset(db, asset_id)
    except AssetError as exc:
        await db.rollback()
        _error(request, 409, "asset_delete_conflict", str(exc))
    await db.commit()
    return Response(status_code=204)


@router.post("/preview", response_model=dto.PreviewJobResponse)
async def enqueue_preview(
    command: dto.PreviewRequest,
    background: BackgroundTasks,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    layout = await _layout_or_404(db, request, command.layout_id)
    if layout.lock_version != command.layout_lock_version:
        _error(request, 409, "layout_version_conflict", "The requested layout version is stale")
    if command.source_kind == "sample":
        try:
            load_sample(command.source_id)
        except KeyError:
            _error(request, 404, "preview_source_not_found", "The sample was not found")
    else:
        document = await db.get(CommercialDocument, int(command.source_id))
        if document is None or document.business_profile_id != layout.business_profile_id:
            _error(request, 404, "preview_source_not_found", "The document was not found")
    job, cache_hit = await _preview_jobs.enqueue(
        db,
        actor_id=_actor_id(actor),
        business_profile_id=layout.business_profile_id,
        configuration_id=layout.id,
        layout_lock_version=command.layout_lock_version,
        source_type=command.source_kind,
        source_reference=command.source_id,
    )
    await db.commit()
    response.status_code = 200 if cache_hit else 202
    if not cache_hit:
        background.add_task(_run_preview, job.public_id)
    return _job_response(job)


async def _owned_job(db: AsyncSession, public_id: str, actor: User | None):
    job = await db.scalar(select(orm.DocumentPreviewJob).where(orm.DocumentPreviewJob.public_id == public_id))
    if job is None or job.actor_id != _actor_id(actor):
        raise HTTPException(status_code=404, detail={"code": "preview_not_found"})
    return job


@router.get("/preview/{public_id}", response_model=dto.PreviewJobResponse)
async def preview_status(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    return _job_response(await _owned_job(db, public_id, actor))


@router.get("/preview/{public_id}/pdf")
async def preview_pdf(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    job = await _owned_job(db, public_id, actor)
    try:
        content = _preview_jobs.read_result(job)
    except PreviewJobError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code}) from None
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "ETag": f'"{sha256(content).hexdigest()}"',
        },
    )


@router.get("/preview/{public_id}/report")
async def preview_report(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    job = await _owned_job(db, public_id, actor)
    return {"status": job.status, "findings": dict(job.findings or {})}
