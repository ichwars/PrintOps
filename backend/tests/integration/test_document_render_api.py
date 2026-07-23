from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

from sqlalchemy import select

from backend.app.api.routes import document_render as render_routes
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact, DocumentSnapshot
from backend.app.schemas.document_layout import CreateLayoutRequest, LayoutScope, PublishLayoutRequest
from backend.app.services.document_layout_samples import load_sample
from backend.app.services.document_layouts import create_draft, publish_layout
from backend.app.services.document_renderer import RenderedPdf
from backend.app.services.document_snapshot import canonicalize_snapshot, snapshot_sha256
from backend.app.services.verapdf import PdfaValidationReport

BASE_URL = "/api/v1/document-render"


async def _published_snapshot(db_session):
    profile = BusinessProfile(
        name="Render API",
        legal_name="Render API GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.flush()
    layout = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id),
            template_key="classic",
            reason="External render profile default",
        ),
        actor_id=None,
    )
    layout = await publish_layout(
        db_session,
        layout.id,
        PublishLayoutRequest(
            expected_lock_version=layout.lock_version,
            reason="Release for immutable external rendering",
        ),
        actor_id=None,
    )
    sample = load_sample("invoice-de-standard")
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number=sample.number,
        technical_status="issued",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    snapshot = DocumentSnapshot(
        document_id=document.id,
        canonical_json=canonicalize_snapshot(sample).decode("utf-8"),
        sha256=snapshot_sha256(sample),
        configuration_id=None,
        configuration_version=1,
        tax_rule_version="2026.1",
        einvoice_rule_versions={},
        issued_by_id=None,
        issued_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.commit()
    return layout, snapshot


async def test_external_render_is_snapshot_only_idempotent_and_downloadable(
    async_client,
    db_session,
    tmp_path,
    monkeypatch,
):
    layout, snapshot = await _published_snapshot(db_session)
    content = b"%PDF-1.7\nimmutable-render"
    digest = sha256(content).hexdigest()
    artifact_path = tmp_path / "document-render-artifacts" / digest[:2] / f"{digest}.pdf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(content)

    class FakeRenderer:
        def __init__(self, **_kwargs):
            pass

        def render_final(self, render_input, reference):
            assert render_input.source_snapshot_sha256 == snapshot.sha256
            assert reference is None
            return RenderedPdf(
                content=content,
                sha256=digest,
                page_count=1,
                page_format="A4",
                mode="final",
                from_cache=False,
                duration_ms=1,
                artifact_path=artifact_path,
                validation_status="valid",
                validation_report=PdfaValidationReport(
                    compliant=True,
                    validator_version="1.30.2",
                    ruleset="PDF/A-3U",
                    findings=[],
                    raw_report_sha256="a" * 64,
                ),
                render_receipt={"pdf_sha256": digest},
            )

    monkeypatch.setattr(render_routes, "resolve_data_dir", lambda: tmp_path)
    monkeypatch.setattr(render_routes, "DocumentRenderer", FakeRenderer)
    monkeypatch.setattr(
        render_routes,
        "probe_document_runtime",
        lambda **_kwargs: SimpleNamespace(ready=True),
    )
    payload = {
        "document_snapshot_id": snapshot.id,
        "published_layout_id": layout.id,
        "idempotency_id": "external-render-0001",
    }

    first = await async_client.post(BASE_URL, json=payload)
    second = await async_client.post(BASE_URL, json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["artifact_id"] == first.json()["artifact_id"]
    artifact = await db_session.scalar(
        select(DocumentArtifact).where(DocumentArtifact.id == first.json()["artifact_id"])
    )
    assert artifact is not None
    assert artifact.layout_configuration_id == layout.id
    assert artifact.render_receipt["document_snapshot_sha256"] == snapshot.sha256

    download = await async_client.get(f"{BASE_URL}/artifacts/{artifact.id}")
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["etag"] == f'"{digest}"'
    assert download.headers["x-content-type-options"] == "nosniff"


async def test_external_render_rejects_mutable_or_guessed_inputs(async_client, db_session):
    layout, snapshot = await _published_snapshot(db_session)
    missing = await async_client.post(
        BASE_URL,
        json={
            "document_snapshot_id": 999999,
            "published_layout_id": layout.id,
            "idempotency_id": "external-render-0002",
        },
    )
    forbidden_shape = await async_client.post(
        BASE_URL,
        json={
            "document_snapshot_id": snapshot.id,
            "published_layout_id": layout.id,
            "idempotency_id": "external-render-0003",
            "html": "<h1>unsafe</h1>",
        },
    )

    assert missing.status_code in {404, 424}
    assert forbidden_shape.status_code == 422
