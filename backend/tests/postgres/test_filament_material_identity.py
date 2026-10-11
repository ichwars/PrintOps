"""Real PostgreSQL upgrade and concurrent cross-domain material allocation."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base, run_migrations
from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.small_part import SmallPart, SmallPartUnit
from backend.app.schemas.warehouse_article import WarehouseArticleCreate
from backend.app.services.filament_sku_identity import backfill_material_numbers, ensure_sku
from backend.app.services.warehouse_articles import WarehouseError, create_article
from backend.app.services.warehouse_number_sequence import reserve_number

URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not URL, reason="live PostgreSQL URL not configured")]


async def test_upgrade_twice_preserves_legacy_references_and_serializes_shared_allocations(test_engine, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "database_url", URL)
    database_name = f"stock_identity_{uuid4().hex}"
    admin = create_async_engine(URL, isolation_level="AUTOCOMMIT")
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE DATABASE {database_name}"))
    engine = create_async_engine(make_url(URL).set(database=database_name))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE filament_sku_settings DROP COLUMN material_number CASCADE"))
            await conn.execute(
                text(
                    "INSERT INTO filament_sku_settings (id,material,lead_time_days,safety_margin_value,safety_margin_unit,alerts_snoozed) VALUES (41,'PLA',12,14,'days',false),(42,'PLA',4,14,'days',false)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO suppliers (id,name,name_key,default_lead_time_days,is_active) VALUES (31,'Own supplier','own supplier',0,true)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO procurement_offers (id,supplier_id,filament_sku_settings_id,resource_key,package_quantity,package_unit_code,minimum_order_quantity,lead_time_days,net_price,gross_price,is_preferred,is_active) VALUES (21,31,42,'filament:42',1,'C62',1,0,1,1,false,true)"
                )
            )
            await run_migrations(conn)
            await run_migrations(conn)
            columns = await conn.run_sync(
                lambda sync: {c["name"] for c in inspect(sync).get_columns("filament_sku_settings")}
            )
            assert "material_number" in columns
        async with sessions() as db:
            await backfill_material_numbers(db)
            db.add(SmallPartUnit(code="C62", label="Piece"))
            await db.commit()
            offer = await db.get(ProcurementOffer, 21)
            assert (offer.filament_sku_settings_id, offer.resource_key) == (42, "filament:42")
            assert (await db.get(FilamentSkuSettings, 41)).material_number == "MAT-00001"
            assert (await db.get(FilamentSkuSettings, 42)).material_number is None
            assert (await db.get(Supplier, 31)).name == "Own supplier"

        async def filament():
            async with sessions() as db:
                row = await ensure_sku(db, {"material": "PETG"})
                await db.commit()
                return row.material_number

        async def small_part():
            async with sessions() as db:
                number = await reserve_number(db, key="material")
                db.add(SmallPart(sku=number, name="Washer", unit_code="C62"))
                await db.commit()
                return number

        async def article():
            async with sessions() as db:
                number = await reserve_number(db, key="material")
                row = await create_article(
                    db, WarehouseArticleCreate(sku=number, name="Printed widget", kind="finished", unit_code="C62")
                )
                await db.commit()
                return row.sku

        values = await asyncio.gather(filament(), small_part(), filament(), article())
        assert values[0] == values[2]
        assert set(values) == {"MAT-00002", "MAT-00003", "MAT-00004"}

        allocated = asyncio.Event()
        article_entered = asyncio.Event()
        release = asyncio.Event()

        async def held_filament():
            async with sessions() as db:
                row = await ensure_sku(db, {"material": "ABS"})
                allocated.set()
                await release.wait()
                await db.commit()
                return row.material_number

        async def explicit_article():
            await allocated.wait()
            async with sessions() as db:
                article_entered.set()
                try:
                    await create_article(
                        db, WarehouseArticleCreate(sku="MAT-00005", name="Collision", kind="finished", unit_code="C62")
                    )
                    await db.commit()
                    return "accepted"
                except WarehouseError as exc:
                    await db.rollback()
                    return exc.code

        filament_task = asyncio.create_task(held_filament())
        article_task = asyncio.create_task(explicit_article())
        try:
            await asyncio.wait_for(article_entered.wait(), timeout=2)
            release.set()
            assert await asyncio.gather(filament_task, article_task) == ["MAT-00005", "material_number_conflict"]
        finally:
            release.set()
            await asyncio.gather(filament_task, article_task, return_exceptions=True)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE {database_name}"))
        await admin.dispose()
