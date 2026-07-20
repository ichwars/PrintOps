"""Closed domain catalog for commercial documents and their capabilities."""

from dataclasses import dataclass
from typing import Literal

from backend.app.core.compat import StrEnum


class DocumentType(StrEnum):
    """Commercial document types supported by PrintOps."""

    QUOTATION = "quotation"
    ORDER_CONFIRMATION = "order_confirmation"
    DELIVERY_NOTE = "delivery_note"
    ADVANCE_INVOICE = "advance_invoice"
    PROGRESS_INVOICE = "progress_invoice"
    FINAL_INVOICE = "final_invoice"
    INVOICE = "invoice"
    CANCELLATION_INVOICE = "cancellation_invoice"
    INVOICE_CORRECTION = "invoice_correction"
    COMMERCIAL_CREDIT_NOTE = "commercial_credit_note"
    PAYMENT_REMINDER = "payment_reminder"
    DUNNING_NOTICE = "dunning_notice"
    SELF_BILLING = "self_billing"


class EInvoiceRequirement(StrEnum):
    """Configurable E-invoice policy for capable document types."""

    OPTIONAL = "optional"
    RULE_REQUIRED = "rule_required"


@dataclass(frozen=True, slots=True)
class DocumentCapability:
    """Invariant behavior of one commercial document type."""

    einvoice: bool
    issuer_role: Literal["seller", "buyer"]
    has_payment_terms: bool
    has_tax: bool
    allowed_successors: frozenset[DocumentType]


def _successors(*document_types: DocumentType) -> frozenset[DocumentType]:
    return frozenset(document_types)


DOCUMENT_CAPABILITIES: dict[DocumentType, DocumentCapability] = {
    DocumentType.QUOTATION: DocumentCapability(
        False,
        "seller",
        True,
        True,
        _successors(DocumentType.ORDER_CONFIRMATION, DocumentType.INVOICE),
    ),
    DocumentType.ORDER_CONFIRMATION: DocumentCapability(
        False,
        "seller",
        True,
        True,
        _successors(
            DocumentType.DELIVERY_NOTE,
            DocumentType.ADVANCE_INVOICE,
            DocumentType.PROGRESS_INVOICE,
            DocumentType.FINAL_INVOICE,
            DocumentType.INVOICE,
        ),
    ),
    DocumentType.DELIVERY_NOTE: DocumentCapability(
        False,
        "seller",
        False,
        False,
        _successors(DocumentType.FINAL_INVOICE, DocumentType.INVOICE),
    ),
    DocumentType.ADVANCE_INVOICE: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(
            DocumentType.PROGRESS_INVOICE,
            DocumentType.FINAL_INVOICE,
            DocumentType.CANCELLATION_INVOICE,
            DocumentType.INVOICE_CORRECTION,
        ),
    ),
    DocumentType.PROGRESS_INVOICE: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(
            DocumentType.PROGRESS_INVOICE,
            DocumentType.FINAL_INVOICE,
            DocumentType.CANCELLATION_INVOICE,
            DocumentType.INVOICE_CORRECTION,
        ),
    ),
    DocumentType.FINAL_INVOICE: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(
            DocumentType.CANCELLATION_INVOICE,
            DocumentType.INVOICE_CORRECTION,
            DocumentType.COMMERCIAL_CREDIT_NOTE,
            DocumentType.PAYMENT_REMINDER,
            DocumentType.DUNNING_NOTICE,
        ),
    ),
    DocumentType.INVOICE: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(
            DocumentType.CANCELLATION_INVOICE,
            DocumentType.INVOICE_CORRECTION,
            DocumentType.COMMERCIAL_CREDIT_NOTE,
            DocumentType.PAYMENT_REMINDER,
            DocumentType.DUNNING_NOTICE,
        ),
    ),
    DocumentType.CANCELLATION_INVOICE: DocumentCapability(True, "seller", True, True, frozenset()),
    DocumentType.INVOICE_CORRECTION: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(DocumentType.CANCELLATION_INVOICE, DocumentType.INVOICE_CORRECTION),
    ),
    DocumentType.COMMERCIAL_CREDIT_NOTE: DocumentCapability(
        True,
        "seller",
        True,
        True,
        _successors(DocumentType.CANCELLATION_INVOICE, DocumentType.INVOICE_CORRECTION),
    ),
    DocumentType.PAYMENT_REMINDER: DocumentCapability(
        False,
        "seller",
        True,
        False,
        _successors(DocumentType.DUNNING_NOTICE),
    ),
    DocumentType.DUNNING_NOTICE: DocumentCapability(
        False,
        "seller",
        True,
        False,
        _successors(DocumentType.DUNNING_NOTICE),
    ),
    DocumentType.SELF_BILLING: DocumentCapability(
        True,
        "buyer",
        True,
        True,
        _successors(DocumentType.CANCELLATION_INVOICE, DocumentType.INVOICE_CORRECTION),
    ),
}


TEXT_BLOCK_PURPOSES = (
    "intro",
    "closing",
    "payment_terms",
    "delivery_terms",
    "tax_note",
    "footer",
    "dunning_notice",
)


PLACEHOLDERS = (
    "company.name",
    "company.address",
    "company.tax_id",
    "company.vat_id",
    "customer.name",
    "customer.number",
    "customer.address",
    "customer.email",
    "customer.vat_id",
    "document.number",
    "document.issue_date",
    "document.due_date",
    "document.service_date",
    "document.currency",
    "payment.term_days",
    "payment.discount_deadline",
    "payment.discount_percent",
    "dunning.stage",
    "dunning.fee",
    "dunning.new_due_date",
)
