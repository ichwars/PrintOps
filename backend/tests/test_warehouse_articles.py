"""Independent app: these tests do not need parent main.py registration."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes import inventory as inventory_routes, small_parts as material_routes
from backend.app.api.routes.warehouse_articles import router
from backend.app.core.database import Base, get_db
from backend.app.models.location import Location
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
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
        ("get", "/1", None),
        ("get", "/1/ledger", None),
        ("get", "/1/reservations", None),
        ("post", "", {"sku": "DENIED", "name": "No", "unit_code": "C62", "kind": "trade"}),
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
    client.headers["Authorization"] = f"Bearer {create_access_token(data={'sub': writer.username})}"
    response = await move(client, item["id"], "receipt")
    assert response.status_code == 201, response.text
    assert response.json()["actor_id"] == writer.id
