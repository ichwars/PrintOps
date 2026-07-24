"""Immutable semantic contracts shared by all E-invoice syntaxes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class EInvoiceFinding:
    code: str
    message: str
    path: str
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True, slots=True)
class CanonicalContact:
    name: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalAddress:
    line1: str
    city: str
    postal_code: str
    country_code: str
    line2: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalParty:
    name: str
    address: CanonicalAddress
    contact: CanonicalContact
    vat_id: str | None = None
    tax_id: str | None = None
    registration_id: str | None = None
    registration_scheme: str | None = None
    electronic_address: str | None = None
    electronic_address_scheme: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalLine:
    position: int
    description: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    net_amount: Decimal
    tax_category_code: str
    tax_rate: Decimal
    product_identifier: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalTaxSubtotal:
    category_code: str
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    exemption_reason_code: str | None = None
    exemption_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalPayment:
    means_code: str
    due_date: date | None = None
    terms: str | None = None
    iban: str | None = None
    bic: str | None = None
    account_name: str | None = None
    mandate_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalReference:
    kind: str
    identifier: str
    issue_date: date | None = None


@dataclass(frozen=True, slots=True)
class CanonicalInvoice:
    invoice_number: str
    type_code: str
    issue_date: date
    currency: str
    language: str
    seller: CanonicalParty
    buyer: CanonicalParty
    lines: tuple[CanonicalLine, ...]
    tax_subtotals: tuple[CanonicalTaxSubtotal, ...]
    tax_total: Decimal
    line_net_total: Decimal
    allowance_total: Decimal
    charge_total: Decimal
    invoice_total: Decimal
    paid_amount: Decimal
    payable_amount: Decimal
    payment: CanonicalPayment
    references: tuple[CanonicalReference, ...]
    service_date: date | None = None
    due_date: date | None = None
    buyer_reference: str | None = None
    is_credit: bool = False
    is_self_billed: bool = False
