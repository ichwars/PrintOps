from decimal import Decimal

from sqlalchemy import func, select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation, CalculationRevision, CalculationVariant
from backend.app.models.commerce import CustomerOrder, OfferAcceptance
from backend.app.models.number_sequence import NumberSequence
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.models.stock_reservation import StockReservation


async def _approved_revision(db_session, *, with_requirements: bool = False) -> CalculationRevision:
    profile = BusinessProfile(name="Commerce", legal_name="Commerce GmbH", country_code="DE", default_currency="EUR")
    db_session.add(profile)
    await db_session.flush()
    db_session.add_all(
        [
            NumberSequence(
                business_profile_id=profile.id,
                key="offer",
                prefix="ANG",
                pattern="{PREFIX}-{YYYY}-{#####}",
                reset_policy="yearly",
            ),
            NumberSequence(
                business_profile_id=profile.id,
                key="order",
                prefix="AUF",
                pattern="{PREFIX}-{YYYY}-{#####}",
                reset_policy="yearly",
            ),
        ]
    )
    calculation = Calculation(business_profile_id=profile.id, title="Mounting set", status="approved")
    calculation.variants.append(CalculationVariant(name="Standard", is_preferred=True, sort_order=0))
    db_session.add(calculation)
    await db_session.flush()
    plates = []
    small_parts = []
    if with_requirements:
        plates = [
            {
                "project_plate_id": 1,
                "stable_key": "plate-one",
                "plate_name": "Plate 1",
                "good_parts": 2,
                "parts_per_print": 2,
                "scrap_prints": 0,
                "material_code": "PETG",
                "grams_per_print": "120",
            }
        ]
        small_parts = [{"small_part_id": 1, "quantity": "3", "unit_code": "C62", "description": "M3 screw"}]
    revision = CalculationRevision(
        calculation_id=calculation.id,
        revision_number=1,
        snapshot={
            "calculation": {
                "id": calculation.id,
                "title": calculation.title,
                "business_profile_id": profile.id,
                "customer_id": None,
                "currency": "EUR",
            },
            "variants": [
                {
                    "name": "Standard",
                    "sort_order": 0,
                    "is_preferred": True,
                    "plates": plates,
                    "small_parts": small_parts,
                }
            ],
        },
        production_cost=Decimal("15"),
        selling_price=Decimal("25"),
        currency="EUR",
    )
    db_session.add(revision)
    await db_session.commit()
    await db_session.refresh(revision)
    return revision


async def test_offer_draft_send_and_reject_do_not_reserve_stock(async_client, db_session):
    revision = await _approved_revision(db_session)

    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    assert created.json()["number"].startswith("ANG-")
    sent = await async_client.post(f"/api/v1/offers/{created.json()['id']}/send", json={"expected_version": 1})
    assert sent.status_code == 200, sent.text
    rejected = await async_client.post(f"/api/v1/offers/{created.json()['id']}/reject", json={"expected_version": 2})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0


async def test_accepting_sent_offer_creates_order_project_and_reservations_once(async_client, db_session):
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(sku="M3", name="M3 screw", unit_code="C62", unit_cost=Decimal("0.05"))
    db_session.add_all([unit, part, Spool(material="PETG", label_weight=500, weight_used=100)])
    await db_session.flush()
    assert part.id == 1
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="opening",
            physical_delta=10,
            reserved_delta=0,
            reason="Opening",
            idempotency_key="opening-m3",
        )
    )
    await db_session.commit()
    revision = await _approved_revision(db_session, with_requirements=True)
    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    sent = await async_client.post(f"/api/v1/offers/{created.json()['id']}/send", json={"expected_version": 1})

    accepted = await async_client.post(
        f"/api/v1/offers/{created.json()['id']}/accept",
        json={"expected_version": sent.json()["version"], "idempotency_key": "accept-mounting-set-1"},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["offer"]["status"] == "accepted"
    assert len(accepted.json()["order"]["reservations"]) == 2
    replay = await async_client.post(
        f"/api/v1/offers/{created.json()['id']}/accept",
        json={"expected_version": sent.json()["version"], "idempotency_key": "accept-mounting-set-1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["order"]["id"] == accepted.json()["order"]["id"]
    assert await db_session.scalar(select(func.count()).select_from(CustomerOrder)) == 1
    assert await db_session.scalar(select(func.count()).select_from(OfferAcceptance)) == 1
