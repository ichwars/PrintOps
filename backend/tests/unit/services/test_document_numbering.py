from __future__ import annotations

from datetime import date

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.document_numbering import (
    document_sequence_key,
    reserve_document_number,
)


@pytest.mark.parametrize(
    ("document_type", "expected_key"),
    [
        ("quotation", "offer"),
        ("order_confirmation", "order"),
        ("delivery_note", "order"),
        ("invoice", "invoice"),
        ("final_invoice", "invoice"),
        ("self_billing", "invoice"),
    ],
)
def test_document_types_use_the_configured_number_family(document_type, expected_key):
    assert document_sequence_key(document_type) == expected_key


@pytest.mark.asyncio
async def test_reservation_persists_number_and_sequence_reference(db_session):
    profile = BusinessProfile(
        name="Numbering profile",
        legal_name="Numbering GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    sequence = NumberSequence(
        business_profile_id=profile.id,
        key="invoice",
        prefix="RE",
        pattern="{PREFIX}-{YYYY}-{####}",
        reset_policy="yearly",
    )
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        technical_status="ready",
        issue_date=date(2026, 7, 20),
        language="de-DE",
        currency="EUR",
    )
    db_session.add_all([sequence, document])
    await db_session.flush()

    reservation = await reserve_document_number(
        db_session,
        document,
        date(2026, 7, 20),
        idempotency_key="issue-number-1",
        intent_sha256="a" * 64,
    )
    await db_session.flush()

    assert reservation.number == "RE-2026-0001"
    assert reservation.sequence_id == sequence.id
    assert reservation.status == "reserved"
    assert reservation.intent_sha256 == "a" * 64


@pytest.mark.asyncio
async def test_existing_legacy_document_number_is_evidenced_without_consuming_next_value(db_session):
    profile = BusinessProfile(
        name="Legacy number profile",
        legal_name="Legacy Number GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    sequence = NumberSequence(
        business_profile_id=profile.id,
        key="offer",
        prefix="ANG",
        pattern="{PREFIX}-{YYYY}-{####}",
        next_value=42,
    )
    document = CommercialDocument(
        document_type="quotation",
        business_profile_id=profile.id,
        number="ANG-2026-0041",
        technical_status="ready",
        issue_date=date(2026, 7, 20),
        language="de-DE",
        currency="EUR",
    )
    db_session.add_all([sequence, document])
    await db_session.flush()

    reservation = await reserve_document_number(
        db_session,
        document,
        date(2026, 7, 20),
    )
    await db_session.flush()

    assert reservation.number == "ANG-2026-0041"
    assert sequence.next_value == 42
