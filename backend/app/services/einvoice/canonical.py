"""Map immutable issued snapshots to one syntax-neutral EN-16931 model."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.schemas.einvoice import (
    CanonicalAddress,
    CanonicalContact,
    CanonicalInvoice,
    CanonicalLine,
    CanonicalParty,
    CanonicalPayment,
    CanonicalReference,
    CanonicalTaxSubtotal,
    EInvoiceFinding,
)

_MONEY = Decimal("0.01")
_TYPE_CODES: dict[str, tuple[str, bool, bool]] = {
    "advance_invoice": ("386", False, False),
    "progress_invoice": ("386", False, False),
    "final_invoice": ("380", False, False),
    "invoice": ("380", False, False),
    "invoice_correction": ("384", False, False),
    "cancellation_invoice": ("381", True, False),
    "commercial_credit_note": ("381", True, False),
    "self_billing": ("389", False, True),
}


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required(value: Any, field: str) -> str:
    normalized = _optional(value)
    if normalized is None:
        raise ValueError(f"{field} is required")
    return normalized


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _iso_alpha(value: str, length: int, label: str) -> str:
    normalized = value.strip().upper()
    if not re.fullmatch(rf"[A-Z]{{{length}}}", normalized):
        raise ValueError(f"{label} code is required")
    return normalized


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _party(payload: dict[str, Any], role: str) -> CanonicalParty:
    address_data = payload.get("address") or payload
    country_code = _iso_alpha(
        _required(address_data.get("country_code"), f"{role}.address.country_code"),
        2,
        "ISO 3166-1 alpha-2",
    )
    contact_data = payload.get("contact") or {}
    return CanonicalParty(
        name=_required(payload.get("name") or payload.get("legal_name"), f"{role}.name"),
        address=CanonicalAddress(
            line1=_required(
                address_data.get("line1") or address_data.get("street"),
                f"{role}.address.line1",
            ),
            line2=_optional(address_data.get("line2")),
            city=_required(address_data.get("city"), f"{role}.address.city"),
            postal_code=_required(
                address_data.get("postal_code") or address_data.get("postcode"),
                f"{role}.address.postal_code",
            ),
            country_code=country_code,
        ),
        contact=CanonicalContact(
            name=_optional(contact_data.get("name")),
            email=_optional(contact_data.get("email")),
            phone=_optional(contact_data.get("phone")),
        ),
        vat_id=_optional(payload.get("vat_id")),
        tax_id=_optional(payload.get("tax_id")),
        registration_id=_optional(payload.get("registration_id")),
        registration_scheme=_optional(payload.get("registration_scheme")),
        electronic_address=_optional(payload.get("electronic_address")),
        electronic_address_scheme=_optional(payload.get("electronic_address_scheme")),
    )


def _payment(payload: dict[str, Any], due_date: date | None) -> CanonicalPayment:
    return CanonicalPayment(
        means_code=_required(payload.get("means_code"), "payment.means_code"),
        due_date=_date(payload.get("due_date")) or due_date,
        terms=_optional(payload.get("terms")),
        iban=_optional(payload.get("iban")),
        bic=_optional(payload.get("bic")),
        account_name=_optional(payload.get("account_name")),
        mandate_reference=_optional(payload.get("mandate_reference")),
    )


def _references(payloads: tuple[dict[str, Any], ...]) -> tuple[CanonicalReference, ...]:
    return tuple(
        CanonicalReference(
            kind=_required(item.get("kind"), "reference.kind"),
            identifier=_required(item.get("identifier"), "reference.identifier"),
            issue_date=_date(item.get("issue_date")),
        )
        for item in payloads
    )


def from_snapshot(snapshot: IssuedDocumentSnapshot) -> CanonicalInvoice:
    """Create the deterministic semantic model from issued evidence only."""
    try:
        type_code, is_credit, is_self_billed = _TYPE_CODES[snapshot.document_type]
    except KeyError as exc:
        raise ValueError(f"Document type {snapshot.document_type!r} is not E-invoice capable") from exc

    currency = _iso_alpha(snapshot.currency, 3, "ISO 4217")
    lines = tuple(
        CanonicalLine(
            position=line.position,
            description=line.description,
            quantity=line.quantity,
            unit_code=_required(line.unit_code, "line.unit_code").upper(),
            unit_price=line.unit_price,
            net_amount=_money(line.net_amount),
            tax_category_code=_required(line.tax_category_code, "line.tax_category_code").upper(),
            tax_rate=_money(line.tax_rate),
            product_identifier=_optional(line.product_identifier),
        )
        for line in sorted(snapshot.lines, key=lambda item: item.position)
    )

    grouped: dict[tuple[str, Decimal], Decimal] = defaultdict(lambda: Decimal("0"))
    for line in lines:
        grouped[(line.tax_category_code, line.tax_rate)] += line.net_amount
    tax_decision = snapshot.metadata.get("tax_decision")
    if not isinstance(tax_decision, dict):
        tax_decision = {}
    exemption_reason_code = _optional(
        snapshot.metadata.get("tax_exemption_code") or tax_decision.get("exemption_reason_code")
    )
    exemption_reason = _optional(snapshot.metadata.get("tax_exemption_reason") or tax_decision.get("exemption_reason"))
    tax_subtotals = tuple(
        CanonicalTaxSubtotal(
            category_code=category,
            rate=rate,
            taxable_amount=_money(taxable),
            tax_amount=_money(taxable * rate / Decimal("100")),
            exemption_reason_code=exemption_reason_code,
            exemption_reason=exemption_reason,
        )
        for (category, rate), taxable in sorted(grouped.items(), key=lambda item: item[0])
    )

    totals = snapshot.totals
    derived_line_net = _money(sum((line.net_amount for line in lines), Decimal("0")))
    derived_tax = _money(sum((item.tax_amount for item in tax_subtotals), Decimal("0")))
    line_net = _money(totals.get("line_net", derived_line_net))
    allowance = _money(totals.get("allowance", Decimal("0")))
    charge = _money(totals.get("charge", Decimal("0")))
    tax_total = _money(totals.get("tax", derived_tax))
    invoice_total = _money(totals.get("invoice_total", line_net - allowance + charge + tax_total))
    paid = _money(totals.get("paid", Decimal("0")))
    payable = _money(totals.get("payable", invoice_total - paid))

    return CanonicalInvoice(
        invoice_number=snapshot.number,
        type_code=type_code,
        issue_date=snapshot.issue_date,
        service_date=snapshot.service_date,
        due_date=snapshot.due_date,
        currency=currency,
        language=snapshot.language,
        seller=_party(snapshot.seller, "seller"),
        buyer=_party(snapshot.buyer, "buyer"),
        buyer_reference=_optional(snapshot.buyer.get("buyer_reference")),
        lines=lines,
        tax_subtotals=tax_subtotals,
        tax_total=tax_total,
        line_net_total=line_net,
        allowance_total=allowance,
        charge_total=charge,
        invoice_total=invoice_total,
        paid_amount=paid,
        payable_amount=payable,
        payment=_payment(snapshot.payment, snapshot.due_date),
        references=_references(snapshot.references),
        is_credit=is_credit,
        is_self_billed=is_self_billed,
    )


def validate_math(invoice: CanonicalInvoice) -> tuple[EInvoiceFinding, ...]:
    """Validate declared totals against independently recomputed EN-16931 totals."""
    findings: list[EInvoiceFinding] = []
    calculated_line_net = _money(sum((line.net_amount for line in invoice.lines), Decimal("0")))
    calculated_tax = _money(sum((subtotal.tax_amount for subtotal in invoice.tax_subtotals), Decimal("0")))
    calculated_invoice_total = _money(
        calculated_line_net - invoice.allowance_total + invoice.charge_total + calculated_tax
    )
    calculated_payable = _money(calculated_invoice_total - invoice.paid_amount)

    comparisons = (
        (
            "line_net_total_mismatch",
            "Line net total does not equal the sum of invoice lines",
            "line_net_total",
            invoice.line_net_total,
            calculated_line_net,
        ),
        (
            "tax_total_mismatch",
            "Tax total does not equal the sum of tax subtotals",
            "tax_total",
            invoice.tax_total,
            calculated_tax,
        ),
        (
            "invoice_total_mismatch",
            "Invoice total does not equal net total plus tax and charges less allowances",
            "invoice_total",
            invoice.invoice_total,
            calculated_invoice_total,
        ),
        (
            "payable_amount_mismatch",
            "Payable amount does not equal invoice total less paid amount",
            "payable_amount",
            invoice.payable_amount,
            calculated_payable,
        ),
    )
    for code, message, path, declared, calculated in comparisons:
        if declared != calculated:
            findings.append(
                EInvoiceFinding(
                    code=code,
                    message=f"{message}: declared {declared}, calculated {calculated}",
                    path=path,
                )
            )
    return tuple(findings)
