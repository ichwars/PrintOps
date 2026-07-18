from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.services.stock_availability import (
    InsufficientStock,
    StockCandidate,
    StockRequirement,
    allocate_candidates,
    check_availability,
    requirements_from_snapshot,
)


def test_filament_allocation_is_deterministic_and_can_split_spools():
    candidates = [
        StockCandidate("internal", "1", Decimal("500"), "PETG"),
        StockCandidate("internal", "2", Decimal("400"), "PETG"),
    ]

    allocations = allocate_candidates("plate:1", Decimal("750"), candidates)

    assert [(item.candidate.resource_id, item.quantity) for item in allocations] == [
        ("1", Decimal("500")),
        ("2", Decimal("250")),
    ]


def test_allocation_reports_shortage_without_partial_success():
    with pytest.raises(InsufficientStock) as error:
        allocate_candidates(
            "plate:1",
            Decimal("750"),
            [StockCandidate("internal", "1", Decimal("500"), "PETG")],
        )

    assert error.value.shortage == Decimal("250")


def test_requirements_are_derived_from_immutable_selected_variant():
    snapshot = {
        "variants": [
            {
                "sort_order": 0,
                "is_preferred": True,
                "plates": [
                    {
                        "project_plate_id": 12,
                        "stable_key": "plate-a",
                        "good_parts": 7,
                        "parts_per_print": 3,
                        "scrap_prints": 1,
                        "material_code": "PETG",
                        "grams_per_print": "100",
                    }
                ],
                "small_parts": [
                    {
                        "small_part_id": 8,
                        "quantity": "4",
                        "unit_code": "C62",
                        "description": "M3 screw",
                    }
                ],
            }
        ],
    }

    requirements = requirements_from_snapshot(snapshot, 0)

    assert requirements[0].quantity == Decimal("400")
    assert requirements[0].material_code == "PETG"
    assert requirements[1].small_part_id == 8
    assert requirements[1].quantity == Decimal("4")


@pytest.mark.asyncio
async def test_repeated_requirements_share_internal_filament_capacity(db_session):
    db_session.add(Spool(material="PETG", label_weight=150, weight_used=0))
    await db_session.commit()
    requirements = tuple(
        StockRequirement(f"plate:{index}", "filament", Decimal("100"), "GRM", material_code="PETG")
        for index in range(2)
    )

    report = await check_availability(db_session, requirements)

    assert [line.status for line in report.lines] == ["available", "short"]
    assert report.lines[1].available == Decimal("50")


@pytest.mark.asyncio
async def test_repeated_requirements_share_small_part_capacity(db_session):
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(sku="SHARED", name="Shared part", unit_code="C62")
    db_session.add_all([unit, part])
    await db_session.flush()
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="opening",
            physical_delta=Decimal("5"),
            reserved_delta=Decimal("0"),
            reason="Opening",
            idempotency_key="shared-small-part-opening",
        )
    )
    await db_session.commit()
    requirements = tuple(
        StockRequirement(f"part:{index}", "small_part", Decimal("3"), "C62", small_part_id=part.id)
        for index in range(2)
    )

    report = await check_availability(db_session, requirements)

    assert [line.status for line in report.lines] == ["available", "short"]
    assert report.lines[1].available == Decimal("2")


@pytest.mark.asyncio
async def test_spoolman_mode_uses_external_spools(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.stock_availability.get_setting",
        AsyncMock(return_value="true"),
    )
    client = AsyncMock()
    client.get_spools.return_value = [
        {"id": 42, "remaining_weight": 250, "filament": {"material": "PETG", "weight": 1000}}
    ]
    monkeypatch.setattr(
        "backend.app.services.stock_availability.get_spoolman_client",
        AsyncMock(return_value=client),
    )
    requirement = StockRequirement("plate:1", "filament", Decimal("200"), "GRM", material_code="PETG")

    report = await check_availability(db_session, (requirement,))

    assert report.lines[0].status == "available"
    assert report.lines[0].allocations[0].candidate.backend == "spoolman"
    assert report.lines[0].allocations[0].candidate.resource_id == "42"
