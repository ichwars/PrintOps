from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, CommercialDocumentLine
from backend.app.schemas.commercial_document import (
    CommercialDocumentDraft,
    CommercialDocumentLineDraft,
)
from backend.app.services.commercial_documents import (
    InvalidDocumentTransition,
    cancel_document,
    correct_document,
    create_draft,
    create_successor,
    mark_ready,
    transition_document,
    update_draft,
)


def _line(description: str = "Bauteil") -> CommercialDocumentLineDraft:
    return CommercialDocumentLineDraft(
        position=1,
        description=description,
        quantity=Decimal("1.000"),
        unit_code="C62",
        unit_price=Decimal("100.00"),
        net_amount=Decimal("100.00"),
        tax_category_code="S",
        tax_rate=Decimal("19.00"),
    )


async def _profile(db_session) -> BusinessProfile:
    profile = BusinessProfile(
        name="Lifecycle profile",
        legal_name="Lifecycle GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


def _draft(profile_id: int, document_type: str = "invoice") -> CommercialDocumentDraft:
    return CommercialDocumentDraft(
        document_type=document_type,
        business_profile_id=profile_id,
        language="de-DE",
        currency="EUR",
        lines=(_line(),),
    )


@pytest.mark.asyncio
async def test_draft_update_validation_and_ready_transition(db_session):
    profile = await _profile(db_session)
    document = await create_draft(db_session, _draft(profile.id), actor_id=None)
    updated = _draft(profile.id).model_copy(update={"lines": (_line("Geändertes Bauteil"),)})

    await update_draft(db_session, document.id, document.lock_version, updated)
    await mark_ready(db_session, document.id, document.lock_version)
    await db_session.flush()

    assert document.technical_status == "ready"
    assert document.lines[0].description == "Geändertes Bauteil"
    assert document.lock_version == 3


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected(db_session):
    profile = await _profile(db_session)
    document = await create_draft(db_session, _draft(profile.id), actor_id=None)

    with pytest.raises(InvalidDocumentTransition):
        await transition_document(db_session, document, "issued")


@pytest.mark.asyncio
async def test_successor_must_be_allowed_by_document_catalog(db_session):
    profile = await _profile(db_session)
    quotation = CommercialDocument(
        document_type="quotation",
        business_profile_id=profile.id,
        number="AG-2026-0001",
        technical_status="issued",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(quotation)
    await db_session.flush()

    successor = await create_successor(
        db_session,
        quotation.id,
        "order_confirmation",
        actor_id=None,
    )
    with pytest.raises(ValueError, match="not an allowed successor"):
        await create_successor(db_session, quotation.id, "dunning_notice", actor_id=None)

    assert successor.document_type == "order_confirmation"
    assert successor.incoming_relations[0].source_document_id == quotation.id
    assert successor.incoming_relations[0].relation_data == {"document_number": "AG-2026-0001"}


@pytest.mark.asyncio
async def test_correction_creates_new_document_and_preserves_original(db_session):
    profile = await _profile(db_session)
    issued = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0001",
        technical_status="issued",
        language="de-DE",
        currency="EUR",
        subtotal_amount=Decimal("100.00"),
        tax_amount=Decimal("19.00"),
        total_amount=Decimal("119.00"),
        open_amount=Decimal("119.00"),
    )
    db_session.add(issued)
    await db_session.flush()

    correction = await correct_document(
        db_session,
        issued.id,
        reason="Quantity corrected",
        actor_id=None,
    )
    await db_session.flush()

    assert correction.id != issued.id
    assert correction.document_type == "invoice_correction"
    assert correction.technical_status == "draft"
    assert issued.technical_status == "corrected"
    assert issued.number == "RE-2026-0001"
    assert correction.incoming_relations[0].relation_type == "correction"


@pytest.mark.asyncio
async def test_cancellation_is_a_full_reversal_and_preserves_original_number(db_session):
    profile = await _profile(db_session)
    issued = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0002",
        technical_status="issued",
        language="de-DE",
        currency="EUR",
        subtotal_amount=Decimal("100.00"),
        tax_amount=Decimal("19.00"),
        total_amount=Decimal("119.00"),
        open_amount=Decimal("119.00"),
    )
    issued.lines = [
        CommercialDocumentLine(
            position=1,
            description="Bauteil",
            quantity=Decimal("1.000"),
            unit_code="C62",
            unit_price=Decimal("100.00"),
            net_amount=Decimal("100.00"),
            tax_category_code="S",
            tax_rate=Decimal("19.00"),
        )
    ]
    db_session.add(issued)
    await db_session.flush()

    cancellation = await cancel_document(
        db_session,
        issued.id,
        reason="Order cancelled in full",
        actor_id=None,
    )
    await db_session.flush()

    assert issued.technical_status == "cancelled"
    assert issued.number == "RE-2026-0002"
    assert cancellation.document_type == "cancellation_invoice"
    assert cancellation.total_amount == Decimal("-119.00")
    assert cancellation.lines[0].quantity == Decimal("-1.000")
    assert cancellation.lines[0].net_amount == Decimal("-100.00")
    assert cancellation.incoming_relations[0].relation_type == "cancellation"
