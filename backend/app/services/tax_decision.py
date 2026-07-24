from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

BuyerKind = Literal["business", "consumer"]
TransactionKind = Literal["service", "goods"]
SellerTaxMode = Literal["standard", "small_business"]

EU_COUNTRY_CODES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)


@dataclass(frozen=True, slots=True)
class TaxRules:
    version: str
    standard_rates: Mapping[str, Decimal]


TAX_RULES_2026_1 = TaxRules(
    version="2026.1",
    standard_rates={
        "AT": Decimal("20.00"),
        "BE": Decimal("21.00"),
        "BG": Decimal("20.00"),
        "HR": Decimal("25.00"),
        "CY": Decimal("19.00"),
        "CZ": Decimal("21.00"),
        "DE": Decimal("19.00"),
        "DK": Decimal("25.00"),
        "EE": Decimal("24.00"),
        "ES": Decimal("21.00"),
        "FI": Decimal("25.50"),
        "FR": Decimal("20.00"),
        "GR": Decimal("24.00"),
        "HU": Decimal("27.00"),
        "IE": Decimal("23.00"),
        "IT": Decimal("22.00"),
        "LT": Decimal("21.00"),
        "LU": Decimal("17.00"),
        "LV": Decimal("21.00"),
        "MT": Decimal("18.00"),
        "NL": Decimal("21.00"),
        "PL": Decimal("23.00"),
        "PT": Decimal("23.00"),
        "RO": Decimal("21.00"),
        "SE": Decimal("25.00"),
        "SI": Decimal("22.00"),
        "SK": Decimal("23.00"),
    },
)


@dataclass(frozen=True, slots=True)
class TaxDecisionInput:
    seller_country: str | None
    buyer_country: str | None
    place_of_supply: str | None
    buyer_kind: BuyerKind
    seller_tax_mode: SellerTaxMode = "standard"
    transaction_kind: TransactionKind = "service"
    seller_vat_id: str | None = None
    buyer_vat_id: str | None = None
    buyer_vat_valid: bool | None = None
    vat_validation_evidence: Mapping[str, str] | None = None
    exemption_code: str | None = None
    exemption_text: str | None = None


@dataclass(frozen=True, slots=True)
class TaxFinding:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TaxDecision:
    treatment: str
    tax_country: str | None
    place_of_supply: str | None
    category_code: str | None
    rate: Decimal | None
    legal_reason_code: str | None
    legal_reason_text: str | None
    seller_vat_id: str | None
    buyer_vat_id: str | None
    vat_validation_evidence: Mapping[str, str]
    rule_version: str
    blocking_findings: tuple[TaxFinding, ...] = ()
    manual_override: bool = False
    override_reason: str | None = None
    override_actor_id: int | None = None
    overridden_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TaxOverride:
    treatment: str
    tax_country: str
    category_code: str
    rate: Decimal
    legal_reason_code: str | None
    legal_reason_text: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class TaxOverrideActor:
    user_id: int
    can_override: bool


def _country(value: str | None) -> str | None:
    return value.strip().upper() if value and value.strip() else None


def _blocked(data: TaxDecisionInput, rules: TaxRules, findings: list[TaxFinding]) -> TaxDecision:
    return TaxDecision(
        treatment="blocked",
        tax_country=_country(data.place_of_supply),
        place_of_supply=_country(data.place_of_supply),
        category_code=None,
        rate=None,
        legal_reason_code=None,
        legal_reason_text=None,
        seller_vat_id=data.seller_vat_id,
        buyer_vat_id=data.buyer_vat_id,
        vat_validation_evidence=dict(data.vat_validation_evidence or {}),
        rule_version=rules.version,
        blocking_findings=tuple(findings),
    )


def _decision(
    data: TaxDecisionInput,
    rules: TaxRules,
    *,
    treatment: str,
    category_code: str,
    rate: Decimal,
    legal_reason_code: str | None = None,
    legal_reason_text: str | None = None,
) -> TaxDecision:
    place_of_supply = _country(data.place_of_supply)
    return TaxDecision(
        treatment=treatment,
        tax_country=place_of_supply,
        place_of_supply=place_of_supply,
        category_code=category_code,
        rate=rate,
        legal_reason_code=legal_reason_code,
        legal_reason_text=legal_reason_text,
        seller_vat_id=data.seller_vat_id,
        buyer_vat_id=data.buyer_vat_id,
        vat_validation_evidence=dict(data.vat_validation_evidence or {}),
        rule_version=rules.version,
    )


