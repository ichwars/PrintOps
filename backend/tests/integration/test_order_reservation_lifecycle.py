from decimal import Decimal

from sqlalchemy import select

from backend.app.models.small_part import SmallPartLedgerEntry
from backend.app.models.spool import Spool
from backend.app.services.small_parts import get_balance
from backend.tests.integration.test_offers_api import _approved_revision
from backend.app.models.small_part import SmallPart, SmallPartUnit


async def _accepted_order(async_client, db_session):
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(sku="M3", name="M3 screw", unit_code="C62", unit_cost=Decimal("0.05"))
    spool = Spool(material="PETG", label_weight=500, weight_used=100)
    db_session.add_all([unit, part, spool])
    await db_session.flush()
    db_session.add(SmallPartLedgerEntry(small_part_id=part.id, entry_kind="opening", physical_delta=10, reserved_delta=0, reason="Opening", idempotency_key="opening-order-flow"))
    await db_session.commit()
    revision = await _approved_revision(db_session, with_requirements=True)
    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    sent = await async_client.post(f"/api/v1/offers/{created.json()['id']}/send", json={"expected_version": 1})
    accepted = await async_client.post(f"/api/v1/offers/{created.json()['id']}/accept", json={"expected_version": sent.json()["version"], "idempotency_key": "accept-order-lifecycle"})
    return accepted.json()["order"], part, spool


async def test_issue_reconcile_and_cancel_release_remaining_reservations(async_client, db_session):
    order, part, spool = await _accepted_order(async_client, db_session)
    small_allocation = next(item for reservation in order["reservations"] if reservation["resource_kind"] == "small_part" for item in reservation["allocations"])
    filament_allocation = next(item for reservation in order["reservations"] if reservation["resource_kind"] == "filament" for item in reservation["allocations"])

    issued = await async_client.post(f"/api/v1/orders/{order['id']}/small-parts/{small_allocation['id']}/issue", json={"quantity": "2", "idempotency_key": "issue-order-1"})
    assert issued.status_code == 200, issued.text
    replay = await async_client.post(f"/api/v1/orders/{order['id']}/small-parts/{small_allocation['id']}/issue", json={"quantity": "2", "idempotency_key": "issue-order-1"})
    assert replay.status_code == 200, replay.text
    reconciled = await async_client.post(f"/api/v1/orders/{order['id']}/filament/{filament_allocation['id']}/reconcile", json={"quantity": "100", "idempotency_key": "reconcile-order-1"})
    assert reconciled.status_code == 200, reconciled.text

    cancelled = await async_client.post(f"/api/v1/orders/{order['id']}/cancel", json={"idempotency_key": "cancel-order-1"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    balance = await get_balance(db_session, part.id)
    await db_session.refresh(spool)
    assert balance.physical == Decimal("8")
    assert balance.reserved == Decimal("0")
    assert Decimal(str(spool.weight_used)) == Decimal("200")
    assert len((await db_session.scalars(select(SmallPartLedgerEntry).where(SmallPartLedgerEntry.entry_kind == "issue"))).all()) == 1
