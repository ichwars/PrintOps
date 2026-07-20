"""Relational schema contracts for versioned document configuration."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_configuration import (
    DocumentConfiguration,
    DocumentTextBlock,
    PaymentPolicy,
)


@pytest.mark.asyncio
async def test_configuration_schema_has_versioned_children(db_session):
    profile = BusinessProfile(
        name="Schema profile",
        legal_name="Schema GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()

    configuration = DocumentConfiguration(
        business_profile_id=profile.id,
        document_type="invoice",
        language="de",
        version=1,
        status="draft",
    )
    configuration.payment_policy = PaymentPolicy(payment_term_days=14, currency="EUR")
    configuration.text_blocks = [DocumentTextBlock(purpose="closing", body="Vielen Dank.")]
    db_session.add(configuration)
    await db_session.flush()

    assert configuration.payment_policy.configuration_id == configuration.id
    assert configuration.text_blocks[0].configuration_id == configuration.id


@pytest.mark.asyncio
async def test_configuration_version_key_is_unique(db_session):
    profile = BusinessProfile(
        name="Unique profile",
        legal_name="Unique GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add_all(
        [
            DocumentConfiguration(
                business_profile_id=profile.id,
                document_type="invoice",
                language="de",
                version=1,
                status="draft",
            ),
            DocumentConfiguration(
                business_profile_id=profile.id,
                document_type="invoice",
                language="de",
                version=1,
                status="draft",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_all_document_configuration_tables_are_registered(test_engine):
    async with test_engine.connect() as connection:
        table_names = await connection.run_sync(lambda sync_connection: set(inspect(sync_connection).get_table_names()))

    assert {
        "document_configurations",
        "document_basic_policies",
        "payment_policies",
        "dunning_policies",
        "dunning_stages",
        "document_text_blocks",
        "document_content_policies",
        "tax_policies",
        "einvoice_policies",
        "customer_document_preferences",
        "configuration_publications",
    } <= table_names
