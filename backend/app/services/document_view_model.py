"""Deterministic, presentation-ready semantic model for document templates."""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.schemas.document_layout import EffectiveDocumentLayout
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.document_snapshot import canonicalize_payload


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AddressView(ViewModel):
    street: str
    postal_code: str
    city: str
    country_code: str


class PartyView(ViewModel):
    name: str
    address: AddressView
    email: str | None = None
    customer_number: str | None = None
    tax_id: str | None = None
    vat_id: str | None = None


class HeaderView(ViewModel):
    document_type: str
    title: str
    number_label: str
    number: str
    issue_date_label: str
    issue_date: str
    service_date_label: str
    service_date: str | None
    due_date_label: str
    due_date: str | None


class TechnicalView(ViewModel):
    printer: str | None = None
    plate: str | None = None
    material: str | None = None
    print_time: str | None = None
    weight: str | None = None
    file_name: str | None = None


class PositionView(ViewModel):
    position: int
    description: str
    quantity: str
    unit: str
    unit_price: str
    net_amount: str
    tax_rate: str
    discount_percent: str | None
    technical: TechnicalView | None


class TaxView(ViewModel):
    category_code: str
    rate: str
    basis: str
    amount: str


class TotalsView(ViewModel):
    line_net: str
    discount: str | None
    net: str
    tax: str
    gross: str
    prepaid: str | None
    payable: str


class PaymentView(ViewModel):
    term_text: str | None
    discount_text: str | None
    iban: str | None
    bic: str | None
    account_holder: str | None
    payment_reference: str | None


class TextBlockView(ViewModel):
    purpose: str
    text: str


class FooterView(ViewModel):
    company: str
    tax: str
    bank: str
    note: str | None


class PresentationCapabilities(ViewModel):
    show_amounts: bool
    has_tax: bool
    has_payment_terms: bool
    issuer_role: Literal["seller", "buyer"]


class DocumentViewModel(ViewModel):
    schema_version: int = 1
    language: Literal["de", "en"]
    currency: str
    sender: PartyView
    recipient: PartyView
    header: HeaderView
    positions: tuple[PositionView, ...]
    taxes: tuple[TaxView, ...]
    totals: TotalsView
    payment: PaymentView
    references: tuple[str, ...]
    texts: tuple[TextBlockView, ...]
    footer: FooterView
    capabilities: PresentationCapabilities


_TITLES = {
    "quotation": ("Angebot", "Quotation"),
    "order_confirmation": ("Auftragsbestätigung", "Order confirmation"),
    "delivery_note": ("Lieferschein", "Delivery note"),
    "advance_invoice": ("Abschlagsrechnung", "Advance invoice"),
    "progress_invoice": ("Teilrechnung", "Progress invoice"),
    "final_invoice": ("Schlussrechnung", "Final invoice"),
    "invoice": ("Rechnung", "Invoice"),
    "cancellation_invoice": ("Stornorechnung", "Cancellation invoice"),
    "invoice_correction": ("Rechnungskorrektur", "Invoice correction"),
    "commercial_credit_note": ("Gutschrift", "Credit note"),
    "payment_reminder": ("Zahlungserinnerung", "Payment reminder"),
    "dunning_notice": ("Mahnung", "Dunning notice"),
    "self_billing": ("Abrechnungsgutschrift", "Self-billing invoice"),
}
_UNITS = {
    "C62": ("Stück", "pc"),
    "HUR": ("Stunde", "hour"),
    "KGM": ("kg", "kg"),
}
_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def plain_text(value: object, *, max_length: int = 4000) -> str:
    """Normalize untrusted values as text; markup remains inert template input."""
    normalized = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        char for char in normalized if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf"}
    )
    return normalized[:max_length]


def _language(language: str) -> Literal["de", "en"]:
    return "de" if language.lower().startswith("de") else "en"


def format_date(value: date | None, language: Literal["de", "en"]) -> str | None:
    if value is None:
        return None
    if language == "de":
        return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    return f"{months[value.month - 1]} {value.day}, {value.year}"


