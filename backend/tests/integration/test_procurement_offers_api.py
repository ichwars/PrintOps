from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.small_part import SmallPart, SmallPartUnit


@pytest.fixture
async def procurement_resources(db_session):
    unit = SmallPartUnit(code="C62", label="Piece", decimal_places=0)
    parts = [
        SmallPart(sku="PROC-A", name="Procurement A", unit_code="C62", unit_cost=Decimal("1.25")),
        SmallPart(sku="PROC-B", name="Procurement B", unit_code="C62", unit_cost=Decimal("2.50")),
    ]
    suppliers = [
        Supplier(name="Alpha Supply", name_key="alpha supply", default_lead_time_days=6),
        Supplier(name="Beta Supply", name_key="beta supply", default_lead_time_days=9),
    ]
    db_session.add_all([unit, *parts, *suppliers])
    await db_session.commit()
    return {
        "material_ids": [part.id for part in parts],
        "supplier_ids": [supplier.id for supplier in suppliers],
    }


def material_resource(material_id: int) -> dict[str, object]:
    return {"kind": "material", "small_part_id": material_id}


async def replace_material_offers(
    client: AsyncClient,
    material_id: int,
    supplier_ids: list[int],
) -> list[dict[str, object]]:
    response = await client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(material_id),
            "offers": [
                {
                    "supplier_id": supplier_ids[0],
                    "net_price": "4.20",
                    "gross_price": "4.99",
                    "is_preferred": True,
                },
                {
                    "supplier_id": supplier_ids[1],
                    "net_price": "4.10",
                    "gross_price": "4.88",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_replaces_material_offers_with_one_preferred(async_client, procurement_resources):
    material_id = procurement_resources["material_ids"][0]
    supplier_ids = procurement_resources["supplier_ids"]

    offers = await replace_material_offers(async_client, material_id, supplier_ids)

    assert sum(item["is_preferred"] for item in offers) == 1
    assert all(item["resource_key"] == f"material:{material_id}" for item in offers)
    assert offers[0]["supplier"]["name"] == "Alpha Supply"
    assert offers[1]["lead_time_days"] == 9


@pytest.mark.asyncio
async def test_filament_descriptor_reuses_sku_identity(async_client, procurement_resources):
    descriptor = {
        "kind": "filament",
        "material": "PLA",
        "subtype": "Matte",
        "brand": "Poly",
        "color_name": "Black",
    }
    first = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": descriptor,
            "offers": [{"supplier_id": procurement_resources["supplier_ids"][0], "is_preferred": True}],
        },
    )
    second = await async_client.get(
        "/api/v1/procurement-offers",
        params={key: value for key, value in descriptor.items() if key != "kind"} | {"kind": "filament"},
    )

    assert first.status_code == second.status_code == 200
    assert second.json()[0]["id"] == first.json()[0]["id"]
    assert second.json()[0]["resource_key"].startswith("filament:")


@pytest.mark.asyncio
async def test_get_missing_filament_resource_returns_empty_without_creating_settings(
    async_client, db_session
):
    response = await async_client.get(
        "/api/v1/procurement-offers",
        params={"kind": "filament", "material": "PETG", "brand": "None Yet"},
    )

    assert response.status_code == 200
    assert response.json() == []
    assert await db_session.scalar(select(func.count(FilamentSkuSettings.id))) == 0


@pytest.mark.asyncio
async def test_replacement_soft_deactivates_omitted_offer(async_client, procurement_resources):
    material_id = procurement_resources["material_ids"][0]
    created = await replace_material_offers(
        async_client, material_id, procurement_resources["supplier_ids"]
    )

    replaced = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={"resource": material_resource(material_id), "offers": []},
    )
    inactive = await async_client.get(
        "/api/v1/procurement-offers",
        params={"kind": "material", "small_part_id": material_id, "active": False},
    )

    assert replaced.status_code == 200
    assert replaced.json() == []
    assert {item["id"] for item in inactive.json()} == {item["id"] for item in created}
    assert all(item["is_active"] is False and item["is_preferred"] is False for item in inactive.json())


@pytest.mark.asyncio
async def test_replacement_rejects_offer_id_from_another_resource_transactionally(
    async_client, procurement_resources
):
    first_id, second_id = procurement_resources["material_ids"]
    supplier_id = procurement_resources["supplier_ids"][0]
    first = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(first_id),
            "offers": [{"supplier_id": supplier_id, "net_price": "7.00", "is_preferred": True}],
        },
    )
    assert first.status_code == 200, first.text

    rejected = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(second_id),
            "offers": [
                {
                    "id": first.json()[0]["id"],
                    "supplier_id": supplier_id,
                    "net_price": "99.00",
                    "is_preferred": True,
                }
            ],
        },
    )
    unchanged = await async_client.get(
        "/api/v1/procurement-offers",
        params={"kind": "material", "small_part_id": first_id},
    )

    assert rejected.status_code == 422
    assert unchanged.json()[0]["net_price"] == "7.000000"