def determine_tax(data: TaxDecisionInput, rules: TaxRules) -> TaxDecision:
    """Return a deterministic tax classification or explicit blocking findings.

    The engine deliberately consumes already collected VAT evidence. External VAT
    validation is an upstream process and is never performed while issuing a document.
    """
    seller_country = _country(data.seller_country)
    buyer_country = _country(data.buyer_country)
    place_of_supply = _country(data.place_of_supply)
    findings: list[TaxFinding] = []
    if seller_country is None:
        findings.append(TaxFinding("seller_country_missing", "Seller country is required"))
    if buyer_country is None:
        findings.append(TaxFinding("buyer_country_missing", "Buyer country is required"))
    if place_of_supply is None:
        findings.append(TaxFinding("place_of_supply_missing", "Place of supply is required"))
    if findings:
        return _blocked(data, rules, findings)

    assert seller_country is not None
    assert buyer_country is not None
    assert place_of_supply is not None

    if data.exemption_code or data.exemption_text:
        if not data.exemption_code or not data.exemption_text:
            return _blocked(
                data,
                rules,
                [
                    TaxFinding(
                        "exemption_evidence_incomplete",
                        "Exemption code and legal reason text are both required",
                    )
                ],
            )
        return _decision(
            data,
            rules,
            treatment="explicit_exemption",
            category_code="E",
            rate=Decimal("0.00"),
            legal_reason_code=data.exemption_code,
            legal_reason_text=data.exemption_text,
        )

    if data.seller_tax_mode == "small_business":
        return _decision(
            data,
            rules,
            treatment="small_business_exempt",
            category_code="E",
            rate=Decimal("0.00"),
            legal_reason_code="VATEX-EU-DE-19",
            legal_reason_text="Steuerbefreiung fuer Kleinunternehmer gemaess § 19 UStG",
        )

    if seller_country == buyer_country and place_of_supply == seller_country:
        rate = rules.standard_rates.get(place_of_supply)
        if rate is None:
            return _blocked(
                data,
                rules,
                [TaxFinding("tax_rate_missing", f"No standard tax rate exists for {place_of_supply}")],
            )
        return _decision(
            data,
            rules,
            treatment="domestic_standard",
            category_code="S",
            rate=rate,
        )

    seller_in_eu = seller_country in EU_COUNTRY_CODES
    buyer_in_eu = buyer_country in EU_COUNTRY_CODES
    if seller_in_eu and buyer_in_eu and seller_country != buyer_country:
        if data.buyer_kind == "business":
            if not data.buyer_vat_id or data.buyer_vat_valid is None:
                return _blocked(
                    data,
                    rules,
                    [
                        TaxFinding(
                            "buyer_vat_validation_missing",
                            "A validated buyer VAT identifier is required for EU B2B treatment",
                        )
                    ],
                )
            if data.buyer_vat_valid is False:
                return _blocked(
                    data,
                    rules,
                    [TaxFinding("buyer_vat_invalid", "The buyer VAT identifier is not valid")],
                )
            if data.transaction_kind == "goods":
                return _decision(
                    data,
                    rules,
                    treatment="intra_community_supply",
                    category_code="K",
                    rate=Decimal("0.00"),
                    legal_reason_code="VATEX-EU-IC",
                    legal_reason_text="Steuerfreie innergemeinschaftliche Lieferung",
                )
            return _decision(
                data,
                rules,
                treatment="eu_reverse_charge",
                category_code="AE",
                rate=Decimal("0.00"),
                legal_reason_code="VATEX-EU-AE",
                legal_reason_text="Steuerschuldnerschaft des Leistungsempfaengers",
            )

        rate = rules.standard_rates.get(buyer_country)
        if rate is None:
            return _blocked(
                data,
                rules,
                [TaxFinding("oss_rate_missing", f"No OSS tax rate exists for {buyer_country}")],
            )
        return _decision(
            data,
            rules,
            treatment="eu_b2c_oss",
            category_code="S",
            rate=rate,
        )

    if not buyer_in_eu and place_of_supply == buyer_country:
        if data.transaction_kind == "goods":
            category_code = "G"
            reason_code = "VATEX-EU-G"
            reason_text = "Steuerfreie Ausfuhrlieferung"
        else:
            category_code = "O"
            reason_code = "VATEX-EU-O"
            reason_text = "Leistung ausserhalb des Anwendungsbereichs der Umsatzsteuer"
        return _decision(
            data,
            rules,
            treatment="third_country",
            category_code=category_code,
            rate=Decimal("0.00"),
            legal_reason_code=reason_code,
            legal_reason_text=reason_text,
        )

    return _blocked(
        data,
        rules,
        [TaxFinding("tax_rule_not_found", "No deterministic tax rule matches the supplied facts")],
    )


def override_tax(
    decision: TaxDecision,
    override: TaxOverride,
    actor: TaxOverrideActor,
) -> TaxDecision:
    if not actor.can_override:
        raise PermissionError("The actor lacks the tax override permission")
    reason = override.reason.strip()
    if not reason:
        raise ValueError("A non-empty override reason is required")
    if override.rate < 0 or override.rate > 100:
        raise ValueError("Override rate must be between 0 and 100")

    return replace(
        decision,
        treatment=override.treatment,
        tax_country=_country(override.tax_country),
        place_of_supply=_country(override.tax_country),
        category_code=override.category_code,
        rate=override.rate,
        legal_reason_code=override.legal_reason_code,
        legal_reason_text=override.legal_reason_text,
        blocking_findings=(),
        manual_override=True,
        override_reason=reason,
        override_actor_id=actor.user_id,
        overridden_at=datetime.now(UTC),
    )
