"""Lifecycle and effective-value integration tests for document configuration."""

from datetime import date

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import Customer, CustomerAccount
from backend.app.models.document_configuration import (
    DocumentBasicPolicy,
    DocumentConfiguration,
    DocumentContentPolicy,
    DocumentTextBlock,
    EInvoicePolicy,
    PaymentPolicy,
    TaxPolicy,
)
from backend.app.services.document_configuration import clone_version, publish, resolve_effective, update_draft
from backend.app.services.order_errors import VersionConflictError


async def _configuration_fixture(db_session):
    profile = BusinessProfile(
        name="Lifecycle profile",
        legal_name="Lifecycle GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    customer = Customer(kind="company", display_name="Example Customer", status="active", preferred_locale="de")
    db_session.add_all([profile, customer])
    await db_session.flush()
    db_session.add(
        CustomerAccount(
            customer_id=customer.id,
            business_profile_id=profile.id,
            number="KD-1",
            preferred_currency="EUR",
            payment_term_days=30,
        )
    )
    configuration = DocumentConfiguration(
        business_profile_id=profile.id,
        document_type="invoice",
        language="de",
        version=1,
        status="active",
        effective_from=date.today(),
        lock_version=1,
    )
    configuration.basic_policy = DocumentBasicPolicy(subject="Rechnung {DOCUMENT_NUMBER}")
    configuration.payment_policy = PaymentPolicy(payment_term_days=14, currency="USD")
    configuration.content_policy = DocumentContentPolicy(include_calculation_data=True)
    configuration.tax_policy = TaxPolicy(allowed_cases=["domestic"], allow_override=False)
    configuration.einvoice_policy = EInvoicePolicy(requirement="rule_required", syntax="ubl_2_1")
    configuration.text_blocks = [DocumentTextBlock(purpose="closing", body="Vielen Dank.", position=0)]
    db_session.add(configuration)
    await db_session.flush()
    return profile, customer, configuration


@pytest.mark.asyncio
async def test_publishing_clone_supersedes_previous_active_version(db_session):
    _profile, _customer, active = await _configuration_fixture(db_session)
    draft = await clone_version(db_session, active.id, actor_id=7)

    published = await publish(
        db_session,
        draft.id,
        expected_version=draft.lock_version,
        effective_from=date.today(),
        reason="Updated payment terms",
        actor_id=7,
        rule_versions={"tax": "2026.1", "en16931": "1.3.16"},
    )

    assert published.status == "active"
    assert published.publication.rule_versions["en16931"] == "1.3.16"
    assert active.status == "superseded"
    assert draft.payment_policy is not active.payment_policy
    assert draft.text_blocks[0] is not active.text_blocks[0]


@pytest.mark.asyncio
async def test_effective_values_report_customer_and_document_sources(db_session):
    profile, customer, configuration = await _configuration_fixture(db_session)

    customer_result = await resolve_effective(
        db_session,
        profile.id,
        customer.id,
        "invoice",
        "de",
        {},
    )
    document_result = await resolve_effective(
        db_session,
        profile.id,
        customer.id,
        "invoice",
        "de",
        {"payment": {"payment_term_days": 45}},
    )

    assert customer_result.configuration_id == configuration.id
    assert customer_result.payment.payment_term_days.value == 30
    assert customer_result.payment.payment_term_days.source == "customer"
    assert customer_result.payment.currency.value == "EUR"
    assert customer_result.payment.currency.source == "customer"
    assert document_result.payment.payment_term_days.value == 45
    assert document_result.payment.payment_term_days.source == "document"


@pytest.mark.asyncio
async def test_update_draft_uses_compare_and_swap(db_session):
    _profile, _customer, active = await _configuration_fixture(db_session)
    draft = await clone_version(db_session, active.id, actor_id=7)

    updated = await update_draft(
        db_session,
        draft.id,
        expected_version=1,
        patch={"payment": {"payment_term_days": 21}},
        actor_id=7,
    )

    assert updated.lock_version == 2
    assert updated.payment_policy.payment_term_days == 21
    with pytest.raises(VersionConflictError):
        await update_draft(
            db_session,
            draft.id,
            expected_version=1,
            patch={"payment": {"payment_term_days": 28}},
            actor_id=7,
        )
