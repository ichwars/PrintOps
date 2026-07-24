from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import (
    CommercialDocument,
    CommercialDocumentLine,
    DocumentRelation,
    DocumentSnapshot,
)
from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot, SnapshotLine
from backend.app.services.document_audit import append_audit
from backend.app.services.document_snapshot import (
    ImmutableDocumentError,
    attach_issued_snapshot,
    replace_issued_snapshot,
)


def _issued_snapshot(number: str = "RE-2026-0001") -> IssuedDocumentSnapshot:
    return IssuedDocumentSnapshot(
        document_type="invoice",
        number=number,
        issue_date=date(2026, 7, 20),
        language="de-DE",
        currency="EUR",
        seller={"name": "Schema GmbH", "country_code": "DE"},
        buyer={"name": "Kunde GmbH", "country_code": "DE"},
        lines=(
            SnapshotLine(
                position=1,
                description="Bauteil",
                quantity=Decimal("1.000"),
                unit_code="C62",
                unit_price=Decimal("10.00"),
                net_amount=Decimal("10.00"),
                tax_category_code="S",
                tax_rate=Decimal("19.00"),
            ),
        ),
        totals={"line_net": Decimal("10.00"), "tax": Decimal("1.90"), "payable": Decimal("11.90")},
    )


async def _profile(db_session) -> BusinessProfile:
    profile = BusinessProfile(
        name="Document schema profile",
        legal_name="Document Schema GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest.mark.asyncio
async def test_document_aggregate_persists_lines_relations_and_snapshot(db_session):
    profile = await _profile(db_session)
    quotation = CommercialDocument(
        document_type="quotation",
        business_profile_id=profile.id,
        technical_status="draft",
        language="de-DE",
        currency="EUR",
    )
    quotation.lines = [
        CommercialDocumentLine(
            position=1,
            description="Bauteil",
            quantity=Decimal("1.000"),
            unit_code="C62",
            unit_price=Decimal("10.00"),
            net_amount=Decimal("10.00"),
            tax_category_code="S",
            tax_rate=Decimal("19.00"),
        )
    ]
    invoice = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0001",
        technical_status="issued",
        language="de-DE",
        currency="EUR",
    )
    db_session.add_all([quotation, invoice])
    await db_session.flush()
    db_session.add(
        DocumentRelation(
            source_document_id=quotation.id,
            target_document_id=invoice.id,
            relation_type="successor",
        )
    )
    snapshot = await attach_issued_snapshot(
        db_session,
        invoice,
        _issued_snapshot(),
        configuration_id=None,
        configuration_version=1,
        tax_rule_version="2026.1",
        einvoice_rule_versions={"en16931": "1.3.16"},
        actor_id=None,
    )
    await db_session.flush()
    await db_session.refresh(invoice, attribute_names=["incoming_relations", "snapshot"])

    assert quotation.lines[0].net_amount == Decimal("10.00")
    assert invoice.incoming_relations[0].source_document_id == quotation.id
    assert snapshot.sha256
    assert invoice.snapshot.id == snapshot.id


@pytest.mark.asyncio
async def test_issued_snapshot_and_audit_event_are_immutable(db_session):
    profile = await _profile(db_session)
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0001",
        technical_status="issued",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    snapshot = await attach_issued_snapshot(
        db_session,
        document,
        _issued_snapshot(),
        configuration_id=None,
        configuration_version=1,
        tax_rule_version="2026.1",
        einvoice_rule_versions={},
        actor_id=None,
    )
    event = await append_audit(
        db_session,
        action="issue",
        object_type="commercial_document",
        object_id=document.id,
        actor_id=None,
        reason="Invoice approved and issued",
        before={"technical_status": "ready"},
        after={"technical_status": "issued"},
        correlation_id="corr-1",
    )
    await db_session.flush()
    event_id = event.id
    await db_session.commit()

    with pytest.raises(ImmutableDocumentError):
        await replace_issued_snapshot(db_session, document.id, _issued_snapshot("RE-2026-9999"))

    snapshot.sha256 = "0" * 64
    with pytest.raises(ImmutableDocumentError):
        await db_session.flush()
    await db_session.rollback()

    persisted_event = await db_session.get(DocumentAuditEvent, event_id)
    assert persisted_event is not None
    persisted_event.reason = "rewritten"
    with pytest.raises(ImmutableDocumentError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_sensitive_audit_actions_require_reason(db_session):
    with pytest.raises(ValueError, match="reason"):
        await append_audit(
            db_session,
            action="tax_override",
            object_type="commercial_document",
            object_id=1,
            actor_id=None,
            reason=" ",
            before=None,
            after={"rate": "7.00"},
            correlation_id="corr-2",
        )


@pytest.mark.asyncio
async def test_commercial_document_tables_are_registered(test_engine):
    async with test_engine.connect() as connection:
        names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {
        "commercial_documents",
        "commercial_document_lines",
        "document_relations",
        "document_snapshots",
        "document_artifacts",
        "document_number_reservations",
        "document_audit_events",
    } <= names
