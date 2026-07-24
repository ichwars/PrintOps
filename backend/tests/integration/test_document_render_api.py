from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

from sqlalchemy import select

from backend.app.api.routes import document_render as render_routes
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact, DocumentSnapshot
from backend.app.models.document_audit import DocumentAuditEvent
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
    audit = await db_session.scalar(
        select(DocumentAuditEvent).where(
            DocumentAuditEvent.action == "export",
            DocumentAuditEvent.object_id == snapshot.document_id,
        )
    )
    assert audit is not None
    assert audit.after == {"artifact_id": artifact.id, "sha256": digest}


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


async def test_resolved_assets_include_inherited_layers_and_specific_overrides(monkeypatch):
    profile_asset = SimpleNamespace(id=1, sha256="a" * 64)
    specific_asset = SimpleNamespace(id=2, sha256="b" * 64)
    layers = {
        10: SimpleNamespace(asset_links=[SimpleNamespace(role="logo", asset=profile_asset)]),
        20: SimpleNamespace(asset_links=[SimpleNamespace(role="logo", asset=specific_asset)]),
    }

    async def load_layer(_db, configuration_id):
        return layers[configuration_id]

    monkeypatch.setattr(render_routes, "get_layout", load_layer)
    monkeypatch.setattr(render_routes, "read_asset", lambda asset: f"asset-{asset.id}".encode())

    assets, roles, receipts = await render_routes._resolved_assets(SimpleNamespace(), (10, 20))

    assert assets == {"a" * 64: b"asset-1", "b" * 64: b"asset-2"}
    assert roles == {"logo": "b" * 64}
    assert receipts == {"logo": {"asset_id": 2, "sha256": "b" * 64}}


async def test_external_render_schema_rejects_einvoice_ambiguity_and_remote_input(
    async_client,
    db_session,
):
    layout, snapshot = await _published_snapshot(db_session)
    ambiguous = await async_client.post(
        BASE_URL,
        json={
            "document_snapshot_id": snapshot.id,
            "published_layout_id": layout.id,
            "zugferd_artifact_id": 1,
            "xrechnung_artifact_id": 2,
            "idempotency_id": "external-render-ambiguous",
        },
    )
    remote = await async_client.post(
        BASE_URL,
        json={
            "document_snapshot_id": snapshot.id,
            "published_layout_id": layout.id,
            "idempotency_id": "external-render-remote",
            "source_url": "http://169.254.169.254/latest/meta-data/",
            "css": "@import url(https://attacker.invalid/layout.css)",
        },
    )

    assert ambiguous.status_code == 422
    assert remote.status_code == 422


async def test_artifact_download_blocks_path_traversal_and_digest_mismatch(
    async_client,
    db_session,
    tmp_path,
    monkeypatch,
):
    _, snapshot = await _published_snapshot(db_session)
    source_document = await db_session.get(CommercialDocument, snapshot.document_id)
    assert source_document is not None
    mismatch_document = CommercialDocument(
        document_type="invoice",
        business_profile_id=source_document.business_profile_id,
        number="RE-INTEGRITY",
        technical_status="issued",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(mismatch_document)
    await db_session.flush()
    outside = tmp_path.parent / "outside-render.pdf"
    outside.write_bytes(b"%PDF-1.7\noutside")
    traversal = DocumentArtifact(
        document_id=snapshot.document_id,
        kind="pdf",
        content_type="application/pdf",
        storage_path="../outside-render.pdf",
        sha256=sha256(outside.read_bytes()).hexdigest(),
        validation_status="valid",
        validation_report={"valid": True},
    )
    stored = tmp_path / "document-render-artifacts" / "tampered.pdf"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"%PDF-1.7\ntampered")
    mismatch = DocumentArtifact(
        document_id=mismatch_document.id,
        kind="pdf",
        content_type="application/pdf",
        storage_path="document-render-artifacts/tampered.pdf",
        sha256="0" * 64,
        validation_status="valid",
        validation_report={"valid": True},
    )
    db_session.add_all([traversal, mismatch])
    await db_session.commit()
    monkeypatch.setattr(render_routes, "resolve_data_dir", lambda: tmp_path)

    escaped = await async_client.get(f"{BASE_URL}/artifacts/{traversal.id}")
    corrupted = await async_client.get(f"{BASE_URL}/artifacts/{mismatch.id}")

    assert escaped.status_code == 424
    assert escaped.json()["detail"]["code"] == "render_artifact_unavailable"
    assert corrupted.status_code == 424
    assert corrupted.json()["detail"]["code"] == "render_artifact_integrity_failed"
