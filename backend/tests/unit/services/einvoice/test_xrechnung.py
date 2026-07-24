from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree

from backend.app.services.einvoice.xrechnung import render_xrechnung

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
}
EXPECTED_ROOT = Path(__file__).parents[3] / "fixtures" / "einvoice" / "expected"


def _text(root: etree._Element, expression: str) -> str:
    result = root.xpath(f"string({expression})", namespaces=NS)
    return str(result)


def test_ubl_xrechnung_contains_endpoint_buyer_reference_and_tax_totals(
    canonical_invoice,
) -> None:
    root = etree.fromstring(render_xrechnung(canonical_invoice, "ubl"))

    assert root.nsmap[None] == "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    assert _text(root, "//cbc:CustomizationID").endswith("xrechnung_3.0")
    assert _text(root, "//cbc:BuyerReference") == "04011000-12345-34"
    assert _text(root, "//cac:AccountingSupplierParty//cbc:EndpointID") == ("rechnung@example.de")
    assert _text(root, "//cac:OrderReference/cbc:ID") == "PO-4711"
    assert _text(root, "//cac:TaxTotal/cbc:TaxAmount") == "19.00"
    assert _text(root, "//cac:LegalMonetaryTotal/cbc:PayableAmount") == "119.00"
    assert not root.xpath("//*[not(node())]")


def test_ubl_xrechnung_matches_normalized_reference_fixture(canonical_invoice) -> None:
    actual = etree.fromstring(render_xrechnung(canonical_invoice, "ubl"))
    expected = etree.parse(EXPECTED_ROOT / "xrechnung-ubl-invoice.xml").getroot()

    assert etree.tostring(actual, method="c14n") == etree.tostring(expected, method="c14n")


def test_ubl_credit_document_uses_credit_note_root_and_line(canonical_invoice) -> None:
    credit = replace(canonical_invoice, type_code="381", is_credit=True)

    root = etree.fromstring(render_xrechnung(credit, "ubl"))

    assert root.nsmap[None] == "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
    assert root.xpath("count(//cac:CreditNoteLine)", namespaces=NS) == 1.0


def test_cii_xrechnung_is_complete_and_byte_deterministic(canonical_invoice) -> None:
    first = render_xrechnung(canonical_invoice, "cii")
    second = render_xrechnung(canonical_invoice, "cii")
    root = etree.fromstring(first)

    assert first == second
    assert _text(root, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID").endswith("xrechnung_3.0")
    assert _text(root, "//ram:BuyerReference") == "04011000-12345-34"
    assert _text(root, "//ram:GrandTotalAmount") == "119.00"
    assert not root.xpath("//*[not(node())]")


def test_xrechnung_rejects_unknown_syntax(canonical_invoice) -> None:
    with pytest.raises(ValueError, match="syntax"):
        render_xrechnung(canonical_invoice, "edifact")
