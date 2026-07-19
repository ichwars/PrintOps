from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_supplier_lifecycle_and_normalized_conflict(async_client: AsyncClient):
    payload = {
        "name": "Filament World",
        "contact_name": "Ada Einkauf",
        "email": "orders@example.test",
        "country_code": "DE",
        "default_lead_time_days": 4,
        "is_active": True,
    }
    created = await async_client.post("/api/v1/suppliers", json=payload)
    assert created.status_code == 201, created.text

    duplicate = await async_client.post("/api/v1/suppliers", json={**payload, "name": " filament world "})
    listed = await async_client.get("/api/v1/suppliers", params={"q": "Ada"})
    updated = await async_client.patch(
        f"/api/v1/suppliers/{created.json()['id']}", json={"payment_terms": "14 Tage netto"}
    )

    assert duplicate.status_code == 409
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    assert updated.status_code == 200
    assert updated.json()["payment_terms"] == "14 Tage netto"
    assert created.json()["country_code"] == "DE"


@pytest.mark.asyncio
async def test_supplier_patch_rejects_explicit_null_name(async_client: AsyncClient):
    created = await async_client.post("/api/v1/suppliers", json={"name": "Nullable Name"})
    assert created.status_code == 201

    response = await async_client.patch(
        f"/api/v1/suppliers/{created.json()['id']}",
        json={"name": None},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("offer_active", [True, False])
async def test_supplier_referenced_by_any_offer_cannot_be_deleted(
    async_client: AsyncClient, db_session, offer_active: bool
):
    from backend.app.models.procurement import ProcurementOffer
    from backend.app.models.small_part import SmallPart, SmallPartUnit

    created = await async_client.post("/api/v1/suppliers", json={"name": f"Referenced {offer_active}"})
    assert created.status_code == 201

    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    db_session.add(unit)
    await db_session.flush()
    part = SmallPart(sku=f"SUPPLIER-REF-{offer_active}", name="Referenced part", unit_code=unit.code)
    db_session.add(part)
    await db_session.flush()
    db_session.add(
        ProcurementOffer(
            supplier_id=created.json()["id"],
            small_part_id=part.id,
            resource_key=f"small_part:{part.id}",
            is_active=offer_active,
        )
    )
    await db_session.commit()

    deleted = await async_client.delete(f"/api/v1/suppliers/{created.json()['id']}")

    assert deleted.status_code == 409


@pytest.fixture
async def supplier_permission_tokens(db_session):
    from backend.app.core.auth import create_access_token, get_password_hash
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    db_session.add(Settings(key="auth_enabled", value="true"))
    permissions = {
        "reader": "inventory:read",
        "creator": "inventory:create",
        "updater": "inventory:update",
        "deleter": "inventory:delete",
    }
    users: dict[str, User] = {}
    for name, permission in permissions.items():
        group = Group(name=f"supplier_{name}", permissions=[permission])
        user = User(username=f"supplier_{name}", password_hash=get_password_hash("password"), is_active=True)
        user.groups.append(group)
        db_session.add(user)
        users[name] = user
    await db_session.commit()

    return {name: create_access_token(data={"sub": user.username}) for name, user in users.items()}


@pytest.mark.asyncio
async def test_supplier_routes_require_matching_inventory_permissions(
    async_client: AsyncClient, supplier_permission_tokens: dict[str, str]
):
    headers = {name: {"Authorization": f"Bearer {token}"} for name, token in supplier_permission_tokens.items()}
    payload = {"name": "Permission Supplier"}

    assert (await async_client.get("/api/v1/suppliers", headers=headers["reader"])).status_code == 200
    assert (await async_client.get("/api/v1/suppliers", headers=headers["creator"])).status_code == 403
    assert (await async_client.post("/api/v1/suppliers", json=payload, headers=headers["reader"])).status_code == 403

    created = await async_client.post("/api/v1/suppliers", json=payload, headers=headers["creator"])
    assert created.status_code == 201
    supplier_id = created.json()["id"]

    assert (
        await async_client.patch(
            f"/api/v1/suppliers/{supplier_id}", json={"is_active": False}, headers=headers["creator"]
        )
    ).status_code == 403
    assert (
        await async_client.patch(
            f"/api/v1/suppliers/{supplier_id}", json={"is_active": False}, headers=headers["updater"]
        )
    ).status_code == 200
    assert (
        await async_client.delete(f"/api/v1/suppliers/{supplier_id}", headers=headers["updater"])
    ).status_code == 403
    assert (
        await async_client.delete(f"/api/v1/suppliers/{supplier_id}", headers=headers["deleter"])
    ).status_code == 204
