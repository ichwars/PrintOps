"""Independent app: these tests do not need parent main.py registration."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes import inventory as inventory_routes, small_parts as material_routes
from backend.app.api.routes.warehouse_articles import router
from backend.app.core.database import Base, get_db
from backend.app.models.location import Location
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry
from backend.app.schemas.warehouse_article import WarehouseArticleCreate, WarehouseMovementCreate
from backend.app.services.small_parts import append_ledger_entry
from backend.app.services.warehouse_articles import WarehouseError, create_article, read_article
from backend.app.services.warehouse_stock import post_movement

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def warehouse_client(test_engine, db_session, monkeypatch):
    db_session.add_all(
        [
            SmallPartUnit(code="C62", label="Stück", decimal_places=0),
            SmallPartUnit(code="KGM", label="kg", decimal_places=6),
            Location(id=1, name="A", name_key="a"),
            Location(id=2, name="B", name_key="b"),
        ]
    )
    await db_session.commit()
    monkeypatch.setattr("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(inventory_routes, "_spool_counts_for_locations", AsyncMock(return_value={}))
    app = FastAPI()
    app.include_router(router)
    app.include_router(material_routes.router)
    app.include_router(inventory_routes.router)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr("backend.app.core.auth.async_session", factory)

    async def get_test_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://warehouse.test") as client:
        yield client


async def article(client, **overrides):
    response = await client.post(
        "/warehouse-articles",
        json={"sku": "WARE-1", "name": "Printed bracket", "kind": "finished", "unit_code": "C62", **overrides},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def move(client, identifier, kind, quantity="1", key=None, **fields):
    data = {
        "entry_kind": kind,
        "reason": "Behavioral test",
        "idempotency_key": key or f"test-{kind}-{quantity}",
        **fields,
    }
    if kind != "counter":
        data.update(quantity=quantity)
        data.setdefault("location_id", 1)
    return await client.post(f"/warehouse-articles/{identifier}/ledger", json=data)


async def test_forecast_counts_only_recent_effective_issues_against_available_stock(warehouse_client, db_session):
    client = warehouse_client
    item = await article(client, minimum_stock="6")
    identifier = item["id"]
    assert (await move(client, identifier, "receipt", "30")).status_code == 201
    assert (await move(client, identifier, "transfer", "3", target_location_id=2)).status_code == 201
    old = await move(client, identifier, "issue", "8")
    assert old.status_code == 201
    assert (await move(client, identifier, "issue", "4")).status_code == 201
    revoked = await move(client, identifier, "issue", "1")
    assert revoked.status_code == 201
    assert (await move(client, identifier, "counter", reverses_id=revoked.json()["id"])).status_code == 201
    reserved = await move(client, identifier, "reservation", "10")
    assert reserved.status_code == 201
    assert (
        await move(client, identifier, "reserved_issue", "2", reservation_id=reserved.json()["id"])
    ).status_code == 201

    await db_session.execute(
        update(WarehouseArticleLedgerEntry)
        .where(WarehouseArticleLedgerEntry.id == old.json()["id"])
        .values(created_at=datetime.now(timezone.utc) - timedelta(days=31))
    )
    await db_session.commit()

    response = await client.get("/warehouse-articles/forecast")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window_days"] == 30
    row = body["items"][0]
    assert row["id"] == identifier
    assert Decimal(row["available"]) == Decimal("8")
    assert Decimal(row["daily_usage"]) == Decimal("0.2")
    assert Decimal(row["projected_available"]) == Decimal("2")
    assert row["days_until_minimum"] == 10


async def test_forecast_uses_material_units_and_distinguishes_missing_usage(warehouse_client, db_session):
    client = warehouse_client
    part = SmallPart(sku="FORECAST-MAT", name="Linked material", unit_code="KGM", location_id=1)
    db_session.add(part)
    await db_session.flush()
    for kind, delta in (("receipt", "4.05"), ("issue", "-0.9"), ("correction", "-0.05")):
        await append_ledger_entry(
            db_session,
            small_part_id=part.id,
            entry_kind=kind,
            physical_delta=Decimal(delta),
            reserved_delta=Decimal(0),
            reason="Forecast test",
            idempotency_key=f"forecast-material-{kind}",
        )
    await db_session.commit()
    linked = await article(
        client, sku="MATERIAL", stock_source="material", small_part_id=part.id, unit_code="KGM", minimum_stock="0.2"
    )
    critical = await article(client, sku="BELOW", minimum_stock="1")
    healthy = await article(client, sku="NO-HISTORY")
    assert (await move(client, healthy["id"], "receipt", "1")).status_code == 201
    await article(client, sku="SERVICE", kind="service", stock_source="none")
    await article(client, sku="ARCHIVED", is_active=False)

    response = await client.get("/warehouse-articles/forecast", params={"limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    below, material = body["items"]
    assert below["id"] == critical["id"] and below["days_until_minimum"] == 0
    assert below["daily_usage"] is None and below["projected_available"] is None
    assert material["id"] == linked["id"] and material["unit_code"] == "KGM"
    assert Decimal(material["available"]) == Decimal("3.1")
    assert Decimal(material["minimum_stock"]) == Decimal("0.2")
    assert Decimal(material["daily_usage"]) == Decimal("0.03")
    assert Decimal(material["projected_available"]) == Decimal("2.2")
    assert material["days_until_minimum"] is None

    response = await client.get("/warehouse-articles/forecast", params={"limit": 2, "offset": 2})
    assert response.status_code == 200, response.text
    (row,) = response.json()["items"]
    assert row["id"] == healthy["id"]
    assert row["daily_usage"] is None and row["days_until_minimum"] is None


async def test_article_sorting_combines_article_and_material_stock_before_pagination(warehouse_client, db_session):
    client = warehouse_client
    own = await article(client, sku="Z-OWN", name="Own", minimum_stock="9")
    for kind, quantity, fields in (
        ("receipt", "12", {}),
        ("transfer", "3", {"target_location_id": 2}),
        ("reservation", "5", {}),
    ):
        response = await move(client, own["id"], kind, quantity, **fields)
        assert response.status_code == 201, response.text

    part = SmallPart(sku="SORT-MAT", name="Linked stock", unit_code="C62", location_id=1)
    db_session.add(part)
    await db_session.flush()
    await append_ledger_entry(
        db_session,
        small_part_id=part.id,
        entry_kind="receipt",
        physical_delta=Decimal("8"),
        reserved_delta=Decimal("0"),
        reason="Stock used for sorting",
        idempotency_key="sort-material-opening",
    )
    await db_session.commit()
    await article(client, sku="A-LINK", name="Linked", kind="trade", stock_source="material", small_part_id=part.id)
    await article(client, sku="B-ZERO", name="Zero", minimum_stock="2")
    await article(client, sku="C-SERVICE", name="Service", kind="service", stock_source="none")

    async def sorted_skus(column, direction, **params):
        response = await client.get("/warehouse-articles", params={"sort_by": column, "sort_dir": direction, **params})
        assert response.status_code == 200, response.text
        body = response.json()
        return [item["sku"] for item in body["items"]], body["total"]

    assert await sorted_skus("sku", "desc", limit=2, offset=1) == (["C-SERVICE", "B-ZERO"], 4)
    assert await sorted_skus("physical", "desc", limit=1, offset=1) == (["A-LINK"], 4)
    assert await sorted_skus("reserved", "desc") == (["Z-OWN", "A-LINK", "B-ZERO", "C-SERVICE"], 4)
    assert await sorted_skus("available", "asc") == (["B-ZERO", "Z-OWN", "A-LINK", "C-SERVICE"], 4)
    assert await sorted_skus("available", "desc", low_stock=True) == (["Z-OWN", "B-ZERO"], 2)
    assert await sorted_skus("minimum_stock", "asc") == (["A-LINK", "B-ZERO", "Z-OWN", "C-SERVICE"], 4)
    assert (await client.get("/warehouse-articles", params={"sort_by": "unknown"})).status_code == 422


async def test_usage_and_stock_checks_follow_the_physical_stock_owner(warehouse_client, db_session):
    client = warehouse_client
    own = await article(client, sku="STOCK-CHECK-OWN")
    assert own["last_used_at"] is None and own["stock_checked_at"] is None
    assert (await move(client, own["id"], "receipt", "10")).status_code == 201
    assert (await move(client, own["id"], "issue", "2")).status_code == 201
    reversed_issue = await move(client, own["id"], "issue", "1")
    assert reversed_issue.status_code == 201
    assert (await move(client, own["id"], "counter", reverses_id=reversed_issue.json()["id"])).status_code == 201

    part = SmallPart(sku="STOCK-CHECK-MAT", name="Material", unit_code="C62", location_id=1)
    spool = Spool(material="PLA")
    db_session.add_all([part, spool])
    await db_session.flush()
    for kind, delta in (("receipt", "9"), ("issue", "-4")):
        await append_ledger_entry(
            db_session,
            small_part_id=part.id,
            entry_kind=kind,
            physical_delta=Decimal(delta),
            reserved_delta=Decimal(0),
            reason="Stocktake test",
            idempotency_key=f"stocktake-{kind}",
        )
    await db_session.commit()
    linked = await article(client, sku="STOCK-CHECK-LINK", stock_source="material", small_part_id=part.id)
    service = await article(client, sku="STOCK-CHECK-SERVICE", kind="service", stock_source="none")
    response = await client.get("/warehouse-articles", params={"sort_by": "consumed", "sort_dir": "desc"})
    rows = response.json()["items"]
    assert [row["id"] for row in rows] == [linked["id"], own["id"], service["id"]]
    assert [Decimal(row["consumed"]) for row in rows] == [Decimal(4), Decimal(2), Decimal(0)]
    assert rows[0]["last_used_at"] and rows[1]["last_used_at"] and rows[2]["last_used_at"] is None

    result = await client.post("/warehouse-articles/stock-check", json={"ids": [own["id"], service["id"]]})
    assert result.status_code == 409
    assert (await client.get(f"/warehouse-articles/{own['id']}")).json()["stock_checked_at"] is None
    result = await client.post("/warehouse-articles/stock-check", json={"ids": [own["id"], linked["id"]]})
    assert result.status_code == 200, result.text
    checked = result.json()["stock_checked_at"]
    updated = (await client.get(f"/small-parts/{part.id}")).json()
    assert updated["stock_checked_at"] == checked
    assert Decimal(updated["consumed"]) == 4 and Decimal(updated["balance"]["physical"]) == 5
    assert (await client.get(f"/warehouse-articles/{linked['id']}")).json()["stock_checked_at"] == checked
    updated_own = (await client.get(f"/warehouse-articles/{own['id']}")).json()
    assert updated_own["stock_checked_at"] == checked and Decimal(updated_own["balance"]["physical"]) == 8

    material_check = await client.post("/small-parts/stock-check", json={"ids": [part.id]})
    assert material_check.status_code == 200
    spool_check = await client.post("/inventory/spools/stock-check", json={"ids": [spool.id]})
    assert spool_check.status_code == 200, spool_check.text
    assert (await client.get(f"/inventory/spools/{spool.id}")).json()["stock_checked_at"] is not None


async def test_warehouse_toolbar_filters_before_pagination(warehouse_client, db_session):
    client = warehouse_client
    used = await article(client, sku="W-FILTER-USED")
    await move(client, used["id"], "receipt", "6")
    await move(client, used["id"], "issue", "2")
    await move(client, used["id"], "transfer", "4", target_location_id=2)
    part = SmallPart(sku="M-FILTER-NEW", name="Linked stock", unit_code="KGM", location_id=1)
    db_session.add(part)
    await db_session.commit()
    new = await article(
        client,
        sku="W-FILTER-LINK",
        kind="trade",
        unit_code="KGM",
        stock_source="material",
        small_part_id=part.id,
    )
    await article(client, sku="W-FILTER-SERVICE", kind="service", stock_source="none")

    async def matches(**params):
        response = await client.get("/warehouse-articles", params=params)
        assert response.status_code == 200, response.text
        page = response.json()
        return [item["id"] for item in page["items"]], page["total"]

    assert await matches(usage="used", location_id=2, unit_code="C62", sort_by="remaining", limit=1) == (
        [used["id"]],
        1,
    )
    assert await matches(usage="used", location_id=1) == ([], 0)
    assert await matches(usage="new", location_id=1, unit_code="KGM") == ([new["id"]], 1)
    assert await matches(usage="new") == ([new["id"]], 1)
    assert await matches(usage="new", offset=1) == ([], 1)
    assert await matches(article_id=used["id"], limit=1) == ([used["id"]], 1)
    assert await matches(article_id=used["id"], offset=1) == ([], 1)


async def test_crud_search_archive_and_price_separation(warehouse_client):
    client = warehouse_client
    created = await article(client, sale_price="12.50", minimum_stock="2")
    assert created["unit_cost"] == "0"
    assert created["balance"]["is_low_stock"]
    identifier = created["id"]
    changed = await client.patch(f"/warehouse-articles/{identifier}", json={"version": 1, "name": "Edited"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert (
        await client.patch(f"/warehouse-articles/{identifier}", json={"version": 1, "name": "Stale"})
    ).status_code == 409
    assert (await client.patch(f"/warehouse-articles/{identifier}", json={"name": "Unversioned"})).status_code == 422
    assert (
        await client.patch(f"/warehouse-articles/{identifier}", json={"version": 2, "name": None})
    ).status_code == 422
    assert (
        await client.get("/warehouse-articles", params={"q": "edit", "kind": "finished", "low_stock": True})
    ).json()["total"] == 1
    assert (await client.get("/warehouse-articles", params={"q": "%"})).json()["total"] == 0
    archived = await client.delete(f"/warehouse-articles/{identifier}?version=2")
    assert archived.status_code == 200
    assert not archived.json()["is_active"]
    assert (await client.get("/warehouse-articles", params={"active": True})).json()["total"] == 0
    assert (await client.get(f"/warehouse-articles/{identifier}")).status_code == 200


async def test_list_sorting_whitelist_and_pagination(warehouse_client):
    client = warehouse_client
    for sku, name, minimum in (("WARE-C", "Charlie", "0"), ("WARE-A", "Alpha", "5"), ("WARE-B", "Bravo", "2")):
        await article(client, sku=sku, name=name, minimum_stock=minimum)
    # Default stays name asc (backwards compatible).
    default = (await client.get("/warehouse-articles")).json()
    assert [row["name"] for row in default["items"]] == ["Alpha", "Bravo", "Charlie"]
    asc = (await client.get("/warehouse-articles", params={"sort_by": "sku", "sort_dir": "asc"})).json()
    assert [row["sku"] for row in asc["items"]] == ["WARE-A", "WARE-B", "WARE-C"]
    desc = (await client.get("/warehouse-articles", params={"sort_by": "sku", "sort_dir": "desc"})).json()
    assert [row["sku"] for row in desc["items"]] == ["WARE-C", "WARE-B", "WARE-A"]
    by_minimum = (
        await client.get("/warehouse-articles", params={"sort_by": "minimum_stock", "sort_dir": "desc"})
    ).json()
    assert [row["sku"] for row in by_minimum["items"]] == ["WARE-A", "WARE-B", "WARE-C"]
    assert [row["minimum_stock"] for row in by_minimum["items"]] == ["5", "2", "0"]
    # Unknown columns are rejected, invalid directions fail validation.
    assert (await client.get("/warehouse-articles", params={"sort_by": "password"})).status_code == 422
    assert (await client.get("/warehouse-articles", params={"sort_by": "unsupported-column"})).status_code == 422
    assert (await client.get("/warehouse-articles", params={"sort_dir": "sideways"})).status_code == 422
    # Pagination stays consistent with the requested ordering.
    page1 = (await client.get("/warehouse-articles", params={"sort_by": "sku", "limit": 2, "offset": 0})).json()
    page2 = (await client.get("/warehouse-articles", params={"sort_by": "sku", "limit": 2, "offset": 2})).json()
    assert [row["sku"] for row in page1["items"]] == ["WARE-A", "WARE-B"]
    assert [row["sku"] for row in page2["items"]] == ["WARE-C"]
    assert page1["total"] == page2["total"] == 3
    assert page1["limit"] == 2 and page2["offset"] == 2


async def test_low_stock_branch_and_balance_sorting(warehouse_client):
    client = warehouse_client
    low_a = await article(client, sku="LOW-A", name="Low A", minimum_stock="10")
    low_b = await article(client, sku="LOW-B", name="Low B", minimum_stock="10")
    ok = await article(client, sku="OK", name="Plenty", minimum_stock="0")
    assert (await move(client, low_a["id"], "receipt", "2", key="low-a-receipt")).status_code == 201
    assert (await move(client, low_b["id"], "receipt", "5", key="low-b-receipt")).status_code == 201
    assert (await move(client, ok["id"], "receipt", "9", key="ok-receipt")).status_code == 201
    # low_stock loads and filters in Python; balance columns must still sort there.
    asc = await client.get("/warehouse-articles", params={"low_stock": True, "sort_by": "physical", "sort_dir": "asc"})
    assert asc.status_code == 200, asc.text
    assert [row["sku"] for row in asc.json()["items"]] == ["LOW-A", "LOW-B"]
    desc = await client.get(
        "/warehouse-articles", params={"low_stock": True, "sort_by": "physical", "sort_dir": "desc"}
    )
    assert [row["sku"] for row in desc.json()["items"]] == ["LOW-B", "LOW-A"]
    reserved_desc = await client.get(
        "/warehouse-articles", params={"low_stock": True, "sort_by": "reserved", "sort_dir": "desc"}
    )
    assert reserved_desc.status_code == 200, reserved_desc.text
    # Balance columns are sortable in the paginated DB branch as well.
    normal = await client.get("/warehouse-articles", params={"sort_by": "available", "sort_dir": "desc"})
    assert normal.status_code == 200, normal.text
    rows = normal.json()["items"]
    assert [row["sku"] for row in rows] == ["OK", "LOW-B", "LOW-A"]
    assert [row["balance"]["available"] for row in rows] == ["9", "5", "2"]
    # low_stock pagination slices the sorted, filtered rows.
    paged = await client.get(
        "/warehouse-articles",
        params={"low_stock": True, "sort_by": "physical", "sort_dir": "desc", "limit": 1, "offset": 1},
    )
    assert [row["sku"] for row in paged.json()["items"]] == ["LOW-A"]
    assert paged.json()["total"] == 2


async def test_reservations_transfers_and_counter_entries(warehouse_client):
    client = warehouse_client
    item = await article(client)
    identifier = item["id"]
    opening = await move(client, identifier, "opening", "10")
    assert opening.status_code == 201, opening.text
    reserved = await move(client, identifier, "reservation", "7")
    assert reserved.status_code == 201, reserved.text
    reservation_id = reserved.json()["id"]
    for kind in ("issue", "transfer"):
        rejected = await move(
            client, identifier, kind, "4", **({"target_location_id": 2} if kind == "transfer" else {})
        )
        assert rejected.status_code == 409
    assert (await move(client, identifier, "transfer", "3", target_location_id=2)).status_code == 201
    issued = await move(client, identifier, "reserved_issue", "4", reservation_id=reservation_id)
    assert issued.status_code == 201
    assert (await move(client, identifier, "release", "4", reservation_id=reservation_id)).status_code == 409
    assert (await move(client, identifier, "release", "3", reservation_id=reservation_id)).status_code == 201
    detail = (await client.get(f"/warehouse-articles/{identifier}")).json()
    assert detail["balance"]["physical"] == "6"
    assert detail["balance"]["reserved"] == "0"
    assert [row["physical"] for row in detail["locations"]] == ["3", "3"]
    assert (await client.delete(f"/warehouse-articles/{identifier}?version={detail['version']}")).status_code == 409
    assert (
        await client.patch(f"/warehouse-articles/{identifier}", json={"version": detail["version"], "unit_code": "KGM"})
    ).status_code == 409
    assert (
        await move(client, identifier, "counter", key="undo-opening", reverses_id=opening.json()["id"])
    ).status_code == 409
    undone = await move(client, identifier, "counter", key="undo-issue", reverses_id=issued.json()["id"])
    assert undone.status_code == 201, undone.text
    assert (
        await move(client, identifier, "counter", key="undo-issue-again", reverses_id=issued.json()["id"])
    ).status_code == 409
    reservations = (await client.get(f"/warehouse-articles/{identifier}/reservations")).json()
    assert reservations == [{"id": reservation_id, "location_id": 1, "order_id": None, "remaining": "4"}]


async def test_idempotency_payload_and_actor_conflicts(warehouse_client, db_session):
    client = warehouse_client
    item = await article(client)
    first = await move(client, item["id"], "receipt", "10", key="receipt-replay")
    replay = await move(client, item["id"], "receipt", "10.0", key="receipt-replay")
    assert first.json()["id"] == replay.json()["id"]
    assert (await move(client, item["id"], "receipt", "9", key="receipt-replay")).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(WarehouseArticleLedgerEntry)) == 1
    with pytest.raises(WarehouseError, match="anderen"):
        await post_movement(
            db_session,
            item["id"],
            WarehouseMovementCreate(
                entry_kind="receipt",
                quantity="10",
                location_id=1,
                reason="Behavioral test",
                idempotency_key="receipt-replay",
            ),
            actor_id=99,
        )
    await db_session.rollback()


async def test_transfer_reverse_is_atomic_and_ledger_immutable(warehouse_client, db_session):
    client = warehouse_client
    item = await article(client)
    await move(client, item["id"], "receipt", "5")
    transfer = await move(client, item["id"], "transfer", "5", target_location_id=2)
    await move(client, item["id"], "issue", "1", location_id=2)
    assert (
        await move(client, item["id"], "counter", key="undo-transfer", reverses_id=transfer.json()["id"])
    ).status_code == 409
    body = (await client.get(f"/warehouse-articles/{item['id']}")).json()
    assert [row["physical"] for row in body["locations"]] == ["0", "4"]
    entry = await db_session.get(WarehouseArticleLedgerEntry, transfer.json()["id"])
    entry.reason = "Tampered"
    with pytest.raises(ValueError, match="cannot be changed"):
        await db_session.flush()
    await db_session.rollback()


async def test_services_units_and_material_single_stock_source(warehouse_client, db_session):
    client = warehouse_client
    service = await article(client, sku="SVC", kind="service", stock_source="none")
    assert (await move(client, service["id"], "receipt")).status_code == 409
    assert (
        await client.post(
            "/warehouse-articles", json={"sku": "INVALID", "name": "Unknown", "kind": "trade", "unit_code": "unmapped"}
        )
    ).status_code == 422
    part = SmallPart(sku="MAT", name="Material", unit_code="C62", location_id=1)
    db_session.add(part)
    await db_session.flush()
    await append_ledger_entry(
        db_session,
        small_part_id=part.id,
        entry_kind="receipt",
        physical_delta=Decimal(9),
        reserved_delta=Decimal(0),
        reason="Existing",
        idempotency_key="material-existing",
    )
    await db_session.commit()
    linked = await article(client, sku="LINK", kind="trade", stock_source="material", small_part_id=part.id)
    assert linked["balance"]["physical"] == "9.000000"
    assert linked["has_history"]
    assert (await move(client, linked["id"], "receipt")).status_code == 409
    duplicate = await client.post(
        "/warehouse-articles",
        json={
            "sku": "LINK2",
            "name": "Duplicate",
            "kind": "trade",
            "unit_code": "C62",
            "stock_source": "material",
            "small_part_id": part.id,
        },
    )
    assert duplicate.status_code == 409
    assert (
        await client.patch(
            f"/warehouse-articles/{linked['id']}", json={"version": 1, "stock_source": "own", "small_part_id": None}
        )
    ).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(SmallPartLedgerEntry)) == 1
    assert await db_session.scalar(select(func.count()).select_from(WarehouseArticleLedgerEntry)) == 0


async def test_exact_decimal_and_unit_precision(warehouse_client):
    client = warehouse_client
    whole = await article(client)
    assert (await move(client, whole["id"], "receipt", "0.5")).status_code == 422
    item = await article(client, sku="WEIGHT", unit_code="KGM")
    for n in range(3):
        assert (await move(client, item["id"], "receipt", "0.1", key=f"decimal-{n}")).status_code == 201
    assert (await move(client, item["id"], "issue", "0.3")).status_code == 201
    assert Decimal((await client.get(f"/warehouse-articles/{item['id']}")).json()["balance"]["physical"]) == 0
    assert (await move(client, item["id"], "receipt", "0.0000001")).status_code == 422
    assert (await move(client, item["id"], "receipt", "NaN")).status_code == 422


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "", None),
        ("get", "/forecast", None),
        ("get", "/1", None),
        ("get", "/1/ledger", None),
        ("get", "/1/reservations", None),
        ("post", "", {"sku": "DENIED", "name": "No", "unit_code": "C62", "kind": "trade"}),
        ("post", "/stock-check", {"ids": [1]}),
        ("patch", "/1", {"version": 1, "name": "No"}),
        ("delete", "/1?version=1", None),
        (
            "post",
            "/1/ledger",
            {
                "entry_kind": "receipt",
                "quantity": "1",
                "location_id": 1,
                "reason": "Denied",
                "idempotency_key": "denied-booking",
            },
        ),
    ],
)
async def test_every_endpoint_requires_permission(warehouse_client, monkeypatch, method, path, payload):
    monkeypatch.setattr("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True))
    response = await warehouse_client.request(method, "/warehouse-articles" + path, json=payload)
    assert response.status_code in (401, 403), response.text


async def test_concurrent_reservations_are_serialized_on_file_sqlite(tmp_path, test_engine):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'warehouse-concurrency.db'}", connect_args={"timeout": 10}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def pragmas(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [SmallPartUnit(code="C62", label="Piece", decimal_places=0), Location(id=1, name="A", name_key="a")]
        )
        await session.flush()
        item = await create_article(
            session, WarehouseArticleCreate(sku="RACE", name="Race", kind="trade", unit_code="C62")
        )
        identifier = item.id
        await post_movement(
            session,
            identifier,
            WarehouseMovementCreate(
                entry_kind="opening", quantity=10, location_id=1, reason="Opening", idempotency_key="race-opening"
            ),
        )
        await session.commit()

    async def reserve(key):
        async with factory() as session:
            try:
                await post_movement(
                    session,
                    identifier,
                    WarehouseMovementCreate(
                        entry_kind="reservation", quantity=7, location_id=1, reason="Reserve", idempotency_key=key
                    ),
                )
                await session.commit()
                return "ok"
            except WarehouseError as exc:
                await session.rollback()
                return exc.code

    try:
        assert sorted(await asyncio.gather(reserve("race-first"), reserve("race-second"))) == [
            "insufficient_stock",
            "ok",
        ]
        async with factory() as session:
            current = await session.get(WarehouseArticle, identifier)
            result = await read_article(session, current)
            assert result.balance.available == Decimal(3)
            assert result.balance.reserved == Decimal(7)
    finally:
        await engine.dispose()


async def test_references_are_protected_with_sqlite_foreign_keys_off(warehouse_client, db_session):
    assert (await db_session.scalar(text("PRAGMA foreign_keys"))) == 0
    client = warehouse_client
    item = await article(client)
    await move(client, item["id"], "receipt", "2")
    await move(client, item["id"], "transfer", "2", target_location_id=2)
    for location_id in (1, 2):
        response = await client.delete(f"/inventory/locations/{location_id}")
        assert response.status_code == 409, response.text
    assert (await client.delete("/small-parts/settings/units/C62")).status_code == 409
    assert (await client.patch("/small-parts/settings/units/C62", json={"decimal_places": 2})).status_code == 409
    assert (await client.patch("/small-parts/settings/units/C62", json={"label": "Pieces"})).status_code == 200
    assert (await client.delete("/small-parts/settings/units/KGM")).status_code == 204
    assert await db_session.get(Location, 1) is not None


async def test_material_identity_and_location_remain_valid_for_linked_article(warehouse_client, db_session):
    client = warehouse_client
    part = SmallPart(sku="SOURCE", name="Stock source", unit_code="C62", location_id=1)
    db_session.add(part)
    await db_session.commit()
    await article(client, stock_source="material", small_part_id=part.id)
    for changes in ({"unit_code": "KGM"}, {"is_active": False}):
        response = await client.patch(f"/small-parts/{part.id}", json=changes)
        assert response.status_code == 409, response.text
    assert (await client.delete("/inventory/locations/1")).status_code == 409
    response = await client.post(
        "/small-parts/import",
        files={
            "file": (
                "linked.csv",
                b"Artikelnummer;Bezeichnung;Einheit;Aktiv\nSOURCE;Stock source;C62;false\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["errors"] == 1
    await db_session.refresh(part)
    assert part.is_active
    assert part.unit_code == "C62"


async def test_authenticated_reader_cannot_mutate_and_actor_is_recorded(warehouse_client, db_session, monkeypatch):
    from backend.app.core.auth import create_access_token
    from backend.app.models.group import Group
    from backend.app.models.user import User

    client = warehouse_client
    item = await article(client)
    reader_group = Group(name="warehouse-reader", permissions=["inventory:read"])
    writer_group = Group(name="warehouse-writer", permissions=["inventory:read", "inventory:update"])
    reader = User(username="warehouse-reader", password_hash="unused-test-hash", is_active=True, groups=[reader_group])
    writer = User(username="warehouse-writer", password_hash="unused-test-hash", is_active=True, groups=[writer_group])
    db_session.add_all([reader, writer])
    await db_session.commit()
    monkeypatch.setattr("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True))
    client.headers["Authorization"] = f"Bearer {create_access_token(data={'sub': reader.username})}"
    assert (await client.get("/warehouse-articles")).status_code == 200
    assert (
        await client.patch(f"/warehouse-articles/{item['id']}", json={"version": 1, "name": "Denied"})
    ).status_code == 403
    assert (await move(client, item["id"], "receipt")).status_code == 403
    for path in ("/warehouse-articles/stock-check", "/small-parts/stock-check", "/inventory/spools/stock-check"):
        assert (await client.post(path, json={"ids": [item["id"]]})).status_code == 403
    client.headers["Authorization"] = f"Bearer {create_access_token(data={'sub': writer.username})}"
    response = await move(client, item["id"], "receipt")
    assert response.status_code == 201, response.text
    assert response.json()["actor_id"] == writer.id


@pytest.mark.parametrize("can_archive", [False, True], ids=["update-only", "update-and-delete"])
async def test_patch_archival_requires_delete_permission(warehouse_client, db_session, monkeypatch, can_archive):
    from backend.app.core.auth import create_access_token
    from backend.app.models.group import Group
    from backend.app.models.user import User

    item = await article(warehouse_client)
    group = Group(name="warehouse-updater", permissions=["inventory:read", "inventory:update"])
    if can_archive:
        group.permissions = [*group.permissions, "inventory:delete"]
    user = User(username="warehouse-updater", password_hash="unused-test-hash", is_active=True, groups=[group])
    db_session.add(user)
    await db_session.commit()
    monkeypatch.setattr("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True))
    warehouse_client.headers["Authorization"] = f"Bearer {create_access_token(data={'sub': user.username})}"

    renamed = await warehouse_client.patch(
        f"/warehouse-articles/{item['id']}", json={"version": item["version"], "name": "Allowed rename"}
    )
    assert renamed.status_code == 200, renamed.text
    archived = await warehouse_client.patch(
        f"/warehouse-articles/{item['id']}", json={"version": renamed.json()["version"], "is_active": False}
    )

    assert archived.status_code == (200 if can_archive else 403), archived.text
    stored = await db_session.get(WarehouseArticle, item["id"])
    assert stored.is_active is not can_archive
    assert stored.version == renamed.json()["version"] + int(can_archive)
