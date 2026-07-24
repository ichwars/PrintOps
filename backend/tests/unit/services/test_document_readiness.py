"""Readiness aggregation contracts for document configuration."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

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
from backend.app.services.document_readiness import check_configuration, probe_document_runtime
from backend.app.services.verapdf import VeraPdfRunner


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
        item.code == "bank_account_missing" and item.field_path == "payment.bank_account_id" for item in report.findings
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


def test_runtime_readiness_reports_versions_without_sensitive_paths(tmp_path):
    renderer = tmp_path / "weasyprint.exe"
    renderer.write_bytes(b"runtime")

    def execute(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            "WeasyPrint version: 69.0\nPango version: 15701\n",
            "",
        )

    status = probe_document_runtime(
        renderer_cli=renderer,
        validator=SimpleNamespace(version=lambda: "1.30.2"),
        process_runner=execute,
    )
    assert status.ready is True
    assert status.renderer.version == "69.0"
    assert status.pango.version == "15701"
    assert status.validator.version == "1.30.2"
    assert status.icc_profile_valid is True
    assert str(tmp_path) not in status.model_dump_json()


def test_runtime_readiness_has_concrete_missing_component_codes(tmp_path):
    status = probe_document_runtime(
        renderer_cli=tmp_path / "missing.exe",
        validator=VeraPdfRunner(cli_path=None, report_dir=tmp_path / "reports"),
    )
    assert "PDF_RENDERER_UNAVAILABLE" in status.findings
    assert "PDF_PANGO_UNAVAILABLE" in status.findings
    assert "PDF_VALIDATOR_UNAVAILABLE" in status.findings
