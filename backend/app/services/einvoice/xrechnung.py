"""Deterministic XRechnung 3.0.2 UBL and CII rendering."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from lxml import etree

from backend.app.schemas.einvoice import CanonicalInvoice, CanonicalParty
from backend.app.services.einvoice.zugferd import XRECHNUNG_CONTEXT, _render_cii

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


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


def _party(parent: etree._Element, local_name: str, party: CanonicalParty) -> None:
    wrapper = _element(parent, CAC, local_name)
    node = _element(wrapper, CAC, "Party")
    if not party.electronic_address or not party.electronic_address_scheme:
        raise ValueError("XRechnung seller and buyer electronic endpoints are required")
    _element(
        node,
        CBC,
        "EndpointID",
        party.electronic_address,
        schemeID=party.electronic_address_scheme,
    )
    if party.registration_id:
        identification = _element(node, CAC, "PartyIdentification")
        identifier = _element(identification, CBC, "ID", party.registration_id)
        if party.registration_scheme:
            identifier.set("schemeID", party.registration_scheme)
    name = _element(node, CAC, "PartyName")
    _element(name, CBC, "Name", party.name)
    address = _element(node, CAC, "PostalAddress")
    _element(address, CBC, "StreetName", party.address.line1)
    if party.address.line2:
        _element(address, CBC, "AdditionalStreetName", party.address.line2)
    _element(address, CBC, "CityName", party.address.city)
    _element(address, CBC, "PostalZone", party.address.postal_code)
    country = _element(address, CAC, "Country")
    _element(country, CBC, "IdentificationCode", party.address.country_code)
    for identifier, scheme in ((party.vat_id, "VAT"), (party.tax_id, "FC")):
        if identifier:
            tax_scheme = _element(node, CAC, "PartyTaxScheme")
            _element(tax_scheme, CBC, "CompanyID", identifier)
            scheme_node = _element(tax_scheme, CAC, "TaxScheme")
            _element(scheme_node, CBC, "ID", scheme)
    legal = _element(node, CAC, "PartyLegalEntity")
    _element(legal, CBC, "RegistrationName", party.name)
    if party.registration_id:
        _element(legal, CBC, "CompanyID", party.registration_id)
    if party.contact.name or party.contact.email or party.contact.phone:
        contact = _element(node, CAC, "Contact")
        if party.contact.name:
            _element(contact, CBC, "Name", party.contact.name)
        if party.contact.phone:
            _element(contact, CBC, "Telephone", party.contact.phone)
        if party.contact.email:
            _element(contact, CBC, "ElectronicMail", party.contact.email)


def _render_ubl(invoice: CanonicalInvoice) -> bytes:
    root_namespace = CREDIT_NOTE if invoice.is_credit else INVOICE
    root_name = "CreditNote" if invoice.is_credit else "Invoice"
    root = etree.Element(
        _q(root_namespace, root_name),
        nsmap={None: root_namespace, "cac": CAC, "cbc": CBC},
    )
    _element(root, CBC, "CustomizationID", XRECHNUNG_CONTEXT)
    _element(root, CBC, "ProfileID", PROFILE_ID)
    _element(root, CBC, "ID", invoice.invoice_number)
    _element(root, CBC, "IssueDate", invoice.issue_date.isoformat())
    if invoice.due_date and not invoice.is_credit:
        _element(root, CBC, "DueDate", invoice.due_date.isoformat())
    _element(
        root,
        CBC,
        "CreditNoteTypeCode" if invoice.is_credit else "InvoiceTypeCode",
        invoice.type_code,
    )
    _element(root, CBC, "DocumentCurrencyCode", invoice.currency)
    if invoice.buyer_reference:
        _element(root, CBC, "BuyerReference", invoice.buyer_reference)
    for reference in invoice.references:
        if reference.kind == "order":
            order = _element(root, CAC, "OrderReference")
            _element(order, CBC, "ID", reference.identifier)
            if reference.issue_date:
                _element(order, CBC, "IssueDate", reference.issue_date.isoformat())
            break

    _party(root, "AccountingSupplierParty", invoice.seller)
    _party(root, "AccountingCustomerParty", invoice.buyer)

    if invoice.service_date:
        delivery = _element(root, CAC, "Delivery")
        _element(delivery, CBC, "ActualDeliveryDate", invoice.service_date.isoformat())

    payment = _element(root, CAC, "PaymentMeans")
    _element(payment, CBC, "PaymentMeansCode", invoice.payment.means_code)
    if invoice.payment.due_date:
        _element(payment, CBC, "PaymentDueDate", invoice.payment.due_date.isoformat())
    if invoice.payment.iban:
        account = _element(payment, CAC, "PayeeFinancialAccount")
        _element(account, CBC, "ID", invoice.payment.iban)
        if invoice.payment.account_name:
            _element(account, CBC, "Name", invoice.payment.account_name)
        if invoice.payment.bic:
            branch = _element(account, CAC, "FinancialInstitutionBranch")
            _element(branch, CBC, "ID", invoice.payment.bic)
    if invoice.payment.terms:
        terms = _element(root, CAC, "PaymentTerms")
        _element(terms, CBC, "Note", invoice.payment.terms)

    tax_total = _element(root, CAC, "TaxTotal")
    _element(tax_total, CBC, "TaxAmount", _money(invoice.tax_total), currencyID=invoice.currency)
    for subtotal in invoice.tax_subtotals:
        subtotal_node = _element(tax_total, CAC, "TaxSubtotal")
        _element(
            subtotal_node,
            CBC,
            "TaxableAmount",
            _money(subtotal.taxable_amount),
            currencyID=invoice.currency,
        )
        _element(
            subtotal_node,
            CBC,
            "TaxAmount",
            _money(subtotal.tax_amount),
            currencyID=invoice.currency,
        )
        category = _element(subtotal_node, CAC, "TaxCategory")
        _element(category, CBC, "ID", subtotal.category_code)
        _element(category, CBC, "Percent", _money(subtotal.rate))
        if subtotal.exemption_reason_code:
            _element(category, CBC, "TaxExemptionReasonCode", subtotal.exemption_reason_code)
        if subtotal.exemption_reason:
            _element(category, CBC, "TaxExemptionReason", subtotal.exemption_reason)
        scheme = _element(category, CAC, "TaxScheme")
        _element(scheme, CBC, "ID", "VAT")

    totals = _element(root, CAC, "LegalMonetaryTotal")
    _element(totals, CBC, "LineExtensionAmount", _money(invoice.line_net_total), currencyID=invoice.currency)
    tax_exclusive = invoice.line_net_total - invoice.allowance_total + invoice.charge_total
    _element(totals, CBC, "TaxExclusiveAmount", _money(tax_exclusive), currencyID=invoice.currency)
    _element(totals, CBC, "TaxInclusiveAmount", _money(invoice.invoice_total), currencyID=invoice.currency)
    if invoice.allowance_total:
        _element(totals, CBC, "AllowanceTotalAmount", _money(invoice.allowance_total), currencyID=invoice.currency)
    if invoice.charge_total:
        _element(totals, CBC, "ChargeTotalAmount", _money(invoice.charge_total), currencyID=invoice.currency)
    if invoice.paid_amount:
        _element(totals, CBC, "PrepaidAmount", _money(invoice.paid_amount), currencyID=invoice.currency)
    _element(totals, CBC, "PayableAmount", _money(invoice.payable_amount), currencyID=invoice.currency)

    line_name = "CreditNoteLine" if invoice.is_credit else "InvoiceLine"
    quantity_name = "CreditedQuantity" if invoice.is_credit else "InvoicedQuantity"
    for line in invoice.lines:
        line_node = _element(root, CAC, line_name)
        _element(line_node, CBC, "ID", str(line.position))
        _element(
            line_node,
            CBC,
            quantity_name,
            format(line.quantity, "f"),
            unitCode=line.unit_code,
        )
        _element(
            line_node,
            CBC,
            "LineExtensionAmount",
            _money(line.net_amount),
            currencyID=invoice.currency,
        )
        item = _element(line_node, CAC, "Item")
        _element(item, CBC, "Name", line.description)
        if line.product_identifier:
            seller_id = _element(item, CAC, "SellersItemIdentification")
            _element(seller_id, CBC, "ID", line.product_identifier)
        tax_category = _element(item, CAC, "ClassifiedTaxCategory")
        _element(tax_category, CBC, "ID", line.tax_category_code)
        _element(tax_category, CBC, "Percent", _money(line.tax_rate))
        scheme = _element(tax_category, CAC, "TaxScheme")
        _element(scheme, CBC, "ID", "VAT")
        price = _element(line_node, CAC, "Price")
        _element(price, CBC, "PriceAmount", _money(line.unit_price), currencyID=invoice.currency)
        _element(price, CBC, "BaseQuantity", "1", unitCode=line.unit_code)

    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def render_xrechnung(
    invoice: CanonicalInvoice,
    syntax: Literal["ubl", "cii"],
) -> bytes:
    if syntax == "ubl":
        return _render_ubl(invoice)
    if syntax == "cii":
        return _render_cii(invoice, XRECHNUNG_CONTEXT)
    raise ValueError(f"Unsupported XRechnung syntax: {syntax}")
