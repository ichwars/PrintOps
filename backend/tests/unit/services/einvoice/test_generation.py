from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import pytest

from backend.app.models.commercial_document import CommercialDocument
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot, SnapshotLine
from backend.app.services.commercial_documents import (
    EInvoiceValidationFailed,
    generate_required_artifact,
)


def _snapshot(canonical_invoice, *, required: bool = True) -> IssuedDocumentSnapshot:
    invoice = canonical_invoice
    return IssuedDocumentSnapshot(
        document_type="invoice",
        number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        service_date=invoice.service_date,
        due_date=invoice.due_date,
        language=invoice.language,
        currency=invoice.currency,
        seller=asdict(invoice.seller),
        buyer={**asdict(invoice.buyer), "buyer_reference": invoice.buyer_reference},
        lines=tuple(
            SnapshotLine(
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                unit_code=line.unit_code,
                unit_price=line.unit_price,
                net_amount=line.net_amount,
                tax_category_code=line.tax_category_code,
                tax_rate=line.tax_rate,
                product_identifier=line.product_identifier,
            )
            for line in invoice.lines
        ),
        totals={
            "line_net": invoice.line_net_total,
            "allowance": invoice.allowance_total,
            "charge": invoice.charge_total,
            "tax": invoice.tax_total,
            "invoice_total": invoice.invoice_total,
            "paid": invoice.paid_amount,
            "payable": invoice.payable_amount,
        },
        payment=asdict(invoice.payment),
        references=tuple(asdict(item) for item in invoice.references),
        metadata={
            "einvoice": {
                "required": required,
                "standard": "xrechnung",
                "syntax": "ubl_2_1",
                "profile": "xrechnung",
            }
        },
    )


@pytest.mark.asyncio
async def test_required_artifact_is_rendered_and_officially_validated(canonical_invoice):
    artifact = await generate_required_artifact(
        None,
        CommercialDocument(customer_id=1),
        _snapshot(canonical_invoice),
    )

    assert artifact is not None
    assert artifact.kind == "xrechnung_xml"
    assert artifact.validation_status == "valid"
    assert artifact.validation_report["valid"] is True
    assert artifact.rule_versions["xrechnung"] == "3.0.2-2026-01-31"


@pytest.mark.asyncio
async def test_non_required_artifact_is_not_generated(canonical_invoice):
    artifact = await generate_required_artifact(
        None,
        CommercialDocument(customer_id=1),
        _snapshot(canonical_invoice, required=False),
    )

    assert artifact is None


@pytest.mark.asyncio
async def test_math_mismatch_stops_artifact_generation(canonical_invoice):
    snapshot = _snapshot(canonical_invoice).model_copy(
        update={"totals": {**_snapshot(canonical_invoice).totals, "tax": Decimal("1.00")}}
    )

    with pytest.raises(EInvoiceValidationFailed, match="tax_total_mismatch"):
        await generate_required_artifact(None, CommercialDocument(customer_id=1), snapshot)
