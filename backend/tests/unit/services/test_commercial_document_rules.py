from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.schemas.commercial_document import (
    CommercialDocumentDraft,
    CommercialDocumentLineDraft,
)
from backend.app.services.commercial_documents import validate_document


def _line(*, net: str = "100.00", tax_rate: str = "19.00") -> CommercialDocumentLineDraft:
    return CommercialDocumentLineDraft(
        position=1,
        description="3D-Druck",
        quantity=Decimal("1.000"),
        unit_code="C62",
        unit_price=Decimal(net),
        net_amount=Decimal(net),
        tax_category_code="S",
        tax_rate=Decimal(tax_rate),
    )


def _draft(document_type: str, **updates) -> CommercialDocumentDraft:
    values = {
        "document_type": document_type,
        "business_profile_id": 1,
        "customer_id": None,
        "language": "de-DE",
        "currency": "EUR",
        "lines": (_line(),),
        "content_options": {},
    }
    values.update(updates)
    return CommercialDocumentDraft(**values)


def test_delivery_note_rejects_prices_and_internal_calculation():
    draft = _draft(
        "delivery_note",
        content_options={"show_prices": True, "include_internal_calculation": True},
    )

    findings = validate_document(draft)

    assert {item.code for item in findings} == {
        "delivery_prices_forbidden",
        "internal_calculation_forbidden",
    }


def test_final_invoice_requires_prior_payment_deductions_by_tax_group():
    draft = _draft(
        "final_invoice",
        content_options={
            "prior_invoices": [{"document_id": 10, "tax_category_code": "S", "tax_rate": "19.00", "gross": "119.00"}],
            "prior_payment_deductions": [],
        },
    )

    findings = validate_document(draft)

    assert any(item.code == "prior_payment_deduction_missing" for item in findings)


def test_reminder_has_no_vat_and_requires_invoice_balance_reference():
    draft = _draft(
        "payment_reminder",
        lines=(_line(net="10.00"),),
        content_options={"invoice_balance": "10.00"},
    )

    findings = validate_document(draft)

    assert {item.code for item in findings} == {
        "reminder_invoice_reference_missing",
        "reminder_vat_forbidden",
    }


def test_self_billing_requires_external_issuer_number_and_buyer_role():
    findings = validate_document(_draft("self_billing"))

    assert {item.code for item in findings} == {
        "self_billing_external_number_missing",
        "self_billing_issuer_role_invalid",
    }


def test_complete_final_invoice_deductions_match_tax_groups():
    draft = _draft(
        "final_invoice",
        content_options={
            "prior_invoices": [{"document_id": 10, "tax_category_code": "S", "tax_rate": "19.00", "gross": "119.00"}],
            "prior_payment_deductions": [
                {"document_id": 10, "tax_category_code": "S", "tax_rate": "19.00", "gross": "119.00"}
            ],
        },
    )

    assert validate_document(draft) == ()


def test_document_draft_rejects_duplicate_line_positions():
    with pytest.raises(ValidationError, match="line positions"):
        _draft("invoice", lines=(_line(), _line()))