def format_number(value: Decimal, language: Literal["de", "en"], places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    rendered = f"{value.quantize(quantum, rounding=ROUND_HALF_UP):,.{places}f}"
    if language == "de":
        rendered = rendered.replace(",", "_").replace(".", ",").replace("_", ".")
    return rendered


def format_money(value: Decimal, currency: str, language: Literal["de", "en"]) -> str:
    amount = format_number(value, language)
    symbol = _CURRENCY_SYMBOLS.get(currency, currency)
    return f"{amount} {symbol}" if language == "de" else f"{symbol}{amount}"


def _party(data: dict) -> PartyView:
    address = data.get("address") if isinstance(data.get("address"), dict) else data
    contact = data.get("contact") if isinstance(data.get("contact"), dict) else data
    return PartyView(
        name=plain_text(data.get("legal_name") or data["name"]),
        address=AddressView(
            street=plain_text(address.get("street") or address.get("line1", "")),
            postal_code=plain_text(address.get("postal_code", "")),
            city=plain_text(address.get("city", "")),
            country_code=plain_text(address.get("country_code") or data.get("country_code", "")),
        ),
        email=plain_text(contact["email"]) if contact.get("email") else None,
        customer_number=(
            plain_text(data.get("customer_number") or data.get("registration_id"))
            if data.get("customer_number") or data.get("registration_id")
            else None
        ),
        tax_id=plain_text(data["tax_id"]) if data.get("tax_id") else None,
        vat_id=plain_text(data["vat_id"]) if data.get("vat_id") else None,
    )


def _technical(metadata: dict, language: Literal["de", "en"]) -> TechnicalView | None:
    data = metadata.get("technical")
    if not isinstance(data, dict):
        return None
    minutes = int(data.get("print_time_minutes", 0))
    time_text = f"{minutes // 60} h {minutes % 60} min" if minutes else None
    weight = data.get("weight_grams")
    return TechnicalView(
        printer=plain_text(data["printer"]) if data.get("printer") else None,
        plate=plain_text(data["plate"]) if data.get("plate") else None,
        material=plain_text(data["material"]) if data.get("material") else None,
        print_time=time_text,
        weight=(f"{format_number(Decimal(str(weight)), language)} g" if weight is not None else None),
        file_name=plain_text(data["file_name"]) if data.get("file_name") else None,
    )


def build_document_view_model(snapshot: IssuedDocumentSnapshot) -> DocumentViewModel:
    language = _language(snapshot.language)
    capability = DOCUMENT_CAPABILITIES[DocumentType(snapshot.document_type)]
    sender = _party(snapshot.seller)
    recipient = _party(snapshot.buyer)
    title = _TITLES[snapshot.document_type][0 if language == "de" else 1]
    labels = (
        ("Nummer", "Datum", "Leistungsdatum", "Fällig am")
        if language == "de"
        else ("Number", "Date", "Service date", "Due date")
    )
    positions = tuple(
        PositionView(
            position=line.position,
            description=plain_text(line.description),
            quantity=format_number(line.quantity, language, 3),
            unit=_UNITS.get(line.unit_code, (line.unit_code, line.unit_code))[0 if language == "de" else 1],
            unit_price=format_money(line.unit_price, snapshot.currency, language),
            net_amount=format_money(line.net_amount, snapshot.currency, language),
            tax_rate=f"{format_number(line.tax_rate, language)} %",
            discount_percent=(
                f"{format_number(Decimal(str(line.metadata['discount_percent'])), language)} %"
                if line.metadata.get("discount_percent") is not None
                else None
            ),
            technical=_technical(line.metadata, language),
        )
        for line in snapshot.lines
    )
    tax_groups: dict[tuple[str, Decimal], Decimal] = {}
    for line in snapshot.lines:
        key = (line.tax_category_code, line.tax_rate)
        tax_groups[key] = tax_groups.get(key, Decimal("0")) + line.net_amount
    taxes = (
        tuple(
            TaxView(
                category_code=category,
                rate=f"{format_number(rate, language)} %",
                basis=format_money(basis, snapshot.currency, language),
                amount=format_money(basis * rate / Decimal("100"), snapshot.currency, language),
            )
            for (category, rate), basis in sorted(tax_groups.items(), key=lambda item: (item[0][1], item[0][0]))
        )
        if capability.has_tax
        else ()
    )
    totals = snapshot.totals
    payment = snapshot.payment
    term_days = payment.get("term_days")
    discount_days = payment.get("discount_days")
    discount_percent = payment.get("discount_percent")
    footer_note = next(
        (plain_text(block.get("text", "")) for block in snapshot.text_blocks if block.get("purpose") == "footer"),
        None,
    )
    return DocumentViewModel(
        language=language,
        currency=snapshot.currency,
        sender=sender,
        recipient=recipient,
        header=HeaderView(
            document_type=snapshot.document_type,
            title=title,
            number_label=labels[0],
            number=plain_text(snapshot.number),
            issue_date_label=labels[1],
            issue_date=format_date(snapshot.issue_date, language) or "",
            service_date_label=labels[2],
            service_date=format_date(snapshot.service_date, language),
            due_date_label=labels[3],
            due_date=format_date(snapshot.due_date, language),
        ),
        positions=positions,
        taxes=taxes,
        totals=TotalsView(
            line_net=format_money(totals.get("line_net", Decimal("0")), snapshot.currency, language),
            discount=(format_money(totals["discount"], snapshot.currency, language) if "discount" in totals else None),
            net=format_money(totals.get("net", totals.get("line_net", Decimal("0"))), snapshot.currency, language),
            tax=format_money(totals.get("tax", Decimal("0")), snapshot.currency, language),
            gross=format_money(totals.get("gross", totals.get("payable", Decimal("0"))), snapshot.currency, language),
            prepaid=(format_money(totals["prepaid"], snapshot.currency, language) if "prepaid" in totals else None),
            payable=format_money(totals.get("payable", Decimal("0")), snapshot.currency, language),
        ),
        payment=PaymentView(
            term_text=(
                f"Zahlbar innerhalb von {term_days} Tagen."
                if capability.has_payment_terms and language == "de" and term_days
                else f"Payable within {term_days} days."
                if capability.has_payment_terms and term_days
                else None
            ),
            discount_text=(
                f"{format_number(Decimal(str(discount_percent)), language)} % Skonto bei Zahlung innerhalb von {discount_days} Tagen."
                if capability.has_payment_terms and language == "de" and discount_percent is not None and discount_days
                else f"{format_number(Decimal(str(discount_percent)), language)}% discount for payment within {discount_days} days."
                if capability.has_payment_terms and discount_percent is not None and discount_days
                else None
            ),
            iban=plain_text(payment["iban"]) if payment.get("iban") else None,
            bic=plain_text(payment["bic"]) if payment.get("bic") else None,
            account_holder=(
                plain_text(payment.get("account_holder") or payment.get("account_name"))
                if payment.get("account_holder") or payment.get("account_name")
                else None
            ),
            payment_reference=plain_text(payment["payment_reference"]) if payment.get("payment_reference") else None,
        ),
        references=tuple(
            f"{plain_text(reference.get('type') or reference.get('kind', 'reference'))}: {plain_text(reference.get('value') or reference.get('identifier', ''))}"
            for reference in snapshot.references
        ),
        texts=tuple(
            TextBlockView(
                purpose=plain_text(block.get("purpose", "note")),
                text=plain_text(block.get("text") or block.get("body", "")),
            )
            for block in snapshot.text_blocks
        ),
        footer=FooterView(
            company=f"{sender.name} · {sender.address.street}",
            tax=" · ".join(filter(None, (sender.tax_id, sender.vat_id))),
            bank=" · ".join(filter(None, (payment.get("iban"), payment.get("bic")))),
            note=footer_note,
        ),
        capabilities=PresentationCapabilities(
            show_amounts=snapshot.document_type != "delivery_note",
            has_tax=capability.has_tax,
            has_payment_terms=capability.has_payment_terms,
            issuer_role=capability.issuer_role,
        ),
    )


def canonicalize_view_model(view_model: DocumentViewModel) -> bytes:
    return canonicalize_payload(view_model)


def render_context_sha256(
    view_model: DocumentViewModel,
    layout: EffectiveDocumentLayout,
    asset_receipts: dict,
) -> str:
    return hashlib.sha256(
        canonicalize_payload(
            {
                "view_model": view_model,
                "layout": layout,
                "asset_receipts": asset_receipts,
            }
        )
    ).hexdigest()
