from __future__ import annotations

from dataclasses import replace

import pytest
from lxml import etree

from backend.app.services.einvoice.zugferd import render_zugferd

NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}


def test_zugferd_25_uses_d22b_context_and_has_no_empty_elements(
    canonical_invoice,
) -> None:
    xml = render_zugferd(canonical_invoice, "en16931")
    root = etree.fromstring(xml)

    assert b"urn:cen.eu:en16931:2017" in xml
    assert b"CrossIndustryInvoice:100" in xml
    assert (
        root.xpath(
            "string(//ram:ApplicableHeaderTradeSettlement/ram:InvoiceCurrencyCode)",
            namespaces=NS,
        )
        == "EUR"
    )
    assert (
        root.xpath(
            "string(//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:DuePayableAmount)",
            namespaces=NS,
        )
        == "119.00"
    )
    assert not root.xpath("//*[not(node())]")


def test_zugferd_xrechnung_profile_uses_german_cius(canonical_invoice) -> None:
    xml = render_zugferd(canonical_invoice, "xrechnung")

    assert b"urn:xeinkauf.de:kosit:xrechnung_3.0" in xml


def test_zugferd_omits_absent_optional_delivery_data(canonical_invoice) -> None:
    invoice = replace(canonical_invoice, service_date=None)

    root = etree.fromstring(render_zugferd(invoice, "en16931"))

    assert not root.xpath("//*[not(node())]")


def test_zugferd_rejects_unknown_profile(canonical_invoice) -> None:
    with pytest.raises(ValueError, match="profile"):
        render_zugferd(canonical_invoice, "basic")
