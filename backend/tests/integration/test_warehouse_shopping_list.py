from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import create_access_token, get_password_hash
from backend.app.core.database import load_all_models
from backend.app.models.group import Group
from backend.app.models.procurement import WarehouseShoppingListItem
from backend.app.models.settings import Settings
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.user import User
from backend.app.models.warehouse_article import WarehouseArticle

SHOPPING_LIST = "/api/v1/warehouse-shopping-list"
PURCHASE_ORDERS = "/api/v1/warehouse-purchase-orders"


@pytest.fixture
async def stock_resources(db_session: AsyncSession):
    db_session.add(SmallPartUnit(code="MTR", label="Metre", decimal_places=6))
    part = SmallPart(sku="MAT-1", name="Cable", unit_code="MTR", minimum_stock=Decimal("3.500001"))
    db_session.add(part)
    await db_session.flush()
    linked = WarehouseArticle(
        sku="GOOD-1",
        name="Cable for sale",
        kind="trade",
        stock_source="material",
        small_part_id=part.id,
        unit_code="MTR",
        minimum_stock=Decimal("5.250001"),
    )
    own = WarehouseArticle(
        sku="GOOD-2",
        name="Independent roll",
        kind="finished",
        stock_source="own",
        unit_code="MTR",
        minimum_stock=Decimal("999999999999.000001"),
    )
    service = WarehouseArticle(sku="SVC-1", name="Cutting", kind="service", stock_source="none", unit_code="MTR")
    db_session.add_all([linked, own, service])
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="opening",
            physical_delta=Decimal("2"),
            reserved_delta=Decimal("0.75"),
            reason="Test stock",
            idempotency_key="shopping-list-stock",
        )
    )
    await db_session.commit()
    return part, linked, own, service


@pytest.mark.asyncio
async def test_only_material_can_be_added_and_uses_its_own_minimum(async_client, stock_resources):
    part, linked, own, service = stock_resources

    for article in (linked, own, service):
        rejected = await async_client.put(f"{SHOPPING_LIST}/warehouse/{article.id}")
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "warehouse_article_not_purchasable"
    assert (await async_client.get(SHOPPING_LIST)).json() == []

    result = await async_client.put(f"{SHOPPING_LIST}/material/{part.id}")
    assert result.status_code == 200
    assert result.json() == {
        "id": result.json()["id"],
        "resource_kind": "material",
        "resource_id": part.id,
        "sku": "MAT-1",
        "name": "Cable",
        "quantity": "2.250001",
        "unit_code": "MTR",
        "unit_label": "Metre",
    }
    assert (await async_client.get(SHOPPING_LIST)).json() == [result.json()]


@pytest.mark.asyncio
async def test_legacy_warehouse_shopping_items_are_excluded_and_preserved(async_client, db_session, stock_resources):
    _, _, article, _ = stock_resources
    existing = WarehouseShoppingListItem(
        article_id=article.id,
        sku=article.sku,
        name=article.name,
        quantity=Decimal("2"),
        unit_code=article.unit_code,
        unit_label="Metre",
    )
    db_session.add(existing)
    await db_session.commit()

    assert (await async_client.get(SHOPPING_LIST)).json() == []
    assert (await async_client.delete(f"{SHOPPING_LIST}/{existing.id}")).status_code == 204
    await db_session.refresh(existing)
    assert existing.article_id == article.id


@pytest.mark.asyncio
async def test_repeat_keeps_the_saved_quantity_after_a_stock_change(async_client, db_session, stock_resources):
    part, _, _, _ = stock_resources
    url = f"{SHOPPING_LIST}/material/{part.id}"
    original = await async_client.put(url)
    assert original.status_code == 200
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="receipt",
            physical_delta=Decimal("5"),
            reserved_delta=Decimal("0"),
            reason="New stock",
            idempotency_key="shopping-list-receipt",
        )
    )
    await db_session.commit()

    repeated = await async_client.put(url)

    assert repeated.status_code == 200
    assert repeated.json() == original.json()
    assert (await async_client.delete(f"{SHOPPING_LIST}/{original.json()['id']}")).status_code == 204
    assert (await async_client.put(url)).status_code == 409


