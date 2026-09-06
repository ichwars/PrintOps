"""Conservative one-shot repair of demonstrably stale RFID core weights."""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.app.models  # noqa: F401
from backend.app.core.database import Base
from backend.app.core.rfid_core_weight_migration import (
    RFID_CORE_WEIGHT_REPAIR_FLAG,
    repair_rfid_core_weights,
)
from backend.app.models.spool import Spool
from backend.app.models.spool_catalog import SpoolCatalogEntry


@pytest.fixture
async def engine(tmp_path):
    value = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/issue137.db")
    async with value.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield value
    finally:
        await value.dispose()


async def _seed(db):
    rows = [
        SpoolCatalogEntry(name="Bambu Lab - Plastic High Temp", weight=216),
        SpoolCatalogEntry(name="Bambu Lab - Plastic Low Temp", weight=250),
        SpoolCatalogEntry(name="Bambu Lab - Plastic White", weight=253),
    ]
    db.add_all(rows)
    await db.flush()
    return rows


def _spool(**overrides):
    values = {
        "material": "PLA",
        "brand": "Bambu Lab",
        "label_weight": 1000,
        "core_weight": 216,
        "weight_used": 416.0,
        "data_origin": "rfid_auto",
        "tag_type": "bambulab",
        "last_scale_weight": 800,
        "last_weighed_at": datetime(2026, 8, 23, 11, 0),
    }
    values.update(overrides)
    return Spool(**values)


async def _run(engine):
    async with engine.begin() as conn:
        await repair_rfid_core_weights(conn)


@pytest.mark.asyncio
async def test_repairs_only_unedited_legacy_rfid_rows_and_remaining_grams(engine):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        _, low, _ = await _seed(db)
        stale = _spool()
        edited = _spool(core_weight_catalog_id=1)
        manual = _spool(data_origin="manual")
        db.add_all([stale, edited, manual])
        await db.commit()
        ids = stale.id, edited.id, manual.id
        low_id = low.id

    await _run(engine)

    async with sessions() as db:
        repaired = await db.get(Spool, ids[0])
        assert (repaired.core_weight, repaired.core_weight_catalog_id) == (250, low_id)
        assert repaired.weight_used == 450.0
        assert repaired.label_weight - repaired.weight_used == 550.0
        assert (await db.get(Spool, ids[1])).core_weight == 216
        assert (await db.get(Spool, ids[2])).core_weight == 216


@pytest.mark.asyncio
async def test_repair_is_idempotent_and_preserves_later_user_correction(engine):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        await _seed(db)
        stale = _spool(last_weighed_at=None, last_scale_weight=None, weight_used=200)
        db.add(stale)
        await db.commit()
        spool_id = stale.id

    await _run(engine)
    async with sessions() as db:
        repaired = await db.get(Spool, spool_id)
        repaired.core_weight = 216
        repaired.core_weight_catalog_id = None
        await db.commit()

    await _run(engine)
    async with sessions() as db:
        preserved = await db.get(Spool, spool_id)
        assert preserved.core_weight == 216
        assert preserved.weight_used == 200
        assert (
            await db.execute(
                text('SELECT value FROM settings WHERE "key" = :key'), {"key": RFID_CORE_WEIGHT_REPAIR_FLAG}
            )
        ).scalar_one() == "true"
