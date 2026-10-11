"""Material numbers share the own SKU identity and warehouse allocator."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.small_part import SmallPart, SmallPartUnit
from backend.tests.integration.test_inventory_tag_conflicts import remote_spoolman as remote_spoolman


@pytest.mark.asyncio
async def test_spools_share_one_group_number_across_bulk_and_catalog_reads(async_client):
    response = await async_client.post(
        "/api/v1/inventory/spools/bulk",
        json={"quantity": 3, "spool": {"material": "PLA", "subtype": "Matte", "brand": "Bambu", "color_name": "Black"}},
    )
    assert response.status_code == 200, response.text
    numbers = {spool.get("material_number") for spool in response.json()}
    assert numbers == {"MAT-00001"}
    listed = await async_client.get("/api/v1/inventory/spools")
    assert {spool["material_number"] for spool in listed.json()} == numbers
    settings = await async_client.get("/api/v1/inventory/sku-settings")
    assert len(settings.json()) == 1
    assert settings.json()[0]["material_number"] == "MAT-00001"


@pytest.mark.asyncio
async def test_allocator_sees_historical_material_and_new_sku_numbers(async_client, db_session):
    db_session.add(SmallPartUnit(code="C62", label="Piece"))
    db_session.add(SmallPart(sku="MAT-00001", name="Historical washer", unit_code="C62"))
    await db_session.commit()
    sku = await async_client.post(
        "/api/v1/inventory/sku-settings", json={"material": "PETG", "material_number": "MAT-00002"}
    )
    assert sku.status_code == 200, sku.text
    assert sku.json().get("material_number") == "MAT-00002"
    part = await async_client.post("/api/v1/small-parts", json={"name": "New washer", "unit_code": "C62"})
    assert part.status_code == 201, part.text
    assert part.json()["sku"] == "MAT-00003"
    conflict = await async_client.post(
        "/api/v1/inventory/sku-settings", json={"material": "ABS", "material_number": "MAT-00001"}
    )
    assert conflict.status_code == 409
    reverse = await async_client.post(
        "/api/v1/small-parts", json={"sku": "MAT-00002", "name": "Collision", "unit_code": "C62"}
    )
    assert reverse.status_code == 409


@pytest.mark.asyncio
async def test_nullable_group_upserts_and_legacy_rows_keep_one_identity(async_client, db_session):
    legacy = [
        FilamentSkuSettings(material="PLA", lead_time_days=7),
        FilamentSkuSettings(material="PLA", lead_time_days=12),
    ]
    db_session.add_all(legacy)
    await db_session.commit()
    responses = [await async_client.post("/api/v1/inventory/sku-settings", json={"material": "PLA"}) for _ in range(2)]
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert {r.json()["id"] for r in responses} == {legacy[0].id}
    assert {r.json().get("material_number") for r in responses} == {"MAT-00001"}
    await db_session.refresh(legacy[1])
    assert legacy[1].id == legacy[0].id + 1
    assert len(list((await db_session.scalars(select(FilamentSkuSettings))).all())) == 2
    listed = await async_client.get("/api/v1/inventory/sku-settings")
    assert [row["id"] for row in listed.json()] == [legacy[0].id]


@pytest.mark.asyncio
async def test_spoolman_bulk_creation_uses_own_group_identity(async_client, remote_spoolman):
    response = await async_client.post(
        "/api/v1/spoolman/inventory/spools/bulk",
        json={"quantity": 2, "spool": {"spoolman_filament_id": 7, "label_weight": 250}},
    )
    assert response.status_code == 200, response.text
    assert {spool.get("material_number") for spool in response.json()} == {"MAT-00001"}


@pytest.mark.asyncio
async def test_real_connections_serialize_cross_domain_allocations_and_nullable_groups(tmp_path, test_engine):
    from backend.app.core.database import Base
    from backend.app.services.filament_sku_identity import ensure_sku
    from backend.app.services.warehouse_number_sequence import lock_material_numbers, reserve_number

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/material-race.db", connect_args={"timeout": 10})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(SmallPartUnit(code="C62", label="Piece"))
            await db.commit()

        async def create_filament(material):
            async with sessions() as db:
                sku = await ensure_sku(db, {"material": material})
                await db.commit()
                return sku.material_number

        async def create_material():
            async with sessions() as db:
                await lock_material_numbers(db)
                number = await reserve_number(db, key="material")
                db.add(SmallPart(sku=number, name="Washer", unit_code="C62"))
                await db.commit()
                return number

        values = await asyncio.gather(
            create_filament("PLA"), create_filament("PLA"), create_material(), create_filament("PETG")
        )
        assert values[0] == values[1]
        assert len(set(values)) == 3
        async with sessions() as db:
            assert len(list((await db.scalars(select(FilamentSkuSettings))).all())) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_preserves_procurement_references_and_label_lookup_never_allocates(db_session):
    from backend.app.models.procurement import ProcurementOffer, Supplier
    from backend.app.models.spool import Spool
    from backend.app.services.filament_sku_identity import backfill_material_numbers, resolve_material_numbers

    rows = [FilamentSkuSettings(material="PLA"), FilamentSkuSettings(material="PLA")]
    supplier = Supplier(name="Own supplier", name_key="own supplier")
    spool = Spool(material="PLA", label_weight=1000)
    db_session.add_all([*rows, supplier, spool])
    await db_session.flush()
    offer = ProcurementOffer(
        supplier_id=supplier.id, filament_sku_settings_id=rows[1].id, resource_key=f"filament:{rows[1].id}"
    )
    db_session.add(offer)
    await db_session.commit()
    assert await resolve_material_numbers(db_session, [spool]) == {spool.id: None}
    assert all(row.material_number is None for row in rows)
    await backfill_material_numbers(db_session)
    await db_session.commit()
    assert await resolve_material_numbers(db_session, [spool]) == {spool.id: "MAT-00001"}
    assert rows[1].material_number is None
    assert offer.filament_sku_settings_id == rows[1].id
    assert offer.resource_key == f"filament:{rows[1].id}"
    await backfill_material_numbers(db_session)
    assert rows[0].material_number == "MAT-00001"
