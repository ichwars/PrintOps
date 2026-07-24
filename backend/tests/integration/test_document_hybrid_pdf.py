from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pikepdf
import pytest
from sqlalchemy import select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import load_sample
from backend.app.services.document_renderer import (
    DocumentRenderer,
    RenderInput,
    XrechnungArtifactReference,
    ZugferdArtifactReference,
)
from backend.app.services.document_snapshot import snapshot_sha256
from backend.app.services.document_view_model import build_document_view_model
from backend.app.services.einvoice.artifacts import (
    EInvoiceArtifactError,
    load_validated_artifact,
    materialize_validated_artifact,
    store_artifact,
)
from backend.app.services.einvoice.canonical import from_snapshot
from backend.app.services.einvoice.validator import validate_xml
from backend.app.services.einvoice.xrechnung import render_xrechnung
from backend.app.services.einvoice.zugferd import render_zugferd
from backend.app.services.verapdf import VeraPdfRunner

ROOT = Path(__file__).parents[2]
WEASYPRINT = (
    ROOT.parent / "installers" / "windows" / "build" / "staging" / "runtime" / "weasyprint" / "dist" / "weasyprint.exe"
)
VERAPDF = ROOT.parent / "installers" / "windows" / "build" / "staging" / "runtime" / "verapdf" / "verapdf.bat"


