"""Contract tests for the supported commercial document catalog."""

from backend.app.services.document_catalog import (
    DOCUMENT_CAPABILITIES,
    PLACEHOLDERS,
    TEXT_BLOCK_PURPOSES,
    DocumentType,
)


def test_all_approved_document_types_have_capabilities():
    assert set(DOCUMENT_CAPABILITIES) == set(DocumentType)
    assert DOCUMENT_CAPABILITIES[DocumentType.DELIVERY_NOTE].einvoice is False
    assert DOCUMENT_CAPABILITIES[DocumentType.INVOICE].einvoice is True
    assert DOCUMENT_CAPABILITIES[DocumentType.SELF_BILLING].issuer_role == "buyer"


def test_catalog_contains_the_complete_approved_document_type_set():
    assert {document_type.value for document_type in DocumentType} == {
        "quotation",
        "order_confirmation",
        "delivery_note",
        "advance_invoice",
        "progress_invoice",
        "final_invoice",
        "invoice",
        "cancellation_invoice",
        "invoice_correction",
        "commercial_credit_note",
        "payment_reminder",
        "dunning_notice",
        "self_billing",
    }


def test_text_purposes_and_placeholders_are_closed_contracts():
    assert set(TEXT_BLOCK_PURPOSES) == {
        "intro",
        "closing",
        "payment_terms",
        "delivery_terms",
        "tax_note",
        "footer",
        "dunning_notice",
    }
    assert {"document.number", "customer.name", "company.name"} <= set(PLACEHOLDERS)