@pytest.mark.asyncio
async def test_removing_item_detaches_order_without_removing_a_later_item(async_client, db_session, stock_resources):
    part, _, _, _ = stock_resources
    other = SmallPart(sku="MAT-2", name="Wire", unit_code="MTR", minimum_stock=Decimal("2"))
    db_session.add(other)
    await db_session.commit()

    added = await async_client.put(f"{SHOPPING_LIST}/material/{part.id}")
    item_url = f"{SHOPPING_LIST}/{added.json()['id']}"
    created = await async_client.post(f"{item_url}/purchase-order")
    assert created.status_code == 201, created.text
    order = created.json()
    assert (await async_client.delete(item_url)).status_code == 204

    replacement = await async_client.put(f"{SHOPPING_LIST}/material/{other.id}")
    assert replacement.status_code == 200, replacement.text
    new_order = await async_client.post(f"{SHOPPING_LIST}/{replacement.json()['id']}/purchase-order")
    assert new_order.status_code == 201, new_order.text
    assert new_order.json()["sku"] == other.sku
    assert new_order.json()["id"] != order["id"]

    receipt = await async_client.post(
        f"{PURCHASE_ORDERS}/{order['id']}/receipts",
        json={"quantity": order["quantity"], "idempotency_key": "receipt-after-shopping-item-removal"},
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["order"]["shopping_item_id"] is None
    assert Decimal(receipt.json()["order"]["open_quantity"]) == 0
    assert (await async_client.get(SHOPPING_LIST)).json() == [replacement.json()]


@pytest.mark.asyncio
async def test_rejects_unknown_material_and_unsupported_resource_kind(async_client, stock_resources):
    assert (await async_client.put(f"{SHOPPING_LIST}/material/999999")).status_code == 404
    assert (await async_client.put(f"{SHOPPING_LIST}/filament/1")).status_code == 422
    assert (await async_client.get(SHOPPING_LIST)).json() == []


@pytest.mark.asyncio
async def test_shopping_list_and_purchase_order_routes_enforce_inventory_permissions(
    async_client, db_session, stock_resources
):
    part, _, _, _ = stock_resources
    db_session.add(Settings(key="auth_enabled", value="true"))
    for permission in ("read", "update"):
        user = User(username=f"shopping_{permission}", password_hash=get_password_hash("password"), is_active=True)
        user.groups.append(Group(name=f"Shopping {permission}", permissions=[f"inventory:{permission}"]))
        db_session.add(user)
    await db_session.commit()

    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    reader = auth(create_access_token({"sub": "shopping_read"}))
    updater = auth(create_access_token({"sub": "shopping_update"}))
    expired = auth(create_access_token({"sub": "shopping_update"}, expires_delta=-timedelta(minutes=5)))
    add = f"{SHOPPING_LIST}/material/{part.id}"
    assert (await async_client.get(SHOPPING_LIST)).status_code == 401
    assert (await async_client.get(SHOPPING_LIST, headers=auth("invalid"))).status_code == 401
    assert (await async_client.get(SHOPPING_LIST, headers=reader)).status_code == 200
    assert (await async_client.get(SHOPPING_LIST, headers=updater)).status_code == 403
    assert (await async_client.put(add, headers=reader)).status_code == 403
    assert (await async_client.put(add, headers=expired)).status_code == 401
    added = await async_client.put(add, headers=updater)
    assert added.status_code == 200

    draft = f"{SHOPPING_LIST}/{added.json()['id']}/purchase-order"
    assert (await async_client.post(draft)).status_code == 401
    assert (await async_client.post(draft, headers=auth("invalid"))).status_code == 401
    assert (await async_client.post(draft, headers=expired)).status_code == 401
    assert (await async_client.post(draft, headers=reader)).status_code == 403
    order = await async_client.post(draft, headers=updater)
    assert order.status_code == 201
    receipts = f"{PURCHASE_ORDERS}/{order.json()['id']}/receipts"
    command = {"quantity": "1", "idempotency_key": "receipt-authorization-test"}
    for path in (PURCHASE_ORDERS, receipts):
        assert (await async_client.get(path)).status_code == 401
        assert (await async_client.get(path, headers=auth("invalid"))).status_code == 401
        assert (await async_client.get(path, headers=expired)).status_code == 401
        assert (await async_client.get(path, headers=updater)).status_code == 403
        assert (await async_client.get(path, headers=reader)).status_code == 200
    assert (await async_client.post(receipts, json=command)).status_code == 401
    assert (await async_client.post(receipts, json=command, headers=auth("invalid"))).status_code == 401
    assert (await async_client.post(receipts, json=command, headers=expired)).status_code == 401
    assert (await async_client.post(receipts, json=command, headers=reader)).status_code == 403
    assert (await async_client.post(receipts, json=command, headers=updater)).status_code == 201

    delete = f"{SHOPPING_LIST}/{added.json()['id']}"
    assert (await async_client.delete(delete, headers=reader)).status_code == 403
    assert (await async_client.delete(delete, headers=updater)).status_code == 204


@pytest.mark.asyncio
async def test_startup_metadata_adds_shopping_list_to_an_existing_database(test_engine, stock_resources):
    metadata = load_all_models()
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("DROP TABLE IF EXISTS warehouse_purchase_orders")
        await conn.exec_driver_sql("DROP TABLE IF EXISTS warehouse_shopping_list_items")
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(metadata.create_all)
        tables = await conn.run_sync(lambda connection: inspect(connection).get_table_names())

    assert {"warehouse_shopping_list_items", "warehouse_purchase_orders"} <= set(tables)