async def _document(db_session, name: str) -> CommercialDocument:
    profile = BusinessProfile(
        name=name,
        legal_name=f"{name} GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.flush()
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0042",
        technical_status="issued",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    return document


def _einvoice_snapshot():
    snapshot = load_sample("invoice-de-standard")
    return snapshot.model_copy(
        update={
            "seller": {
                **snapshot.seller,
                "contact": {
                    "name": "Buchhaltung",
                    "email": "rechnung@example.invalid",
                    "phone": "+49 341 123456",
                },
                "electronic_address": "rechnung@example.invalid",
                "electronic_address_scheme": "EM",
            },
            "buyer": {
                **snapshot.buyer,
                "buyer_reference": "04011000-12345-34",
                "electronic_address": "einkauf@example.invalid",
                "electronic_address_scheme": "EM",
            },
            "payment": {
                **snapshot.payment,
                "means_code": "58",
                "terms": "Zahlbar binnen 14 Tagen.",
                "account_name": snapshot.payment["account_holder"],
            },
            "lines": (snapshot.lines[0],),
            "totals": {
                "line_net": Decimal("98.00"),
                "tax": Decimal("18.62"),
                "gross": Decimal("116.62"),
                "prepaid": Decimal("0.00"),
                "payable": Decimal("116.62"),
            },
            "references": (),
        }
    )


def _input(document_id: int, digest: str) -> RenderInput:
    snapshot = _einvoice_snapshot()
    return RenderInput(
        view_model=build_document_view_model(snapshot),
        layout=TEMPLATE_DEFAULTS["classic"],
        document_timestamp=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        correlation_id=f"hybrid-{document_id}",
        cache_scope="profile:1",
        source_document_id=document_id,
        source_snapshot_sha256=digest,
    )


@pytest.mark.asyncio
@pytest.mark.requires_verapdf
async def test_validated_zugferd_xml_is_embedded_byte_exact_and_revalidated(
    db_session,
    tmp_path,
    monkeypatch,
):
    if not WEASYPRINT.exists() or not VERAPDF.exists():
        pytest.skip("pinned PDF runtimes are not staged")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    snapshot = _einvoice_snapshot()
    digest = snapshot_sha256(snapshot)
    document = await _document(db_session, "Hybrid")
    xml = render_zugferd(from_snapshot(snapshot), "en16931")
    xml_report = validate_xml(xml, "zugferd", "cii-d22b", "en16931")
    artifact = await store_artifact(
        db_session,
        document,
        xml,
        xml_report,
        snapshot_sha256=digest,
    )
    await db_session.flush()
    resolved = materialize_validated_artifact(
        artifact,
        expected_document_id=document.id,
        expected_snapshot_sha256=digest,
    )
    renderer = DocumentRenderer(
        engine_cli=WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "pdfs",
        validator=VeraPdfRunner(cli_path=VERAPDF, report_dir=tmp_path / "reports"),
        einvoice_artifact_resolver=lambda _reference, _request: resolved,
    )

    rendered = renderer.render_final(
        _input(document.id, digest),
        ZugferdArtifactReference(zugferd_artifact_id=artifact.id),
    )

    assert rendered.validation_status == "valid"
    assert rendered.render_receipt["einvoice"]["xml_sha256"] == sha256(xml).hexdigest()
    assert rendered.export_manifest["legal_original"] == "pdf"
    with pikepdf.open(io.BytesIO(rendered.content)) as pdf:
        specification = pdf.attachments["factur-x.xml"]
        assert str(specification.relationship) == "/Alternative"
        assert specification.get_file().mime_type == "text/xml"
        assert specification.get_file().read_bytes() == xml
        assert len(pdf.Root.AF) == 1
        xmp = bytes(pdf.Root.Metadata)
        assert b"urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#" in xmp
        assert b"<fx:ConformanceLevel>EN16931</fx:ConformanceLevel>" in xmp
        assert b"<fx:DocumentFileName>factur-x.xml</fx:DocumentFileName>" in xmp


@pytest.mark.asyncio
async def test_xrechnung_remains_xml_original_and_pdf_has_no_zugferd_claim(
    db_session,
    tmp_path,
    monkeypatch,
):
    if not WEASYPRINT.exists():
        pytest.skip("pinned WeasyPrint runtime is not staged")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    snapshot = _einvoice_snapshot()
    digest = snapshot_sha256(snapshot)
    document = await _document(db_session, "XRechnung")
    xml = render_xrechnung(from_snapshot(snapshot), "ubl")
    report = validate_xml(xml, "xrechnung", "ubl-2.1", "xrechnung")
    artifact = await store_artifact(
        db_session,
        document,
        xml,
        report,
        snapshot_sha256=digest,
    )
    await db_session.flush()
    resolved = materialize_validated_artifact(
        artifact,
        expected_document_id=document.id,
        expected_snapshot_sha256=digest,
    )
    renderer = DocumentRenderer(
        engine_cli=WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "pdfs",
        validator=False,
        einvoice_artifact_resolver=lambda _reference, _request: resolved,
    )

    rendered = renderer.render_final(
        _input(document.id, digest),
        XrechnungArtifactReference(xrechnung_artifact_id=artifact.id),
    )

    assert rendered.export_manifest == {
        "legal_original": "xml",
        "legal_original_artifact_id": artifact.id,
        "legal_original_sha256": artifact.sha256,
        "visual_copy": "pdf",
        "visual_copy_sha256": rendered.sha256,
    }
    with pikepdf.open(io.BytesIO(rendered.content)) as pdf:
        assert list(pdf.attachments) == []
        assert b"factur-x" not in bytes(pdf.Root.Metadata).lower()


@pytest.mark.asyncio
async def test_einvoice_artifact_rejects_snapshot_and_stored_hash_mismatch(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    snapshot = _einvoice_snapshot()
    digest = snapshot_sha256(snapshot)
    document = await _document(db_session, "Integrity")
    xml = render_zugferd(from_snapshot(snapshot), "en16931")
    report = validate_xml(xml, "zugferd", "cii-d22b", "en16931")
    artifact = await store_artifact(
        db_session,
        document,
        xml,
        report,
        snapshot_sha256=digest,
    )
    await db_session.flush()

    with pytest.raises(EInvoiceArtifactError, match="SNAPSHOT_MISMATCH"):
        await load_validated_artifact(
            db_session,
            artifact.id,
            expected_document_id=document.id,
            expected_snapshot_sha256="0" * 64,
            correlation_id="hybrid-integrity-test",
        )
    audit = await db_session.scalar(
        select(DocumentAuditEvent).where(
            DocumentAuditEvent.object_type == "document_artifact",
            DocumentAuditEvent.object_id == artifact.id,
        )
    )
    assert audit is not None
    assert audit.after["code"] == "EINVOICE_ARTIFACT_SNAPSHOT_MISMATCH"

    (tmp_path / artifact.storage_path).write_bytes(xml + b" ")
    with pytest.raises(EInvoiceArtifactError, match="ZUGFERD_XML_HASH_MISMATCH"):
        materialize_validated_artifact(
            artifact,
            expected_document_id=document.id,
            expected_snapshot_sha256=digest,
        )
