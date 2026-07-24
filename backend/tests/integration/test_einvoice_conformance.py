from __future__ import annotations

from dataclasses import replace
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
    CanonicalTaxSubtotal,
)
from backend.app.services.einvoice.validator import validate_xml
from backend.app.services.einvoice.xrechnung import render_xrechnung
from backend.app.services.einvoice.zugferd import render_zugferd


@pytest.fixture
def conformance_invoice() -> CanonicalInvoice:
    return CanonicalInvoice(
        invoice_number="RE-2026-0042",
        type_code="380",
        issue_date=date(2026, 7, 22),
        service_date=date(2026, 7, 21),
        due_date=date(2026, 8, 5),
        currency="EUR",
        language="de-DE",
        seller=CanonicalParty(
            name="PrintOps GmbH",
            address=CanonicalAddress(line1="Werkstraße 1", city="Berlin", postal_code="10115", country_code="DE"),
            contact=CanonicalContact(name="Buchhaltung", email="rechnung@printops.example", phone="+49 30 123456"),
            vat_id="DE123456789",
            electronic_address="rechnung@printops.example",
            electronic_address_scheme="EM",
        ),
        buyer=CanonicalParty(
            name="Bundesbehörde Nord",
            address=CanonicalAddress(line1="Hafenweg 3", city="Hamburg", postal_code="20457", country_code="DE"),
            contact=CanonicalContact(),
            electronic_address="04011000-12345-34",
            electronic_address_scheme="0204",
        ),
        buyer_reference="04011000-12345-34",
        lines=(CanonicalLine(position=1, description="3D-Druck", quantity=Decimal("1"), unit_code="C62", unit_price=Decimal("100"), net_amount=Decimal("100"), tax_category_code="S", tax_rate=Decimal("19")),),
        tax_subtotals=(CanonicalTaxSubtotal(category_code="S", rate=Decimal("19"), taxable_amount=Decimal("100"), tax_amount=Decimal("19")),),
        tax_total=Decimal("19"),
        line_net_total=Decimal("100"),
        allowance_total=Decimal("0"),
        charge_total=Decimal("0"),
        invoice_total=Decimal("119"),
        paid_amount=Decimal("0"),
        payable_amount=Decimal("119"),
        payment=CanonicalPayment(means_code="58", due_date=date(2026, 8, 5), terms="Zahlbar binnen 14 Tagen.", iban="DE02120300000000202051", bic="BYLADEM1001", account_name="PrintOps GmbH"),
        references=(),
    )


@pytest.mark.parametrize(
    ("standard", "syntax", "profile", "renderer"),
    [
        ("xrechnung", "ubl-2.1", "xrechnung", lambda invoice: render_xrechnung(invoice, "ubl")),
        ("xrechnung", "cii-d16b", "xrechnung", lambda invoice: render_xrechnung(invoice, "cii")),
        ("zugferd", "cii-d22b", "en16931", lambda invoice: render_zugferd(invoice, "en16931")),
        ("zugferd", "cii-d22b", "xrechnung", lambda invoice: render_zugferd(invoice, "xrechnung")),
    ],
)
def test_generated_xml_conforms_to_pinned_official_rules(
    conformance_invoice, standard, syntax, profile, renderer
):
    xml = renderer(conformance_invoice)
    report = validate_xml(xml, standard, syntax, profile)

    assert report.valid, report.to_dict()
    assert report.rule_versions["en16931"] == "1.3.16"
    if profile == "xrechnung":
        assert report.rule_versions["xrechnung"] == "3.0.2-2026-01-31"
    if standard == "zugferd":
        assert report.rule_versions["zugferd"] == "2.5"


def test_xrechnung_b2g_buyer_reference_is_a_blocking_business_rule(conformance_invoice):
    xml = render_xrechnung(replace(conformance_invoice, buyer_reference=None), "ubl")

    report = validate_xml(xml, "xrechnung", "ubl-2.1", "xrechnung")

    assert report.valid is False
    assert "BR-DE-15" in {finding.rule_id for finding in report.blockers}
    assert {finding.field_path for finding in report.blockers if finding.rule_id == "BR-DE-15"} == {
        "buyer.reference"
    }


def test_conformance_output_is_byte_deterministic(conformance_invoice):
    assert render_xrechnung(conformance_invoice, "ubl") == render_xrechnung(conformance_invoice, "ubl")
    assert render_zugferd(conformance_invoice, "en16931") == render_zugferd(conformance_invoice, "en16931")
