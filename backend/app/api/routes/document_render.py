"""Narrow external render/export API for immutable commercial-document evidence."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.paths import resolve_data_dir, safe_join
from backend.app.core.permissions import Permission
from backend.app.models.commercial_document import (
    CommercialDocument,
    DocumentArtifact,
    DocumentSnapshot,
)
from backend.app.models.user import User
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.schemas.document_layout import ExternalRenderRequest, ExternalRenderResponse
from backend.app.services.document_audit import append_audit
from backend.app.services.document_layout_assets import read_asset
from backend.app.services.document_layout_catalog import RENDERER_VERSION, VALIDATOR_VERSION
from backend.app.services.document_layouts import LayoutNotFoundError, get_layout, resolve_effective_layout
from backend.app.services.document_readiness import probe_document_runtime
from backend.app.services.document_renderer import (
    DocumentRenderer,
    DocumentRendererError,
    RenderInput,
    XrechnungArtifactReference,
    ZugferdArtifactReference,
)
from backend.app.services.document_view_model import build_document_view_model
from backend.app.services.einvoice.artifacts import EInvoiceArtifactError, load_validated_artifact

router = APIRouter(prefix="/document-render", tags=["document-render"])


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    return str(value)[:128] if value else str(uuid4())


def _actor_id(actor: User | None) -> int | None:
    return actor.id if actor is not None else None


def _error(request: Request, status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "area": "document_render",
            "message": message,
            "correlation_id": _correlation_id(request),
        },
    )


async def _snapshot(db: AsyncSession, snapshot_id: int) -> DocumentSnapshot | None:
    return await db.scalar(
        select(DocumentSnapshot)
        .where(DocumentSnapshot.id == snapshot_id)
        .options(
            selectinload(DocumentSnapshot.document).selectinload(CommercialDocument.artifacts),
        )
    )


def _artifact_storage_path(path: Path) -> str:
    root = resolve_data_dir().resolve()
    target = path.resolve()
    if root != target and root not in target.parents:
        raise DocumentRendererError("RENDER_ARTIFACT_STORAGE_INVALID")
    return target.relative_to(root).as_posix()


def _response(artifact: DocumentArtifact, correlation_id: str) -> ExternalRenderResponse:
    return ExternalRenderResponse(
        artifact_id=artifact.id,
        sha256=artifact.sha256,
        validation_status=artifact.validation_status,
        content_type=artifact.content_type,
        correlation_id=correlation_id,
    )


async def _resolved_assets(
    db: AsyncSession,
    configuration_ids: tuple[int, ...],
) -> tuple[dict[str, bytes], dict[str, str], dict[str, dict[str, int | str]]]:
    assets: dict[str, bytes] = {}
    roles: dict[str, str] = {}
    receipts: dict[str, dict[str, int | str]] = {}
    for configuration_id in configuration_ids:
        layer = await get_layout(db, configuration_id)
        for link in layer.asset_links:
            assets[link.asset.sha256] = read_asset(link.asset)
            roles[link.role] = link.asset.sha256
            receipts[link.role] = {"asset_id": link.asset.id, "sha256": link.asset.sha256}
    return assets, roles, receipts


@router.get("/readiness")
async def runtime_readiness(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DOCUMENT_LAYOUTS_READ),
):
    status = probe_document_runtime(renderer_cli=settings.weasyprint_cli)
    return {
        "ready": status.ready,
        "renderer": status.renderer.model_dump(mode="json"),
        "pango": status.pango.model_dump(mode="json"),
        "icc_profile_sha256": status.icc_profile_sha256,
        "icc_profile_valid": status.icc_profile_valid,
        "validator": status.validator.model_dump(mode="json"),
        "findings": list(status.findings),
    }


@router.post("", response_model=ExternalRenderResponse)
async def render_document(
    command: ExternalRenderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_EXPORT),
):
    correlation_id = _correlation_id(request)
    runtime = probe_document_runtime(renderer_cli=settings.weasyprint_cli)
    if not runtime.ready:
        _error(request, 424, "pdf_runtime_unavailable", "The pinned PDF runtime is unavailable")
    snapshot_row = await _snapshot(db, command.document_snapshot_id)
    if snapshot_row is None:
        _error(request, 404, "document_snapshot_not_found", "The immutable document snapshot was not found")
    document = snapshot_row.document
    previous = next(
        (
            item
            for item in document.artifacts
            if item.kind == "pdf" and (item.render_receipt or {}).get("idempotency_id") == command.idempotency_id
        ),
        None,
    )
    if previous is not None:
        return _response(previous, correlation_id)
    if any(item.kind == "pdf" for item in document.artifacts):
        _error(
            request,
            409,
            "pdf_artifact_exists",
            "This immutable document already has a final PDF artifact",
        )

    snapshot = IssuedDocumentSnapshot.model_validate_json(snapshot_row.canonical_json)
    language = "de" if snapshot.language.lower().startswith("de") else "en"
    resolved = await resolve_effective_layout(
        db,
        business_profile_id=document.business_profile_id,
        document_type=snapshot.document_type,
        language=language,
    )
    if not resolved.configuration_ids:
        _error(request, 424, "published_layout_missing", "No published profile layout is available")
    layout_id = command.published_layout_id or resolved.configuration_ids[-1]
    try:
        layout = await get_layout(db, layout_id)
    except LayoutNotFoundError:
        _error(request, 404, "published_layout_not_found", "The requested published layout was not found")
    if (
        layout.business_profile_id != document.business_profile_id
        or layout.id not in resolved.configuration_ids
        or layout.status != "active"
        or layout.publication is None
    ):
        _error(request, 422, "published_layout_invalid", "The requested layout is not published for this snapshot")

    reference = None
    resolved_einvoice = None
    artifact_id = command.zugferd_artifact_id or command.xrechnung_artifact_id
    if artifact_id is not None:
        try:
            resolved_einvoice = await load_validated_artifact(
                db,
                artifact_id,
                expected_document_id=document.id,
                expected_snapshot_sha256=snapshot_row.sha256,
                actor_id=actor.id if actor is not None else None,
                correlation_id=correlation_id,
            )
        except EInvoiceArtifactError as exc:
            _error(request, 422, exc.code, "The electronic-invoice evidence is invalid")
        reference = (
            ZugferdArtifactReference(zugferd_artifact_id=artifact_id)
            if command.zugferd_artifact_id is not None
            else XrechnungArtifactReference(xrechnung_artifact_id=artifact_id)
        )

    assets, roles, asset_receipts = await _resolved_assets(db, resolved.configuration_ids)
    renderer = DocumentRenderer(
        einvoice_artifact_resolver=(
            (lambda _reference, _render_input: resolved_einvoice) if resolved_einvoice is not None else None
        )
    )
    document_timestamp = snapshot_row.issued_at
    if document_timestamp.tzinfo is None:
        document_timestamp = document_timestamp.replace(tzinfo=UTC)
    try:
        rendered = renderer.render_final(
            RenderInput(
                view_model=build_document_view_model(snapshot),
                layout=resolved.effective,
                document_timestamp=document_timestamp,
                correlation_id=correlation_id,
                cache_scope=f"profile:{document.business_profile_id}:document:{document.id}",
                assets=assets,
                asset_roles=roles,
                source_document_id=document.id,
                source_snapshot_sha256=snapshot_row.sha256,
            ),
            reference,
        )
    except DocumentRendererError as exc:
        if exc.code == "RENDER_TIMEOUT":
            _error(request, 504, exc.code, "PDF rendering timed out")
        if exc.code in {"RENDER_PAGE_LIMIT", "RENDER_MEMORY_LIMIT"}:
            _error(request, 413, exc.code, "The render limits were exceeded")
        if exc.code in {"RENDER_INPUT_INVALID", "EINVOICE_ARTIFACT_NOT_VALID"} or exc.code.startswith(
            ("ZUGFERD_", "XRECHNUNG_", "EINVOICE_")
        ):
            _error(request, 422, exc.code, "The render evidence is invalid")
        _error(request, 424, exc.code, "A required render component failed")
    if rendered.artifact_path is None:
        _error(request, 424, "render_artifact_storage_invalid", "The final artifact was not persisted")

    artifact = DocumentArtifact(
        document_id=document.id,
        kind="pdf",
        content_type="application/pdf",
        storage_path=_artifact_storage_path(rendered.artifact_path),
        content=None,
        sha256=rendered.sha256,
        validation_status=rendered.validation_status,
        validation_report=(
            rendered.validation_report.model_dump(mode="json") if rendered.validation_report is not None else {}
        ),
        rule_versions={"pdfa": "3u"},
        layout_configuration_id=layout.id,
        layout_version=layout.version,
        layout_effective_sha256=resolved.effective_sha256,
        asset_receipts=asset_receipts,
        renderer_version=RENDERER_VERSION,
        validator_version=VALIDATOR_VERSION,
        render_receipt={
            **dict(rendered.render_receipt),
            "idempotency_id": command.idempotency_id,
            "document_snapshot_id": snapshot_row.id,
            "document_snapshot_sha256": snapshot_row.sha256,
            "export_manifest": dict(rendered.export_manifest),
        },
    )
    db.add(artifact)
    await db.flush()
    await db.commit()
    return _response(artifact, correlation_id)


@router.get("/artifacts/{artifact_id}")
async def download_artifact(
    artifact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_EXPORT),
):
    artifact = await db.get(DocumentArtifact, artifact_id)
    if artifact is None or artifact.kind != "pdf" or artifact.validation_status != "valid":
        raise HTTPException(status_code=404, detail={"code": "render_artifact_not_found"})
    if not artifact.storage_path:
        raise HTTPException(status_code=424, detail={"code": "render_artifact_storage_invalid"})
    try:
        content = safe_join(resolve_data_dir(), artifact.storage_path).read_bytes()
    except (OSError, ValueError):
        raise HTTPException(status_code=424, detail={"code": "render_artifact_unavailable"}) from None
    if artifact.sha256 != __import__("hashlib").sha256(content).hexdigest():
        raise HTTPException(status_code=424, detail={"code": "render_artifact_integrity_failed"})
    await append_audit(
        db,
        action="export",
        object_type="commercial_document",
        object_id=artifact.document_id,
        actor_id=_actor_id(actor),
        reason="Immutable document artifact downloaded through render API",
        before=None,
        after={"artifact_id": artifact.id, "sha256": artifact.sha256},
        correlation_id=_correlation_id(request),
    )
    await db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="document-{artifact.document_id}.pdf"',
            "ETag": f'"{artifact.sha256}"',
            "Cache-Control": "private, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
