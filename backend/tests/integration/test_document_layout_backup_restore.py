from __future__ import annotations

from hashlib import sha256

import pytest
from sqlalchemy import func, select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.models.document_layout import (
    DocumentLayoutAsset,
    DocumentLayoutAuditReceipt,
    DocumentLayoutConfiguration,
    DocumentLayoutPublication,
    LayoutFooterRules,
    LayoutHeaderRules,
    LayoutNotesRules,
    LayoutPageRules,
    LayoutPositionRules,
    LayoutTechnicalRules,
    LayoutTitleRules,
    LayoutTotalsRules,
    LayoutTypographyRules,
)
from backend.app.schemas.business_profile import BusinessProfileCreate
from backend.app.services.business_profile import create_business_profile
from backend.app.services.document_layouts import ensure_default_layout_drafts
from backend.app.services.github_backup import GitHubBackupService


@pytest.mark.asyncio
async def test_existing_profile_gets_one_unpublished_classic_draft(db_session):
    profile = BusinessProfile(
        name="Migration",
        legal_name="Migration GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()

    assert await ensure_default_layout_drafts(db_session, migration_event=True) == 1
    assert await ensure_default_layout_drafts(db_session, migration_event=True) == 0

    layout = await db_session.scalar(
        select(DocumentLayoutConfiguration).where(
            DocumentLayoutConfiguration.business_profile_id == profile.id
        )
    )
    assert layout is not None
    assert (layout.template_key, layout.page_format, layout.orientation) == ("classic", "A4", "portrait")
    assert (layout.scope_key, layout.version, layout.status) == ("*|*", 1, "draft")
    assert await db_session.scalar(
        select(func.count(DocumentLayoutPublication.id)).where(
            DocumentLayoutPublication.configuration_id == layout.id
        )
    ) == 0
    for rule_model in (
        LayoutPageRules,
        LayoutTypographyRules,
        LayoutHeaderRules,
        LayoutTitleRules,
        LayoutPositionRules,
        LayoutTotalsRules,
        LayoutTechnicalRules,
        LayoutNotesRules,
        LayoutFooterRules,
    ):
        assert await db_session.get(rule_model, layout.id) is not None
    events = list(
        await db_session.scalars(
            select(DocumentLayoutAuditReceipt.event_type).where(
                DocumentLayoutAuditReceipt.configuration_id == layout.id
            )
        )
    )
    assert events == ["created", "migrated_as_draft"]


@pytest.mark.asyncio
async def test_new_business_profile_gets_default_layout_draft(db_session):
    profile = await create_business_profile(
        db_session,
        BusinessProfileCreate(
            name="Neu",
            legal_name="Neu GmbH",
            country_code="DE",
            default_currency="EUR",
            timezone="Europe/Berlin",
            default_locale="de",
            addresses=[
                {
                    "kind": "registered",
                    "street": "Testweg 1",
                    "postal_code": "10115",
                    "city": "Berlin",
                    "country_code": "DE",
                    "is_default": True,
                }
            ],
        ),
    )

    layouts = list(
        await db_session.scalars(
            select(DocumentLayoutConfiguration).where(
                DocumentLayoutConfiguration.business_profile_id == profile.id
            )
        )
    )
    assert len(layouts) == 1
    assert (layouts[0].template_key, layouts[0].status, layouts[0].version) == ("classic", "draft", 1)


@pytest.mark.asyncio
async def test_private_git_backup_uses_binary_paths_for_layout_and_document_evidence(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    profile = BusinessProfile(
        name="Git backup",
        legal_name="Git Backup GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    await ensure_default_layout_drafts(db_session, migration_event=True)

    logo = b"safe-logo-bytes"
    logo_digest = sha256(logo).hexdigest()
    logo_key = f"document-layout-assets/{profile.id}/logo/{logo_digest}"
    logo_path = tmp_path / logo_key
    logo_path.parent.mkdir(parents=True)
    logo_path.write_bytes(logo)
    db_session.add(
        DocumentLayoutAsset(
            business_profile_id=profile.id,
            asset_type="logo",
            original_name="logo.png",
            mime_type="image/png",
            size_bytes=len(logo),
            sha256=logo_digest,
            storage_key=logo_key,
            preflight_status="valid",
            preflight_report={"valid": True},
        )
    )
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-1",
        technical_status="issued",
        business_status="open",
        payment_status="unpaid",
        language="de",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    pdf = b"%PDF-1.7 issued"
    xml = b"<rsm:CrossIndustryInvoice/>"
    xml_digest = sha256(xml).hexdigest()
    xml_key = f"document-artifacts/{document.id}/{xml_digest}.xml"
    xml_path = tmp_path / xml_key
    xml_path.parent.mkdir(parents=True)
    xml_path.write_bytes(xml)
    db_session.add_all(
        [
            DocumentArtifact(
                document_id=document.id,
                kind="pdf",
                content_type="application/pdf",
                content=pdf,
                sha256=sha256(pdf).hexdigest(),
                validation_status="valid",
                validation_report={"valid": True},
                render_receipt={"renderer_version": "test"},
            ),
            DocumentArtifact(
                document_id=document.id,
                kind="zugferd_xml",
                content_type="application/xml",
                storage_path=xml_key,
                sha256=xml_digest,
                validation_status="valid",
                validation_report={"valid": True, "profile": "EN16931"},
            ),
        ]
    )
    report = tmp_path / "document-validation-reports" / "verapdf.xml"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"<report compliant='true'/>")
    await db_session.flush()

    files: dict = {}
    await GitHubBackupService()._collect_commercial_evidence(db_session, files)

    binary_files = {path: value for path, value in files.items() if path.startswith("documents/binary/")}
    assert logo in binary_files.values()
    assert pdf in binary_files.values()
    assert xml in binary_files.values()
    assert report.read_bytes() in binary_files.values()
    artifact_rows = files["documents/tables/document_artifacts.json"]["rows"]
    assert all(row["content"] is None for row in artifact_rows)
    manifest = files["documents/evidence-manifest.json"]
    assert manifest["artifact_storage"] == "content-addressed/binary"
    assert {entry["evidence_type"] for entry in manifest["files"]} == {
        "document_artifact",
        "layout_asset",
        "validation_report",
    }
    assert manifest["integrity_status"] == "valid"
    assert manifest["file_count"] == len(binary_files)
    assert all(entry["integrity_status"] == "valid" for entry in manifest["files"])
    assert all(
        entry["sha256"] == sha256(binary_files[entry["path"]]).hexdigest()
        and entry["size"] == len(binary_files[entry["path"]])
        for entry in manifest["files"]
    )
    assert all(
        ".." not in entry["path"].split("/") and entry["path"].startswith("documents/binary/")
        for entry in manifest["files"]
    )
