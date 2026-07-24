from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.models.business_profile import (
    BusinessProfile,
    BusinessProfileAddress,
    BusinessProfileBankAccount,
    BusinessProfileTaxIdentifier,
)
from backend.app.models.number_sequence import NumberSequence
from backend.app.schemas.document_configuration import CreateConfigurationCommand
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.document_configuration import create_draft, publish, update_draft
from backend.app.services.document_readiness import check_configuration
from backend.app.services.einvoice.validator import pinned_rule_versions
from backend.app.services.tax_decision import (
    TAX_RULES_2026_1,
    TaxDecisionInput,
    TaxOverride,
    TaxOverrideActor,
    determine_tax,
    override_tax,
)


async def _complete_profile(db_session) -> tuple[BusinessProfile, BusinessProfileBankAccount]:
    profile = BusinessProfile(
        name="E2E", legal_name="PrintOps GmbH", country_code="DE", default_currency="EUR", default_locale="de"
    )
    db_session.add(profile)
    await db_session.flush()
    address = BusinessProfileAddress(
        business_profile_id=profile.id,
        kind="registered",
        street="Werkstraße 1",
        postal_code="10115",
        city="Berlin",
        country_code="DE",
        is_default=True,
    )
    tax_id = BusinessProfileTaxIdentifier(
        business_profile_id=profile.id, kind="vat", value="DE123456789", country_code="DE", is_primary=True
    )
    bank = BusinessProfileBankAccount(
        business_profile_id=profile.id,
        label="Geschäftskonto",
        account_holder="PrintOps GmbH",
        currency="EUR",
        iban="DE02120300000000202051",
        bic="BYLADEM1001",
        is_default=True,
    )
    db_session.add_all([address, tax_id, bank])
    await db_session.flush()
    return profile, bank


@pytest.mark.asyncio
async def test_complete_german_invoice_configuration_reaches_published_state(db_session):
    profile, bank = await _complete_profile(db_session)
    db_session.add(
        NumberSequence(
            business_profile_id=profile.id,
            key="invoice",
            prefix="RE",
            pattern="{PREFIX}-{YYYY}-{####}",
            reset_policy="yearly",
        )
    )
    configuration = await create_draft(
        db_session,
        CreateConfigurationCommand(
            business_profile_id=profile.id,
            document_type=DocumentType.INVOICE,
            language="de",
            change_reason="Erstanlage Rechnung",
        ),
        actor_id=None,
    )
    configuration = await update_draft(
        db_session,
        configuration.id,
        configuration.lock_version,
        {
            "payment": {
                "bank_account_id": bank.id,
                "bank_assignments": [{"bank_account_id": bank.id, "is_default": True}],
            },
            "tax": {
                "allowed_cases": ["domestic_standard", "eu_reverse_charge", "eu_b2c_oss", "third_country"],
                "allow_override": True,
            },
            "einvoice": {
                "seller_identifier": "rechnung@printops.example",
                "seller_identifier_scheme": "EM",
                "bank_account_id": bank.id,
            },
        },
        actor_id=None,
    )

    readiness = await check_configuration(db_session, configuration.id)
    published = await publish(
        db_session,
        configuration.id,
        configuration.lock_version,
        date.today(),
        "Fachlich geprüfte Erstfreigabe",
        None,
        {"tax": TAX_RULES_2026_1.version, **pinned_rule_versions()},
    )

    assert readiness.status == "ready", readiness.model_dump()
    assert published.status == "active"
    assert published.publication.validation_status == "passed"
    assert published.publication.rule_versions["xrechnung"] == "3.0.2-2026-01-31"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["de", "en"])
async def test_every_document_type_has_a_complete_localized_draft(db_session, language):
    profile, _bank = await _complete_profile(db_session)

    for document_type in DocumentType:
        draft = await create_draft(
            db_session,
            CreateConfigurationCommand(
                business_profile_id=profile.id, document_type=document_type, language=language, change_reason="Coverage"
            ),
            actor_id=None,
        )
        purposes = {block.purpose for block in draft.text_blocks}
        assert {"intro", "closing"} <= purposes
        assert bool(draft.einvoice_policy) is True
        assert draft.einvoice_policy.requirement == (
            "rule_required" if DOCUMENT_CAPABILITIES[document_type].einvoice else "optional"
        )


@pytest.mark.parametrize(
    ("buyer_country", "buyer_kind", "vat_id", "vat_valid", "treatment"),
    [
        ("FR", "business", "FR12345678901", True, "eu_reverse_charge"),
        ("FR", "consumer", None, None, "eu_b2c_oss"),
        ("US", "business", None, None, "third_country"),
    ],
)
def test_cross_border_tax_paths_and_manual_override_are_auditable(
    buyer_country, buyer_kind, vat_id, vat_valid, treatment
):
    decision = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country=buyer_country,
            place_of_supply=buyer_country,
            buyer_kind=buyer_kind,
            buyer_vat_id=vat_id,
            buyer_vat_valid=vat_valid,
        ),
        TAX_RULES_2026_1,
    )
    assert decision.treatment == treatment
    assert decision.rule_version == "2026.1"

    overridden = override_tax(
        decision,
        TaxOverride(
            treatment="reviewed_treatment",
            tax_country=buyer_country,
            category_code="O",
            rate=Decimal("0"),
            legal_reason_code="MANUAL",
            legal_reason_text="Steuerlich geprüft",
            reason="Prüfung durch Steuerberatung vom 22.07.2026",
        ),
        TaxOverrideActor(user_id=42, can_override=True),
    )
    assert overridden.manual_override is True
    assert overridden.override_actor_id == 42
    assert overridden.override_reason
    assert overridden.overridden_at is not None
