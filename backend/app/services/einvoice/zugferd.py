"""Deterministic Factur-X 1.09 / ZUGFeRD 2.5 CII rendering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from lxml import etree

from backend.app.schemas.einvoice import CanonicalInvoice, CanonicalParty

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

EN16931_CONTEXT = "urn:factur-x.eu:1p0:en16931"
XRECHNUNG_CONTEXT = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"


def _q(namespace: str, local_name: str) -> str:
    return etree.QName(namespace, local_name)


def _element(
    parent: etree._Element,
    namespace: str,
    local_name: str,
    value: str | None = None,
    **attributes: str,
) -> etree._Element:
    if value is not None and value == "":
        raise ValueError("Empty XML elements are forbidden")
    node = etree.SubElement(parent, _q(namespace, local_name), **attributes)
    if value is not None:
        node.text = value
    return node


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _number(value: Decimal) -> str:
    return format(value, "f")


def _date_element(parent: etree._Element, value: date) -> None:
    wrapper = _element(parent, UDT, "DateTimeString", value.strftime("%Y%m%d"), format="102")
    assert wrapper.text


def _party(parent: etree._Element, local_name: str, party: CanonicalParty) -> None:
    node = _element(parent, RAM, local_name)
    if party.registration_id:
        identifier = _element(node, RAM, "ID", party.registration_id)
        if party.registration_scheme:
            identifier.set("schemeID", party.registration_scheme)
    _element(node, RAM, "Name", party.name)

    if party.contact.name or party.contact.email or party.contact.phone:
        contact = _element(node, RAM, "DefinedTradeContact")
        if party.contact.name:
            _element(contact, RAM, "PersonName", party.contact.name)
        if party.contact.phone:
            telephone = _element(contact, RAM, "TelephoneUniversalCommunication")
            _element(telephone, RAM, "CompleteNumber", party.contact.phone)
        if party.contact.email:
            email = _element(contact, RAM, "EmailURIUniversalCommunication")
            _element(email, RAM, "URIID", party.contact.email)

    address = _element(node, RAM, "PostalTradeAddress")
    _element(address, RAM, "PostcodeCode", party.address.postal_code)
    _element(address, RAM, "LineOne", party.address.line1)
    if party.address.line2:
        _element(address, RAM, "LineTwo", party.address.line2)
    _element(address, RAM, "CityName", party.address.city)
    _element(address, RAM, "CountryID", party.address.country_code)

    if party.electronic_address:
        endpoint = _element(node, RAM, "URIUniversalCommunication")
        identifier = _element(endpoint, RAM, "URIID", party.electronic_address)
        if party.electronic_address_scheme:
            identifier.set("schemeID", party.electronic_address_scheme)

    for scheme, identifier in (("VA", party.vat_id), ("FC", party.tax_id)):
        if identifier:
            registration = _element(node, RAM, "SpecifiedTaxRegistration")
            _element(registration, RAM, "ID", identifier, schemeID=scheme)


def _render_cii(invoice: CanonicalInvoice, context: str) -> bytes:
    root = etree.Element(
        _q(RSM, "CrossIndustryInvoice"),
        nsmap={"rsm": RSM, "ram": RAM, "qdt": QDT, "udt": UDT},
    )
    context_node = _element(root, RSM, "ExchangedDocumentContext")
    if context == XRECHNUNG_CONTEXT:
        process = _element(context_node, RAM, "BusinessProcessSpecifiedDocumentContextParameter")
        _element(process, RAM, "ID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    guideline = _element(context_node, RAM, "GuidelineSpecifiedDocumentContextParameter")
    _element(guideline, RAM, "ID", context)

    document = _element(root, RSM, "ExchangedDocument")
    _element(document, RAM, "ID", invoice.invoice_number)
    _element(document, RAM, "TypeCode", invoice.type_code)
    issue = _element(document, RAM, "IssueDateTime")
    _date_element(issue, invoice.issue_date)

    transaction = _element(root, RSM, "SupplyChainTradeTransaction")
    for line in invoice.lines:
        line_item = _element(transaction, RAM, "IncludedSupplyChainTradeLineItem")
        line_document = _element(line_item, RAM, "AssociatedDocumentLineDocument")
        _element(line_document, RAM, "LineID", str(line.position))

        product = _element(line_item, RAM, "SpecifiedTradeProduct")
        if line.product_identifier:
            _element(product, RAM, "SellerAssignedID", line.product_identifier)
        _element(product, RAM, "Name", line.description)

        agreement = _element(line_item, RAM, "SpecifiedLineTradeAgreement")
        price = _element(agreement, RAM, "NetPriceProductTradePrice")
        _element(price, RAM, "ChargeAmount", _money(line.unit_price))
        _element(price, RAM, "BasisQuantity", "1", unitCode=line.unit_code)

        delivery = _element(line_item, RAM, "SpecifiedLineTradeDelivery")
        _element(
            delivery,
            RAM,
            "BilledQuantity",
            _number(line.quantity),
            unitCode=line.unit_code,
        )

        settlement = _element(line_item, RAM, "SpecifiedLineTradeSettlement")
        tax = _element(settlement, RAM, "ApplicableTradeTax")
        _element(tax, RAM, "TypeCode", "VAT")
        _element(tax, RAM, "CategoryCode", line.tax_category_code)
        _element(tax, RAM, "RateApplicablePercent", _money(line.tax_rate))
        line_totals = _element(settlement, RAM, "SpecifiedTradeSettlementLineMonetarySummation")
        _element(line_totals, RAM, "LineTotalAmount", _money(line.net_amount))

    agreement = _element(transaction, RAM, "ApplicableHeaderTradeAgreement")
    if invoice.buyer_reference:
        _element(agreement, RAM, "BuyerReference", invoice.buyer_reference)
    _party(agreement, "SellerTradeParty", invoice.seller)
    _party(agreement, "BuyerTradeParty", invoice.buyer)
    for reference in invoice.references:
        if reference.kind == "order":
            order = _element(agreement, RAM, "BuyerOrderReferencedDocument")
            _element(order, RAM, "IssuerAssignedID", reference.identifier)
            break

    if invoice.service_date:
        delivery = _element(transaction, RAM, "ApplicableHeaderTradeDelivery")
        event = _element(delivery, RAM, "ActualDeliverySupplyChainEvent")
        occurrence = _element(event, RAM, "OccurrenceDateTime")
        _date_element(occurrence, invoice.service_date)

    settlement = _element(transaction, RAM, "ApplicableHeaderTradeSettlement")
    _element(settlement, RAM, "InvoiceCurrencyCode", invoice.currency)
    payment = _element(settlement, RAM, "SpecifiedTradeSettlementPaymentMeans")
    _element(payment, RAM, "TypeCode", invoice.payment.means_code)
    if invoice.payment.iban:
        account = _element(payment, RAM, "PayeePartyCreditorFinancialAccount")
        _element(account, RAM, "IBANID", invoice.payment.iban)
        if invoice.payment.account_name:
            _element(account, RAM, "AccountName", invoice.payment.account_name)
    if invoice.payment.bic:
        institution = _element(payment, RAM, "PayeeSpecifiedCreditorFinancialInstitution")
        _element(institution, RAM, "BICID", invoice.payment.bic)

    for subtotal in invoice.tax_subtotals:
        tax = _element(settlement, RAM, "ApplicableTradeTax")
        _element(tax, RAM, "CalculatedAmount", _money(subtotal.tax_amount))
        _element(tax, RAM, "TypeCode", "VAT")
        if subtotal.exemption_reason:
            _element(tax, RAM, "ExemptionReason", subtotal.exemption_reason)
        _element(tax, RAM, "BasisAmount", _money(subtotal.taxable_amount))
        _element(tax, RAM, "CategoryCode", subtotal.category_code)
        if subtotal.exemption_reason_code:
            _element(tax, RAM, "ExemptionReasonCode", subtotal.exemption_reason_code)
        _element(tax, RAM, "RateApplicablePercent", _money(subtotal.rate))

    if invoice.service_date:
        period = _element(settlement, RAM, "BillingSpecifiedPeriod")
        start = _element(period, RAM, "StartDateTime")
        _date_element(start, invoice.service_date)
        end = _element(period, RAM, "EndDateTime")
        _date_element(end, invoice.service_date)

    if invoice.payment.terms or invoice.payment.due_date:
        terms = _element(settlement, RAM, "SpecifiedTradePaymentTerms")
        if invoice.payment.terms:
            _element(terms, RAM, "Description", invoice.payment.terms)
        if invoice.payment.due_date:
            due = _element(terms, RAM, "DueDateDateTime")
            _date_element(due, invoice.payment.due_date)

    totals = _element(settlement, RAM, "SpecifiedTradeSettlementHeaderMonetarySummation")
    _element(totals, RAM, "LineTotalAmount", _money(invoice.line_net_total))
    _element(totals, RAM, "ChargeTotalAmount", _money(invoice.charge_total))
    _element(totals, RAM, "AllowanceTotalAmount", _money(invoice.allowance_total))
    _element(
        totals,
        RAM,
        "TaxBasisTotalAmount",
        _money(invoice.line_net_total - invoice.allowance_total + invoice.charge_total),
    )
    _element(totals, RAM, "TaxTotalAmount", _money(invoice.tax_total), currencyID=invoice.currency)
    _element(totals, RAM, "GrandTotalAmount", _money(invoice.invoice_total))
    _element(totals, RAM, "TotalPrepaidAmount", _money(invoice.paid_amount))
    _element(totals, RAM, "DuePayableAmount", _money(invoice.payable_amount))

    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def render_zugferd(
    invoice: CanonicalInvoice,
    profile: Literal["en16931", "xrechnung"],
) -> bytes:
    """Render validated CII XML for embedding in a later PDF/A-3 step."""
    contexts = {"en16931": EN16931_CONTEXT, "xrechnung": XRECHNUNG_CONTEXT}
    try:
        context = contexts[profile]
    except KeyError as exc:
        raise ValueError(f"Unsupported ZUGFeRD profile: {profile}") from exc
    return _render_cii(invoice, context)
