"""Startup migration contracts for document configuration defaults."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.database import _migrate_document_configurations
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_configuration import DocumentConfiguration
from backend.app.models.settings import Settings
from backend.app.services.document_catalog import DocumentType


async def test_legacy_settings_migrate_to_complete_bilingual_drafts(test_engine, db_session):
    profile = BusinessProfile(
        name="Migration profile",
        legal_name="Migration GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    db_session.add_all(
        [
            Settings(key="orders.offer_validity_days", value="30"),
            Settings(key="orders.payment_term_days", value="21"),
            Settings(key="orders.offer_default_text", value="Individuelles Angebot"),
            Settings(key="orders.invoice_default_text", value="Individuelle Rechnung"),
            Settings(key="orders.pdf_footer_text", value="Individuelle Fußzeile"),
        ]
    )
    await db_session.commit()

    async with test_engine.begin() as connection:
        await _migrate_document_configurations(connection)
        await _migrate_document_configurations(connection)

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(DocumentConfiguration).where(DocumentConfiguration.business_profile_id == profile.id)
            )
        ).all()

    assert {(row.document_type, row.language) for row in rows} == {
        (document_type.value, language) for document_type in DocumentType for language in ("de", "en")
    }
    assert all(row.status == "draft" and row.version == 1 for row in rows)

    german_invoice = next(row for row in rows if row.document_type == "invoice" and row.language == "de")
    german_quotation = next(row for row in rows if row.document_type == "quotation" and row.language == "de")

    assert german_invoice.payment_policy.payment_term_days == 21
    assert any(block.body == "Individuelle Rechnung" for block in german_invoice.text_blocks)
    assert any(block.body == "Individuelle Fußzeile" for block in german_invoice.text_blocks)
    assert german_quotation.basic_policy.validity_days == 30
    assert any(block.body == "Individuelles Angebot" for block in german_quotation.text_blocks)