@pytest.mark.asyncio
async def test_replacement_rejects_multiple_active_preferred_offers(async_client, procurement_resources):
    response = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(procurement_resources["material_ids"][0]),
            "offers": [
                {"supplier_id": supplier_id, "is_preferred": True}
                for supplier_id in procurement_resources["supplier_ids"]
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_soft_deactivates_offer(async_client, db_session, procurement_resources):
    created = await replace_material_offers(
        async_client,
        procurement_resources["material_ids"][0],
        procurement_resources["supplier_ids"],
    )

    response = await async_client.delete(f"/api/v1/procurement-offers/{created[0]['id']}")
    db_session.expire_all()
    stored = await db_session.get(ProcurementOffer, created[0]["id"])

    assert response.status_code == 204
    assert stored is not None
    assert stored.is_active is False
    assert stored.is_preferred is False


@pytest.mark.asyncio
async def test_material_unit_cost_tracks_only_active_preferred_net_price(
    async_client, db_session, procurement_resources
):
    material_id = procurement_resources["material_ids"][0]
    supplier_id = procurement_resources["supplier_ids"][0]
    preferred = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(material_id),
            "offers": [{"supplier_id": supplier_id, "net_price": "3.75", "is_preferred": True}],
        },
    )
    db_session.expire_all()
    part = await db_session.get(SmallPart, material_id)
    assert preferred.status_code == 200
    assert part.unit_cost == Decimal("3.750000")

    no_preferred = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": material_resource(material_id),
            "offers": [
                {
                    "id": preferred.json()[0]["id"],
                    "supplier_id": supplier_id,
                    "net_price": "8.00",
                    "is_preferred": False,
                }
            ],
        },
    )
    await db_session.refresh(part)
    assert no_preferred.status_code == 200
    assert part.unit_cost == Decimal("3.750000")


@pytest.fixture
async def procurement_permission_tokens(db_session):
    from backend.app.core.auth import create_access_token, get_password_hash
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    db_session.add(Settings(key="auth_enabled", value="true"))
    permissions = {
        "reader": "inventory:read",
        "updater": "inventory:update",
        "deleter": "inventory:delete",
    }
    users: dict[str, User] = {}
    for name, permission in permissions.items():
        group = Group(name=f"procurement_{name}", permissions=[permission])
        user = User(username=f"procurement_{name}", password_hash=get_password_hash("password"), is_active=True)
        user.groups.append(group)
        db_session.add(user)
        users[name] = user
    await db_session.commit()
    return {name: create_access_token(data={"sub": user.username}) for name, user in users.items()}


@pytest.mark.asyncio
async def test_procurement_offer_routes_require_matching_inventory_permissions(
    async_client,
    procurement_resources,
    procurement_permission_tokens,
):
    headers = {
        name: {"Authorization": f"Bearer {token}"}
        for name, token in procurement_permission_tokens.items()
    }
    material_id = procurement_resources["material_ids"][0]
    payload = {
        "resource": material_resource(material_id),
        "offers": [{"supplier_id": procurement_resources["supplier_ids"][0], "is_preferred": True}],
    }

    assert (
        await async_client.get(
            "/api/v1/procurement-offers",
            params={"kind": "material", "small_part_id": material_id},
            headers=headers["reader"],
        )
    ).status_code == 200
    assert (
        await async_client.get(
            "/api/v1/procurement-offers",
            params={"kind": "material", "small_part_id": material_id},
            headers=headers["updater"],
        )
    ).status_code == 403
    assert (
        await async_client.put(
            "/api/v1/procurement-offers/resource", json=payload, headers=headers["reader"]
        )
    ).status_code == 403

    created = await async_client.put(
        "/api/v1/procurement-offers/resource", json=payload, headers=headers["updater"]
    )
    assert created.status_code == 200, created.text
    offer_id = created.json()[0]["id"]
    assert (
        await async_client.delete(
            f"/api/v1/procurement-offers/{offer_id}", headers=headers["updater"]
        )
    ).status_code == 403
    assert (
        await async_client.delete(
            f"/api/v1/procurement-offers/{offer_id}", headers=headers["deleter"]
        )
    ).status_code == 204
