"""Relational schema and append-only evidence contracts for document layouts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import Base, migrate_document_layout_schema
from backend.app.models.commercial_document import DocumentArtifact, ImmutableDocumentError
from backend.app.models.document_layout import (
    DocumentLayoutAsset,
    DocumentLayoutAssetLink,
    DocumentLayoutAuditReceipt,
    DocumentLayoutConfiguration,
    DocumentLayoutPublication,
    ImmutableLayoutError,
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

RULE_TABLES = {
    "layout_page_rules",
    "layout_typography_rules",
    "layout_header_rules",
    "layout_title_rules",
    "layout_position_rules",
    "layout_totals_rules",
    "layout_technical_rules",
    "layout_notes_rules",
    "layout_footer_rules",
}


def layout(**overrides) -> DocumentLayoutConfiguration:
    values = {
        "business_profile_id": 1,
        "document_type": None,
        "language": None,
        "version": 1,
        "template_key": "classic",
        "page_format": "A4",
        "orientation": "portrait",
        "status": "draft",
        "lock_version": 1,
        "renderer_version": "weasyprint-69.0+pikepdf-10.10.0",
        "validation_status": "pending",
    }
    values.update(overrides)
    return DocumentLayoutConfiguration(**values)


@pytest.mark.asyncio
async def test_fresh_schema_contains_typed_sections_and_artifact_receipts(test_engine):
    async with test_engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        artifact_columns = await connection.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("document_artifacts")}
        )

    assert tables >= RULE_TABLES
    assert {
        "document_layout_configurations",
        "document_layout_assets",
        "document_layout_asset_links",
        "document_layout_publications",
        "document_layout_audit_receipts",
        "document_preview_jobs",
    } <= tables
    assert {
        "layout_configuration_id",
        "layout_version",
        "layout_effective_sha256",
        "asset_receipts",
        "renderer_version",
        "validator_version",
        "render_receipt",
    } <= artifact_columns


@pytest.mark.asyncio
async def test_language_scope_requires_document_type(db_session):
    db_session.add(layout(language="de"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_scope_version_is_null_safe_unique(db_session):
    db_session.add_all([layout(), layout()])
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_all_nine_sections_are_one_to_one(db_session):
    configuration = layout(document_type="invoice", language="de")
    db_session.add(configuration)
    await db_session.flush()
    sections = [
        LayoutPageRules(configuration_id=configuration.id),
        LayoutTypographyRules(configuration_id=configuration.id),
        LayoutHeaderRules(configuration_id=configuration.id),
        LayoutTitleRules(configuration_id=configuration.id),
        LayoutPositionRules(configuration_id=configuration.id),
        LayoutTotalsRules(configuration_id=configuration.id),
        LayoutTechnicalRules(configuration_id=configuration.id),
        LayoutNotesRules(configuration_id=configuration.id),
        LayoutFooterRules(configuration_id=configuration.id),
    ]
    db_session.add_all(sections)
    await db_session.commit()

    db_session.add(LayoutPageRules(configuration_id=configuration.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_published_layout_and_sections_refuse_update_and_delete(db_session):
    configuration = layout(status="active", effective_from=datetime.now(UTC))
    page = LayoutPageRules(configuration=configuration)
    db_session.add(configuration)
    await db_session.commit()
    configuration_id = configuration.id

    configuration.template_key = "modern"
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()
    await db_session.rollback()

    page = await db_session.get(LayoutPageRules, configuration_id)
    page.margin_top_mm = 20
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()
    await db_session.rollback()

    configuration = await db_session.get(DocumentLayoutConfiguration, configuration_id)
    await db_session.delete(configuration)
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_asset_linked_to_published_layout_refuses_update_and_delete(db_session):
    configuration = layout(status="active", effective_from=datetime.now(UTC))
    asset = DocumentLayoutAsset(
        business_profile_id=1,
        asset_type="logo",
        original_name="logo.svg",
        mime_type="image/svg+xml",
        size_bytes=128,
        sha256="a" * 64,
        storage_key="aa/" + "a" * 64,
        preflight_status="valid",
    )
    configuration.asset_links.append(DocumentLayoutAssetLink(asset=asset, role="logo"))
    db_session.add(configuration)
    await db_session.commit()
    asset_id = asset.id

    asset.original_name = "changed.svg"
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()
    await db_session.rollback()

    asset = await db_session.get(DocumentLayoutAsset, asset_id)
    await db_session.delete(asset)
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_audit_and_render_receipts_are_append_only(db_session):
    configuration = layout(status="active", effective_from=datetime.now(UTC))
    publication = DocumentLayoutPublication(
        configuration=configuration,
        effective_sha256="b" * 64,
        renderer_version="weasyprint-69.0+pikepdf-10.10.0",
        validator_version="verapdf-1.30.2",
        validation_status="valid",
    )
    audit = DocumentLayoutAuditReceipt(
        configuration=configuration,
        event_type="publish",
        reason="approved",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    artifact = DocumentArtifact(
        document_id=999,
        kind="pdf",
        content_type="application/pdf",
        sha256="c" * 64,
        layout_version=1,
        layout_effective_sha256="b" * 64,
        renderer_version="weasyprint-69.0+pikepdf-10.10.0",
        validator_version="verapdf-1.30.2",
    )
    db_session.add_all([configuration, publication, audit, artifact])
    await db_session.commit()
    audit_id = audit.id
    artifact_id = artifact.id

    publication.validation_status = "invalid"
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()
    await db_session.rollback()

    audit = await db_session.get(DocumentLayoutAuditReceipt, audit_id)
    audit.reason = "rewritten"
    with pytest.raises(ImmutableLayoutError):
        await db_session.commit()
    await db_session.rollback()

    artifact = await db_session.get(DocumentArtifact, artifact_id)
    artifact.sha256 = "d" * 64
    with pytest.raises(ImmutableDocumentError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_upgrade_adds_artifact_receipts_and_is_idempotent(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'layout-upgrade.db'}")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE document_artifacts ("
                "id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, kind VARCHAR(32) NOT NULL, "
                "content_type VARCHAR(128) NOT NULL, sha256 VARCHAR(64) NOT NULL)"
            )
        )
        await connection.run_sync(Base.metadata.create_all)
        await migrate_document_layout_schema(connection)
        await migrate_document_layout_schema(connection)
        columns = await connection.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("document_artifacts")}
        )
    await engine.dispose()

    assert "layout_configuration_id" in columns
    assert "render_receipt" in columns
    assert "validator_version" in columns
