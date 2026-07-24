from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.schemas.einvoice import (
    CanonicalAddress,
    CanonicalContact,
    CanonicalInvoice,
    CanonicalLine,
    CanonicalParty,
    CanonicalPayment,
    CanonicalReference,
    CanonicalTaxSubtotal,
)


@pytest.fixture
def canonical_invoice() -> CanonicalInvoice:
    seller = CanonicalParty(
        name="Muster & Söhne GmbH",
        address=CanonicalAddress(
            line1="Werkstraße 1",
            city="Berlin",
            postal_code="10115",
            country_code="DE",
        ),
        contact=CanonicalContact(
            name="Buchhaltung",
            email="rechnung@example.de",
            phone="+49 30 123456",
        ),
        vat_id="DE123456789",
        electronic_address="rechnung@example.de",
        electronic_address_scheme="EM",
    )
    buyer = CanonicalParty(
        name="Atelier Nord GmbH",
        address=CanonicalAddress(
            line1="Hafenweg 3",
            city="Hamburg",
            postal_code="20457",
            country_code="DE",
        ),
        contact=CanonicalContact(),
        vat_id="DE987654321",
        electronic_address="04011000-12345-34",
        electronic_address_scheme="0204",
    )
    return CanonicalInvoice(
        invoice_number="RE-2026-0001",
        type_code="380",
        issue_date=date(2026, 7, 20),
        service_date=date(2026, 7, 19),
        due_date=date(2026, 8, 3),
        currency="EUR",
        language="de-DE",
        seller=seller,
        buyer=buyer,
        buyer_reference="04011000-12345-34",
        lines=(
            CanonicalLine(
                position=1,
                description="3D-Druck Gehäuse",
                quantity=Decimal("2.000"),
                unit_code="C62",
                unit_price=Decimal("50.00"),
                net_amount=Decimal("100.00"),
                tax_category_code="S",
                tax_rate=Decimal("19.00"),
                product_identifier="CASE-01",
            ),
        ),
        tax_subtotals=(
            CanonicalTaxSubtotal(
                category_code="S",
                rate=Decimal("19.00"),
                taxable_amount=Decimal("100.00"),
                tax_amount=Decimal("19.00"),
            ),
        ),
        tax_total=Decimal("19.00"),
        line_net_total=Decimal("100.00"),
        allowance_total=Decimal("0.00"),
        charge_total=Decimal("0.00"),
        invoice_total=Decimal("119.00"),
        paid_amount=Decimal("0.00"),
        payable_amount=Decimal("119.00"),
        payment=CanonicalPayment(
            means_code="58",
            due_date=date(2026, 8, 3),
            terms="Zahlbar innerhalb von 14 Tagen netto.",
            iban="DE02120300000000202051",
            bic="BYLADEM1001",
            account_name="Muster & Söhne GmbH",
        ),
        references=(CanonicalReference(kind="order", identifier="PO-4711"),),
    )
