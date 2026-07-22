"""Lifecycle and effective-value integration tests for document configuration."""

from datetime import date

import pytest

from backend.app.models.business_profile import BusinessProfile, BusinessProfileBankAccount
from backend.app.models.customer import Customer, CustomerAccount
from backend.app.models.document_configuration import (
    DocumentBasicPolicy,
    DocumentConfiguration,
    DocumentContentPolicy,
    DocumentTextBlock,
    DunningPolicy,
    EInvoicePolicy,
    PaymentPolicy,
    TaxPolicy,
)
from backend.app.services.document_configuration import (
    clone_version,
    publish,
    resolve_effective,
    to_draft_schema,
    update_draft,
)
from backend.app.services.document_policy_validation import ConfigurationNotReady
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
    bank_account = BusinessProfileBankAccount(
        business_profile_id=profile.id,
        label="Geschäftskonto",
        account_holder="Lifecycle GmbH",
        currency="EUR",
        iban="DE02120300000000202051",
        is_default=True,
    )
    db_session.add(bank_account)
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
    configuration.payment_policy = PaymentPolicy(
        payment_term_days=14,
        currency="USD",
        bank_account_id=bank_account.id,
    )
    configuration.content_policy = DocumentContentPolicy(include_calculation_data=True)
    configuration.dunning_policy = DunningPolicy(enabled=False, annual_interest_rate=0, flat_fee=0)
    configuration.tax_policy = TaxPolicy(allowed_cases=["domestic"], allow_override=False)
    configuration.einvoice_policy = EInvoicePolicy(requirement="rule_required", syntax="ubl_2_1")
    configuration.text_blocks = [
        DocumentTextBlock(purpose="intro", body="Rechnung {DOCUMENT_NUMBER}", position=0),
        DocumentTextBlock(purpose="closing", body="Vielen Dank.", position=1),
        DocumentTextBlock(purpose="payment_terms", body="Zahlbar bis {DUE_DATE}.", position=2),
    ]
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


@pytest.mark.asyncio
async def test_publish_rejects_policy_blockers(db_session):
    _profile, _customer, active = await _configuration_fixture(db_session)
    draft = await clone_version(db_session, active.id, actor_id=7)
    draft = await update_draft(
        db_session,
        draft.id,
        expected_version=1,
        patch={"payment": {"payment_term_days": -1}},
        actor_id=7,
    )

    with pytest.raises(ConfigurationNotReady) as error:
        await publish(
            db_session,
            draft.id,
            expected_version=draft.lock_version,
            effective_from=date.today(),
            reason="Invalid payment policy",
            actor_id=7,
            rule_versions={"tax": "2026.1", "en16931": "1.3.16"},
        )

    assert any(finding.code == "payment_term_negative" for finding in error.value.findings)


@pytest.mark.asyncio
async def test_update_draft_persists_discount_and_installment_rules(db_session):
    _profile, _customer, active = await _configuration_fixture(db_session)
    draft = await clone_version(db_session, active.id, actor_id=7)

    updated = await update_draft(
        db_session,
        draft.id,
        expected_version=1,
        patch={
            "payment": {
                "discount_days": 7,
                "discount_percent": "2.00",
                "installments": [
                    {"percent": "40.00", "due_days": 7},
                    {"percent": "60.00", "due_days": 30},
                ],
            }
        },
        actor_id=7,
    )

    assert updated.payment_policy.early_payment_rules == [{"days": 7, "percent": "2.00"}]
    assert updated.payment_policy.installments == [
        {"percent": "40.00", "due_days": 7},
        {"percent": "60.00", "due_days": 30},
    ]


@pytest.mark.asyncio
async def test_update_draft_round_trips_basic_content_payment_and_dunning(db_session):
    _profile, _customer, active = await _configuration_fixture(db_session)
    draft = await clone_version(db_session, active.id, actor_id=7)

    updated = await update_draft(
        db_session,
        draft.id,
        expected_version=1,
        patch={
            "basic": {"subject": "Rechnung {DOCUMENT_NUMBER}", "reference_requirements": {"order_reference": True}},
            "content": {"include_calculation_data": False, "visible_content": {"material": True}},
            "payment": {"due_date_basis": "service_date", "payment_methods": ["bank_transfer"]},
            "dunning": {
                "enabled": True,
                "annual_interest_rate": "5.0000",
                "flat_fee": "2.50",
                "stages": [
                    {"level": 1, "wait_days": 7, "fee": "2.50", "charge_interest": True, "new_due_days": 7, "body": "Bitte zahlen.", "escalation_hint": None}
                ],
            },
        },
        actor_id=7,
    )

    policy = to_draft_schema(updated)
    assert policy.basic.reference_requirements == {"order_reference": True}
    assert policy.content.visible_content == {"material": True}
    assert policy.payment.due_date_basis == "service_date"
    assert policy.dunning.stages[0].body == "Bitte zahlen."
