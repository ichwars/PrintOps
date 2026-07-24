from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.schemas.commercial_document import IssuedDocumentSnapshot, SnapshotLine
from backend.app.services.einvoice.canonical import from_snapshot, validate_math


def _snapshot(
    *rates: tuple[str, str],
    document_type: str = "invoice",
    contact_email: str | None = "rechnung@example.de",
    totals: dict[str, Decimal] | None = None,
) -> IssuedDocumentSnapshot:
    lines = tuple(
        SnapshotLine(
            position=position,
            description=f"Position {position}",
            quantity=Decimal("1"),
            unit_code="C62",
            unit_price=Decimal(net),
            net_amount=Decimal(net),
            tax_category_code="S",
            tax_rate=Decimal(rate),
        )
        for position, (rate, net) in enumerate(rates or (("19.00", "100.00"),), start=1)
    )
    expected_line_net = sum((line.net_amount for line in lines), Decimal("0"))
    expected_tax = sum(
        (line.net_amount * line.tax_rate / Decimal("100") for line in lines), Decimal("0")
    ).quantize(Decimal("0.01"))
    return IssuedDocumentSnapshot(
        document_type=document_type,
        number="RE-2026-0001",
        issue_date=date(2026, 7, 20),
        service_date=date(2026, 7, 19),
        due_date=date(2026, 8, 3),
        language="de-DE",
        currency="EUR",
        seller={
            "name": "Muster & Söhne GmbH",
            "address": {
                "line1": "Werkstraße 1",
                "city": "Berlin",
                "postal_code": "10115",
                "country_code": "DE",
            },
            "vat_id": "DE123456789",
            "electronic_address": "rechnung@example.de",
            "electronic_address_scheme": "EM",
            "contact": {"name": "Buchhaltung", "email": contact_email, "phone": ""},
        },
        buyer={
            "name": "Atelier Nord GmbH",
            "address": {
                "line1": "Hafenweg 3",
                "city": "Hamburg",
                "postal_code": "20457",
                "country_code": "DE",
            },
            "vat_id": "DE987654321",
            "electronic_address": "04011000-12345-34",
            "electronic_address_scheme": "0204",
            "buyer_reference": "04011000-12345-34",
        },
        lines=lines,
        totals=totals
        or {
            "line_net": expected_line_net,
            "allowance": Decimal("0.00"),
            "charge": Decimal("0.00"),
            "tax": expected_tax,
            "invoice_total": expected_line_net + expected_tax,
            "paid": Decimal("0.00"),
            "payable": expected_line_net + expected_tax,
        },
        payment={
            "means_code": "58",
            "iban": "DE02120300000000202051",
            "bic": "BYLADEM1001",
            "account_name": "Muster & Söhne GmbH",
            "terms": "Zahlbar innerhalb von 14 Tagen netto.",
        },
        references=({"kind": "order", "identifier": "PO-4711"},),
    )


def test_multi_rate_totals_are_grouped_and_exact() -> None:
    invoice = from_snapshot(_snapshot(("19.00", "100.00"), ("7.00", "50.00")))

    assert [(item.rate, item.taxable_amount) for item in invoice.tax_subtotals] == [
        (Decimal("7.00"), Decimal("50.00")),
        (Decimal("19.00"), Decimal("100.00")),
    ]
    assert invoice.tax_subtotals[0].tax_amount == Decimal("3.50")
    assert invoice.tax_subtotals[1].tax_amount == Decimal("19.00")
    assert invoice.tax_total == Decimal("22.50")
    assert invoice.payable_amount == Decimal("172.50")
    assert validate_math(invoice) == ()


def test_empty_optional_values_are_normalized_to_none() -> None:
    invoice = from_snapshot(_snapshot(contact_email=""))

    assert invoice.seller.contact.email is None
    assert invoice.seller.contact.phone is None


@pytest.mark.parametrize(
    ("document_type", "type_code", "is_credit", "is_self_billed"),
    [
        ("invoice", "380", False, False),
        ("advance_invoice", "386", False, False),
        ("invoice_correction", "384", False, False),
        ("cancellation_invoice", "381", True, False),
        ("commercial_credit_note", "381", True, False),
        ("self_billing", "389", False, True),
    ],
)
def test_document_types_have_explicit_en_codes(
    document_type: str, type_code: str, is_credit: bool, is_self_billed: bool
) -> None:
    invoice = from_snapshot(_snapshot(document_type=document_type))

    assert invoice.type_code == type_code
    assert invoice.is_credit is is_credit
    assert invoice.is_self_billed is is_self_billed


def test_iso_currency_and_country_codes_are_required() -> None:
    invalid_currency = _snapshot().model_copy(update={"currency": "EU1"})
    invalid_country = _snapshot().model_copy(
        update={"seller": {**_snapshot().seller, "address": {"country_code": "Deutschland"}}}
    )

    with pytest.raises(ValueError, match="ISO 4217"):
        from_snapshot(invalid_currency)
    with pytest.raises(ValueError, match="ISO 3166-1 alpha-2"):
        from_snapshot(invalid_country)


def test_math_validation_reports_snapshot_total_mismatches() -> None:
    snapshot = _snapshot(
        totals={
            "line_net": Decimal("100.00"),
            "tax": Decimal("1.00"),
            "invoice_total": Decimal("101.00"),
            "payable": Decimal("101.00"),
        }
    )

    findings = validate_math(from_snapshot(snapshot))

    assert {finding.code for finding in findings} == {
        "tax_total_mismatch",
        "invoice_total_mismatch",
        "payable_amount_mismatch",
    }
