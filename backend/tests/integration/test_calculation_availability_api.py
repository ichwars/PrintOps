from decimal import Decimal

from sqlalchemy import func, select

from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.models.stock_reservation import StockReservation


async def test_availability_preview_checks_both_stores_without_reserving(async_client, db_session):
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(sku="SCREW", name="Screw", unit_code="C62", unit_cost=Decimal("0.05"))
    db_session.add_all([unit, part, Spool(material="PETG", label_weight=500, weight_used=100)])
    await db_session.flush()
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="opening",
            physical_delta=5,
            reserved_delta=0,
            reason="Opening",
            idempotency_key="availability-opening",
        )
    )
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/calculations/availability-preview",
        json={
            "name": "Standard",
            "is_preferred": True,
            "plates": [
                {
                    "project_plate_id": 1,
                    "good_parts": 4,
                    "parts_per_print": 2,
                    "material_code": "PETG",
                    "grams_per_print": "100",
                }
            ],
            "small_parts": [
                {
                    "small_part_id": part.id,
                    "quantity": "6",
                    "description_snapshot": "Screw",
                    "unit_code_snapshot": "C62",
                    "unit_cost_snapshot": "0.05",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["reservation_state"] == "not_reserved"
    assert [line["status"] for line in response.json()["lines"]] == ["available", "short"]
    assert Decimal(response.json()["lines"][1]["shortage"]) == Decimal("1")
    assert await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(SmallPartLedgerEntry)
            .where(SmallPartLedgerEntry.entry_kind == "reservation")
        )
        == 0
    )
