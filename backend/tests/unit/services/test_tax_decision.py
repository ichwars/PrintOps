from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from backend.app.services.tax_decision import (
    TAX_RULES_2026_1,
    TaxDecisionInput,
    TaxOverride,
    TaxOverrideActor,
    determine_tax,
    override_tax,
)


@pytest.mark.parametrize(
    ("data", "treatment", "tax_country", "category_code", "rate"),
    [
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="DE",
                place_of_supply="DE",
                buyer_kind="business",
            ),
            "domestic_standard",
            "DE",
            "S",
            Decimal("19.00"),
        ),
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="FR",
                place_of_supply="FR",
                buyer_kind="business",
                buyer_vat_id="FR12345678901",
                buyer_vat_valid=True,
            ),
            "eu_reverse_charge",
            "FR",
            "AE",
            Decimal("0.00"),
        ),
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="FR",
                place_of_supply="FR",
                buyer_kind="consumer",
            ),
            "eu_b2c_oss",
            "FR",
            "S",
            Decimal("20.00"),
        ),
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="US",
                place_of_supply="US",
                buyer_kind="business",
            ),
            "third_country",
            "US",
            "O",
            Decimal("0.00"),
        ),
    ],
)
def test_determines_supported_tax_cases(data, treatment, tax_country, category_code, rate):
    decision = determine_tax(data, TAX_RULES_2026_1)

    assert decision.treatment == treatment
    assert decision.tax_country == tax_country
    assert decision.category_code == category_code
    assert decision.rate == rate
    assert decision.rule_version == "2026.1"
    assert decision.blocking_findings == ()


def test_distinguishes_small_business_goods_and_explicit_exemption():
    small_business = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country="DE",
            place_of_supply="DE",
            buyer_kind="business",
            seller_tax_mode="small_business",
        ),
        TAX_RULES_2026_1,
    )
    intra_community_goods = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country="NL",
            place_of_supply="NL",
            buyer_kind="business",
            buyer_vat_id="NL123456789B01",
            buyer_vat_valid=True,
            transaction_kind="goods",
        ),
        TAX_RULES_2026_1,
    )
    exempt = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country="DE",
            place_of_supply="DE",
            buyer_kind="business",
            exemption_code="VATEX-EU-132-1A",
            exemption_text="Steuerfreie Leistung",
        ),
        TAX_RULES_2026_1,
    )
    exported_goods = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country="US",
            place_of_supply="US",
            buyer_kind="business",
            transaction_kind="goods",
        ),
        TAX_RULES_2026_1,
    )

    assert small_business.treatment == "small_business_exempt"
    assert small_business.legal_reason_code == "VATEX-EU-DE-19"
    assert intra_community_goods.treatment == "intra_community_supply"
    assert intra_community_goods.category_code == "K"
    assert exempt.treatment == "explicit_exemption"
    assert exempt.legal_reason_code == "VATEX-EU-132-1A"
    assert exported_goods.category_code == "G"
    assert exported_goods.legal_reason_code == "VATEX-EU-G"


@pytest.mark.parametrize(
    ("data", "finding_code"),
    [
        (
            TaxDecisionInput(
                seller_country=None,
                buyer_country="DE",
                place_of_supply="DE",
                buyer_kind="business",
            ),
            "seller_country_missing",
        ),
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="DE",
                place_of_supply=None,
                buyer_kind="business",
            ),
            "place_of_supply_missing",
        ),
        (
            TaxDecisionInput(
                seller_country="DE",
                buyer_country="FR",
                place_of_supply="FR",
                buyer_kind="business",
                buyer_vat_id=None,
                buyer_vat_valid=None,
            ),
            "buyer_vat_validation_missing",
        ),
    ],
)
def test_blocks_when_tax_evidence_is_incomplete(data, finding_code):
    decision = determine_tax(data, TAX_RULES_2026_1)

    assert decision.treatment == "blocked"
    assert finding_code in {finding.code for finding in decision.blocking_findings}


def test_override_requires_permission_and_non_empty_reason():
    decision = determine_tax(
        TaxDecisionInput(
            seller_country="DE",
            buyer_country="DE",
            place_of_supply="DE",
            buyer_kind="business",
        ),
        TAX_RULES_2026_1,
    )
    override = TaxOverride(
        treatment="domestic_reduced",
        tax_country="DE",
        category_code="S",
        rate=Decimal("7.00"),
        legal_reason_code=None,
        legal_reason_text="Ermaessigter Steuersatz",
        reason="Manuelle steuerliche Pruefung, Artikel 123",
    )

    with pytest.raises(PermissionError):
        override_tax(decision, override, TaxOverrideActor(user_id=7, can_override=False))
    with pytest.raises(ValueError, match="reason"):
        override_tax(
            decision,
            replace(override, reason=" "),
            TaxOverrideActor(user_id=7, can_override=True),
        )

    overridden = override_tax(
        decision,
        override,
        TaxOverrideActor(user_id=7, can_override=True),
    )
    assert overridden.manual_override is True
    assert overridden.override_reason == override.reason
    assert overridden.override_actor_id == 7
    assert overridden.rate == Decimal("7.00")
    assert overridden.overridden_at is not None
