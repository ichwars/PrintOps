from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.small_part import SmallPart, SmallPartCategory, SmallPartUnit
from backend.app.schemas.small_part import SmallPartUpdate
from backend.app.services.small_parts import (
    InsufficientSmallPartStock,
    SmallPartBalance,
    SmallPartUnitChangeNotAllowed,
    append_ledger_entry,
    get_balance,
    search_small_parts,
    update_small_part,
)


@pytest.fixture
async def small_part(db_session: AsyncSession) -> SmallPart:
    db_session.add(SmallPartUnit(code="C62", label="Stück", decimal_places=0))
    part = SmallPart(sku="M3-001", name="M3 Gewindeeinsatz", unit_code="C62")
    db_session.add(part)
    await db_session.commit()
    await db_session.refresh(part)
    return part


@pytest.mark.asyncio
async def test_ledger_is_idempotent_and_never_overdraws(db_session: AsyncSession, small_part: SmallPart):
    first = await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("10"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-M3-001",
    )
    again = await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("10"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-M3-001",
    )

    assert again.id == first.id
    assert await get_balance(db_session, small_part.id) == SmallPartBalance(
        physical=Decimal("10"), reserved=Decimal("0"), available=Decimal("10")
    )

    with pytest.raises(InsufficientSmallPartStock):
        await append_ledger_entry(
            db_session,
            small_part_id=small_part.id,
            entry_kind="reservation",
            physical_delta=Decimal("0"),
            reserved_delta=Decimal("11"),
            reason="Order reservation",
            idempotency_key="reserve-order-11",
        )


@pytest.mark.asyncio
async def test_release_and_issue_preserve_non_negative_balances(db_session: AsyncSession, small_part: SmallPart):
    await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("5"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-M3-release",
    )
    await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="reservation",
        physical_delta=Decimal("0"),
        reserved_delta=Decimal("3"),
        reason="Order reservation",
        idempotency_key="reserve-M3-release",
    )
    await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="issue",
        physical_delta=Decimal("-3"),
        reserved_delta=Decimal("-3"),
        reason="Order consumption",
        idempotency_key="issue-M3-release",
    )

    assert await get_balance(db_session, small_part.id) == SmallPartBalance(
        physical=Decimal("2"), reserved=Decimal("0"), available=Decimal("2")
    )


@pytest.mark.asyncio
async def test_search_matches_normalized_catalog_text_and_reports_available_stock(db_session: AsyncSession):
    category = SmallPartCategory(name="Schrauben", name_key="schrauben")
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(
        sku="DIN-912-M3",
        name="Zylinderschraube M3",
        search_terms="innensechskant",
        category=category,
        unit=unit,
    )
    db_session.add(part)
    await db_session.commit()
    await db_session.refresh(part)
    await append_ledger_entry(
        db_session,
        small_part_id=part.id,
        entry_kind="opening",
        physical_delta=Decimal("25"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-search-M3",
    )

    results = await search_small_parts(db_session, query="SCHRAUBEN", active_only=True, limit=10)

    assert [(item.part.id, item.available) for item in results] == [(part.id, Decimal("25"))]


@pytest.mark.asyncio
async def test_unit_cannot_change_after_stock_journal_exists(db_session: AsyncSession, small_part: SmallPart):
    db_session.add(SmallPartUnit(code="KGM", label="Kilogramm", decimal_places=3))
    await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("1"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-unit-lock",
    )

    with pytest.raises(SmallPartUnitChangeNotAllowed):
        await update_small_part(db_session, small_part, SmallPartUpdate(unit_code="KGM"))
