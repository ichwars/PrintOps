"""Readiness aggregation contracts for document configuration."""

from backend.app.models.business_profile import BusinessProfile, BusinessProfileBankAccount
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
from backend.app.services.document_readiness import check_configuration


async def test_configuration_readiness_reports_clickable_bank_blocker(db_session):
    profile = BusinessProfile(
        name="Readiness profile",
        legal_name="Readiness GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    bank = BusinessProfileBankAccount(
        business_profile_id=profile.id,
        label="Unvollständig",
        account_holder="Readiness GmbH",
        currency="EUR",
        account_number="12345",
        is_default=True,
    )
    db_session.add(bank)
    await db_session.flush()
    configuration = DocumentConfiguration(
        business_profile_id=profile.id,
        document_type="invoice",
        language="de",
        version=1,
        status="draft",
    )
    configuration.basic_policy = DocumentBasicPolicy(subject="Rechnung {DOCUMENT_NUMBER}")
    configuration.payment_policy = PaymentPolicy(payment_term_days=14, currency="EUR", bank_account_id=bank.id)
    configuration.dunning_policy = DunningPolicy(enabled=False)
    configuration.content_policy = DocumentContentPolicy(include_calculation_data=True)
    configuration.tax_policy = TaxPolicy(allowed_cases=["domestic"])
    configuration.einvoice_policy = EInvoicePolicy(
        requirement="rule_required",
        en16931_version="1.3.16",
        cius_name="XRechnung",
        cius_version="3.0.2",
        seller_identifier="0088:1234567890123",
    )
    configuration.text_blocks = [
        DocumentTextBlock(purpose="intro", body="Rechnung {DOCUMENT_NUMBER}", position=0),
        DocumentTextBlock(purpose="closing", body="Vielen Dank.", position=1),
        DocumentTextBlock(purpose="payment_terms", body="Zahlbar bis {DUE_DATE}.", position=2),
    ]
    db_session.add(configuration)
    await db_session.flush()

    report = await check_configuration(db_session, configuration.id)

    assert report.status == "blocked"
    assert any(
        item.code == "bank_account_missing" and item.field_path == "payment.bank_account_id"
        for item in report.findings
    )


async def test_readiness_status_distinguishes_warnings_from_blockers():
    from backend.app.services.document_readiness import ReadinessFinding, report_from_findings

    warning = ReadinessFinding(
        severity="warning",
        code="optional_reference_missing",
        field_path="einvoice.buyer_reference",
        message_key="documents.warnings.optionalReference",
        correction="Add a default reference if available",
    )

    report = report_from_findings("configuration", [warning])

    assert report.status == "warnings"
