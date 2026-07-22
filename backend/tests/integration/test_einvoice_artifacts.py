from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument
from backend.app.services.einvoice.artifacts import store_artifact
from backend.app.services.einvoice.validator import EInvoiceValidationReport


@pytest.mark.asyncio
async def test_artifact_is_server_named_outside_database_and_hash_verified(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    profile = BusinessProfile(
        name="Artifact profile",
        legal_name="Artifact GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.flush()
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0001",
        technical_status="issued",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    xml = b'<?xml version="1.0" encoding="UTF-8"?><Invoice/>'
    report = EInvoiceValidationReport(
        standard="xrechnung",
        syntax="ubl-2.1",
        profile="xrechnung",
        rule_versions={"en16931": "1.3.16", "xrechnung": "3.0.2-2026-01-31"},
        findings=(),
    )

    artifact = await store_artifact(db_session, document, xml, report, report.rule_versions)
    await db_session.flush()

    assert artifact.content is None
    assert artifact.sha256 == sha256(xml).hexdigest()
    assert artifact.storage_path is not None
    assert ".." not in Path(artifact.storage_path).parts
    stored = tmp_path / artifact.storage_path
    assert stored.is_file()
    assert stored.read_bytes() == xml
    assert artifact.validation_report["byte_size"] == len(xml)
    assert artifact.validation_report["standard"] == "xrechnung"


@pytest.mark.asyncio
async def test_invalid_report_is_never_persisted(db_session):
    report = EInvoiceValidationReport(
        standard="xrechnung",
        syntax="ubl-2.1",
        profile="xrechnung",
        rule_versions={"xrechnung": "3.0.2-2026-01-31"},
        findings=(),
        processing_error="validator unavailable",
    )

    with pytest.raises(ValueError, match="valid"):
        await store_artifact(db_session, CommercialDocument(), b"<Invoice/>", report, {})
