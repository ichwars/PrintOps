from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from hashlib import sha256
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.paths import resolve_data_dir
from backend.app.models.commercial_document import (
    CommercialDocument,
    DocumentArtifact,
    DocumentSnapshot,
    ImmutableDocumentError,
)
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot


class IssuedPdfError(RuntimeError):
    """Stable issuance failure raised before a PDF may become evidence."""

    def __init__(self, code: str):
        self.code = code
        self.failure_code = code.lower()
        super().__init__(code)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        raise TypeError("Binary float values are forbidden in document snapshots")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def canonicalize_snapshot(snapshot: IssuedDocumentSnapshot) -> bytes:
    return canonicalize_payload(snapshot)


def canonicalize_payload(payload: Any) -> bytes:
    """Return stable UTF-8 JSON for an allowed document-domain payload."""
    return json.dumps(
        _canonical_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def snapshot_sha256(snapshot: IssuedDocumentSnapshot) -> str:
    return sha256(canonicalize_snapshot(snapshot)).hexdigest()


async def attach_issued_snapshot(
    session: AsyncSession,
    document: CommercialDocument,
    snapshot: IssuedDocumentSnapshot,
    *,
    configuration_id: int | None,
    configuration_version: int,
    tax_rule_version: str,
    einvoice_rule_versions: dict[str, str],
    actor_id: int | None,
) -> DocumentSnapshot:
    if document.technical_status != "issued":
        raise ValueError("A snapshot can only be attached to an issued document")
    existing = await session.scalar(
        select(DocumentSnapshot.id).where(DocumentSnapshot.document_id == document.id)
    )
    if existing is not None:
        raise ImmutableDocumentError("The issued document already has a snapshot")

    canonical = canonicalize_snapshot(snapshot)
    evidence = DocumentSnapshot(
        document_id=document.id,
        canonical_json=canonical.decode("utf-8"),
        sha256=sha256(canonical).hexdigest(),
        configuration_id=configuration_id,
        configuration_version=configuration_version,
        tax_rule_version=tax_rule_version,
        einvoice_rule_versions=dict(einvoice_rule_versions),
        issued_by_id=actor_id,
        issued_at=datetime.now(UTC),
    )
    session.add(evidence)
    return evidence


async def replace_issued_snapshot(
    session: AsyncSession,
    document_id: int,
    snapshot: IssuedDocumentSnapshot,
) -> DocumentSnapshot:
    del session, document_id, snapshot
    raise ImmutableDocumentError("Issued document snapshots cannot be replaced")


def _relative_artifact_path(path) -> str:
    root = resolve_data_dir().resolve()
    target = path.resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as exc:
        raise IssuedPdfError("PDF_ARTIFACT_STORAGE_INVALID") from exc


async def render_issued_pdf(
    session: AsyncSession,
    document: CommercialDocument,
    evidence: DocumentSnapshot,
    snapshot: IssuedDocumentSnapshot,
    *,
    actor_id: int | None,
    idempotency_key: str,
    correlation_id: str,
    einvoice_artifact: DocumentArtifact | None = None,
) -> DocumentArtifact:
    """Resolve, render and stage exactly one immutable final PDF artifact."""
    from backend.app.schemas.document_layout import EffectiveDocumentLayout
    from backend.app.services.document_audit import append_audit
    from backend.app.services.document_layout_assets import AssetError, read_asset
    from backend.app.services.document_layout_catalog import RENDERER_VERSION, VALIDATOR_VERSION
    from backend.app.services.document_layouts import get_layout, resolve_effective_layout
    from backend.app.services.document_renderer import (
        DocumentRenderer,
        DocumentRendererError,
        RenderInput,
        ZugferdArtifactReference,
    )
    from backend.app.services.document_view_model import build_document_view_model
    from backend.app.services.einvoice.artifacts import materialize_validated_artifact

    existing = await session.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.document_id == document.id,
            DocumentArtifact.kind == "pdf",
        )
    )
    if existing is not None:
        if (existing.render_receipt or {}).get("idempotency_id") == idempotency_key:
            return existing
        raise ImmutableDocumentError("The issued document already has a final PDF")
    if document.issue_date is None or evidence.id is None:
        raise IssuedPdfError("PDF_SOURCE_EVIDENCE_INCOMPLETE")

    language = "de" if snapshot.language.lower().startswith("de") else "en"
    resolved = await resolve_effective_layout(
        session,
        business_profile_id=document.business_profile_id,
        document_type=snapshot.document_type,
        language=language,
        now=datetime.combine(document.issue_date, time.max, tzinfo=UTC),
    )
    if not resolved.configuration_ids:
        raise IssuedPdfError("PUBLISHED_LAYOUT_MISSING")

    layouts = [await get_layout(session, item) for item in resolved.configuration_ids]
    if not any(item.document_type is None and item.language is None for item in layouts):
        raise IssuedPdfError("PUBLISHED_LAYOUT_MISSING")
    selected_layout = layouts[-1]
    assets: dict[str, bytes] = {}
    asset_roles: dict[str, str] = {}
    asset_receipts: dict[str, dict] = {}
    try:
        for layout in layouts:
            for link in layout.asset_links:
                assets[link.asset.sha256] = read_asset(link.asset)
                asset_roles[link.role] = link.asset.sha256
                asset_receipts[link.role] = {
                    "asset_id": link.asset.id,
                    "sha256": link.asset.sha256,
                }
    except (AssetError, OSError) as exc:
        raise IssuedPdfError("LAYOUT_ASSET_INVALID") from exc

    reference = None
    resolved_einvoice = None
    if einvoice_artifact is not None and einvoice_artifact.kind == "zugferd_xml":
        resolved_einvoice = materialize_validated_artifact(
            einvoice_artifact,
            expected_document_id=document.id,
            expected_snapshot_sha256=evidence.sha256,
        )
        reference = ZugferdArtifactReference(zugferd_artifact_id=einvoice_artifact.id)

    renderer = DocumentRenderer(
        einvoice_artifact_resolver=(
            (lambda _reference, _render_input: resolved_einvoice)
            if resolved_einvoice is not None
            else None
        )
    )
    try:
        rendered = renderer.render_final(
            RenderInput(
                view_model=build_document_view_model(snapshot),
                layout=EffectiveDocumentLayout.model_validate(resolved.effective),
                document_timestamp=evidence.issued_at,
                correlation_id=correlation_id,
                cache_scope=f"profile:{document.business_profile_id}:document:{document.id}",
                assets=assets,
                asset_roles=asset_roles,
                source_document_id=document.id,
                source_snapshot_sha256=evidence.sha256,
            ),
            reference,
        )
    except DocumentRendererError as exc:
        raise IssuedPdfError(exc.code) from None
    try:
        persisted_content = (
            rendered.artifact_path.read_bytes()
            if rendered.artifact_path is not None
            else b""
        )
    except OSError as exc:
        raise IssuedPdfError("PDF_ARTIFACT_STORAGE_INVALID") from exc
    if (
        rendered.artifact_path is None
        or rendered.validation_status != "valid"
        or sha256(rendered.content).hexdigest() != rendered.sha256
        or sha256(persisted_content).hexdigest() != rendered.sha256
    ):
        raise IssuedPdfError("PDF_VALIDATION_FAILED")

    original_role = (
        "visual_copy"
        if einvoice_artifact is not None and einvoice_artifact.kind == "xrechnung_xml"
        else "original"
    )
    export_manifest = dict(rendered.export_manifest)
    export_manifest.update(
        {
            "original_role": original_role,
            "pdf_sha256": rendered.sha256,
            "document_snapshot_sha256": evidence.sha256,
        }
    )
    if einvoice_artifact is not None:
        export_manifest.update(
            {
                "einvoice_artifact_id": einvoice_artifact.id,
                "einvoice_kind": einvoice_artifact.kind,
                "xml_sha256": einvoice_artifact.sha256,
            }
        )
    artifact = DocumentArtifact(
        document_id=document.id,
        kind="pdf",
        content_type="application/pdf",
        storage_path=_relative_artifact_path(rendered.artifact_path),
        content=None,
        sha256=rendered.sha256,
        validation_status="valid",
        validation_report=(
            rendered.validation_report.model_dump(mode="json")
            if rendered.validation_report is not None
            else {}
        ),
        rule_versions={"pdfa": "3u"},
        layout_configuration_id=selected_layout.id,
        layout_version=selected_layout.version,
        layout_effective_sha256=resolved.effective_sha256,
        asset_receipts=asset_receipts,
        renderer_version=RENDERER_VERSION,
        validator_version=VALIDATOR_VERSION,
        render_receipt={
            **dict(rendered.render_receipt),
            "idempotency_id": idempotency_key,
            "document_snapshot_id": evidence.id,
            "document_snapshot_sha256": evidence.sha256,
            "original_role": original_role,
            "export_manifest": export_manifest,
        },
    )
    session.add(artifact)
    await append_audit(
        session,
        action="render_success",
        object_type="commercial_document",
        object_id=document.id,
        actor_id=actor_id,
        reason=None,
        before=None,
        after={
            "sha256": rendered.sha256,
            "layout_id": selected_layout.id,
            "layout_version": selected_layout.version,
            "layout_effective_sha256": resolved.effective_sha256,
        },
        correlation_id=correlation_id,
    )
    return artifact
