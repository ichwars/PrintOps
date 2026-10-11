"""All writers serialize the shared material namespace, preserving linked IDs."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.small_part import SmallPart, SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticle
from backend.app.schemas.warehouse_article import WarehouseArticleCreate, WarehouseArticleUpdate
from backend.app.services.filament_sku_identity import ensure_sku
from backend.app.services.warehouse_articles import WarehouseError, create_article, update_article


@pytest.mark.asyncio
async def test_linked_small_part_article_keeps_legitimate_number_and_ids(db_session):
    db_session.add(SmallPartUnit(code="C62", label="Piece"))
    part = SmallPart(sku="MAT-00001", name="Washer", unit_code="C62")
    db_session.add(part)
    await db_session.flush()
    article = await create_article(
        db_session,
        WarehouseArticleCreate(
            sku="MAT-00001",
            name="Washer box",
            kind="trade",
            unit_code="C62",
            stock_source="material",
            small_part_id=part.id,
        ),
    )
    await db_session.commit()
    article_id = article.id
    updated = await update_article(
        db_session, article_id, WarehouseArticleUpdate(name="Own washer box", sku="MAT-00001", version=article.version)
    )
    await db_session.commit()
    assert (updated.id, updated.small_part_id, updated.sku) == (article_id, part.id, "MAT-00001")
    assert part.sku == "MAT-00001"


@pytest.mark.asyncio
async def test_independent_article_writer_cannot_claim_a_filament_number_awaiting_commit(tmp_path, test_engine):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/article-number-race.db", connect_args={"timeout": 10})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    allocated = asyncio.Event()
    article_entered = asyncio.Event()
    release = asyncio.Event()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(SmallPartUnit(code="C62", label="Piece"))
            await db.commit()

        async def filament():
            async with sessions() as db:
                row = await ensure_sku(db, {"material": "PLA"})
                allocated.set()
                await release.wait()
                await db.commit()
                return row.material_number

        async def article():
            await allocated.wait()
            async with sessions() as db:
                article_entered.set()
                try:
                    row = await create_article(
                        db, WarehouseArticleCreate(sku="MAT-00001", name="Widget", kind="finished", unit_code="C62")
                    )
                    await db.commit()
                    return row.sku
                except WarehouseError as exc:
                    await db.rollback()
                    return exc.code

        filament_task = asyncio.create_task(filament())
        article_task = asyncio.create_task(article())
        try:
            await asyncio.wait_for(article_entered.wait(), timeout=2)
            release.set()
            assert await asyncio.gather(filament_task, article_task) == ["MAT-00001", "material_number_conflict"]
        finally:
            release.set()
            await asyncio.gather(filament_task, article_task, return_exceptions=True)
        async with sessions() as db:
            assert list(await db.scalars(select(WarehouseArticle))) == []
    finally:
        release.set()
        await engine.dispose()
