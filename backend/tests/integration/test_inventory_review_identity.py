"""Review regressions: preserve effective settings, aliases and shared numbers."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.small_part import SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.schemas.warehouse_article import WarehouseArticleCreate, WarehouseArticleUpdate
from backend.app.services.filament_sku_identity import backfill_material_numbers, ensure_sku
from backend.app.services.stock_alert_monitor import StockAlertMonitor
from backend.app.services.warehouse_articles import WarehouseError, create_article, update_article


@pytest.mark.asyncio
async def test_backfill_inherits_canonical_colorless_settings_and_supplier_context(db_session):
    old = FilamentSkuSettings(material="PLA", brand="Own", color_name="", lead_time_days=5)
    fallback = FilamentSkuSettings(
        material=" PLA ",
        brand="Own",
        color_name=None,
        material_number="MAT-00009",
        lead_time_days=21,
        safety_margin_value=500,
        safety_margin_unit="g",
        alerts_snoozed=True,
    )
    supplier = Supplier(name="Own", name_key="own")
    spool = Spool(
        material="PLA",
        brand="Own",
        color_name="Red",
        label_weight=1000,
        weight_used=900,
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db_session.add_all([old, fallback, supplier, spool])
    await db_session.flush()
    offer = ProcurementOffer(
        supplier_id=supplier.id,
        filament_sku_settings_id=old.id,
        resource_key=f"filament:{old.id}",
        is_preferred=True,
        lead_time_days=31,
    )
    db_session.add(offer)
    await db_session.commit()
    await backfill_material_numbers(db_session)
    await db_session.commit()
    exact = await db_session.scalar(select(FilamentSkuSettings).where(FilamentSkuSettings.color_name == "Red"))
    assert (exact.lead_time_days, exact.safety_margin_value, exact.safety_margin_unit, exact.alerts_snoozed) == (
        21,
        500,
        "g",
        True,
    )
    forecasts = await StockAlertMonitor()._forecasts(db_session, False)
    assert forecasts[("PLA", "", "Own", "Red")][0].snoozed is True
    assert forecasts[("PLA", "", "Own", "Red")][0].effective_lead_time_days == 31
    await db_session.refresh(offer)
    assert offer.filament_sku_settings_id == old.id and offer.resource_key == f"filament:{old.id}"


@pytest.mark.asyncio
async def test_procurement_get_and_edit_use_trimmed_nullable_canonical_identity(async_client, db_session):
    row = FilamentSkuSettings(material=" PLA ", subtype="", brand=" ", color_name=None, material_number="MAT-00017")
    supplier = Supplier(name="Own", name_key="own")
    db_session.add_all([row, supplier])
    await db_session.flush()
    offer = ProcurementOffer(
        supplier_id=supplier.id, filament_sku_settings_id=row.id, resource_key=f"filament:{row.id}", is_preferred=True
    )
    db_session.add(offer)
    await db_session.commit()
    response = await async_client.get("/api/v1/procurement-offers", params={"kind": "filament", "material": "PLA"})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [offer.id]
    assert len(list(await db_session.scalars(select(FilamentSkuSettings)))) == 1
    updated = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": {"kind": "filament", "material": "PLA"},
            "offers": [{"id": offer.id, "supplier_id": supplier.id, "lead_time_days": 9, "is_preferred": True}],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()[0]["lead_time_days"] == 9
    await db_session.refresh(offer)
    assert (offer.filament_sku_settings_id, offer.resource_key) == (row.id, f"filament:{row.id}")


@pytest.mark.asyncio
@pytest.mark.parametrize("write", ["create", "update"])
async def test_article_cannot_take_existing_filament_material_number(db_session, write):
    db_session.add(SmallPartUnit(code="C62", label="Piece"))
    await db_session.commit()
    sku = await ensure_sku(db_session, {"material": "PLA"})
    await db_session.commit()
    if write == "create":
        with pytest.raises(WarehouseError, match="already in use"):
            await create_article(
                db_session,
                WarehouseArticleCreate(
                    sku=sku.material_number, name="Unrelated widget", kind="finished", unit_code="C62"
                ),
            )
    else:
        article = await create_article(
            db_session, WarehouseArticleCreate(sku="ITEM-9", name="Widget", kind="finished", unit_code="C62")
        )
        await db_session.commit()
        with pytest.raises(WarehouseError, match="already in use"):
            await update_article(
                db_session, article.id, WarehouseArticleUpdate(sku=sku.material_number, version=article.version)
            )
