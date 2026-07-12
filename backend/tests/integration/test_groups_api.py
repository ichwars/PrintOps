"""Integration tests for the /api/v1/groups/* endpoints.

Issue #1083: updates to a group's permission list must persist across GET,
regardless of whether the frontend invalidates its React Query cache.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models.group import Group

ORDER_MANAGEMENT_PERMISSIONS = {
    "customers:read",
    "customers:manage",
    "calculations:read",
    "calculations:update",
    "calculations:approve",
    "orders:read",
    "orders:update",
    "orders:cancel",
    "orders:manage_production",
    "commercial_documents:read",
    "commercial_documents:draft",
    "commercial_documents:approve",
    "commercial_documents:issue",
    "commercial_documents:correct",
    "commercial_documents:export",
    "payments:read",
    "payments:manage",
    "order_audit:read",
    "order_settings:read",
    "order_settings:manage",
    "accounting_integrations:manage",
}


async def _setup_admin(async_client: AsyncClient) -> dict[str, str]:
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "gadmin", "admin_password": "AdminPass1!"},
    )
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "gadmin", "password": "AdminPass1!"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_order_management_permission_category_contract(async_client: AsyncClient):
    headers = await _setup_admin(async_client)

    response = await async_client.get("/api/v1/groups/permissions", headers=headers)

    assert response.status_code == 200
    categories = {category["name"]: category["permissions"] for category in response.json()["categories"]}
    order_permissions = [permission["value"] for permission in categories["Order Management"]]
    assert len(order_permissions) == len(ORDER_MANAGEMENT_PERMISSIONS)
    assert set(order_permissions) == ORDER_MANAGEMENT_PERMISSIONS


@pytest.mark.asyncio
@pytest.mark.integration
async def test_order_permission_backfill_is_additive_and_idempotent(async_client: AsyncClient, db_session):
    from backend.app.core.database import seed_default_groups

    expected_operator_permissions = {
        "customers:read",
        "customers:manage",
        "calculations:read",
        "calculations:update",
        "calculations:approve",
        "orders:read",
        "orders:update",
        "orders:manage_production",
        "commercial_documents:read",
        "commercial_documents:draft",
        "commercial_documents:approve",
        "payments:read",
        "order_audit:read",
    }
    expected_viewer_permissions = {
        "customers:read",
        "calculations:read",
        "orders:read",
        "commercial_documents:read",
        "payments:read",
        "order_audit:read",
    }
    result = await db_session.execute(select(Group).where(Group.name.in_(("Operators", "Viewers"))))
    groups = {group.name: group for group in result.scalars().all()}
    groups["Operators"].permissions = ["printers:read", "custom:operator"]
    groups["Viewers"].permissions = ["system:read", "custom:viewer"]
    db_session.add(
        Group(
            name="Order Specialists",
            description="Custom order permissions",
            permissions=["custom:specialist"],
            is_system=False,
        )
    )
    await db_session.commit()

    await seed_default_groups()
    db_session.expire_all()

    result = await db_session.execute(
        select(Group).where(Group.name.in_(("Operators", "Viewers", "Order Specialists")))
    )
    first_pass = {group.name: list(group.permissions) for group in result.scalars().all()}

    assert set(first_pass["Operators"]) & ORDER_MANAGEMENT_PERMISSIONS == expected_operator_permissions
    assert set(first_pass["Viewers"]) & ORDER_MANAGEMENT_PERMISSIONS == expected_viewer_permissions
    assert "custom:operator" in first_pass["Operators"]
    assert "custom:viewer" in first_pass["Viewers"]
    assert first_pass["Order Specialists"] == ["custom:specialist"]

    await seed_default_groups()
    db_session.expire_all()

    result = await db_session.execute(
        select(Group).where(Group.name.in_(("Operators", "Viewers", "Order Specialists")))
    )
    second_pass = {group.name: list(group.permissions) for group in result.scalars().all()}
    assert second_pass == first_pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_group_permissions_persists(async_client: AsyncClient, db_session):
    """PATCH /groups/{id} with a new permissions list must persist to DB (#1083)."""
    headers = await _setup_admin(async_client)

    create = await async_client.post(
        "/api/v1/groups/",
        headers=headers,
        json={
            "name": "test_perms",
            "permissions": ["printers:read", "archives:read", "queue:read", "inventory:read"],
        },
    )
    assert create.status_code == 201
    gid = create.json()["id"]

    # Update to a wholly different set
    update = await async_client.patch(
        f"/api/v1/groups/{gid}",
        headers=headers,
        json={"permissions": ["users:read", "groups:read"]},
    )
    assert update.status_code == 200
    assert sorted(update.json()["permissions"]) == ["groups:read", "users:read"]

    # Re-read via API — must reflect the update, not the creation
    got = await async_client.get(f"/api/v1/groups/{gid}", headers=headers)
    assert got.status_code == 200
    assert sorted(got.json()["permissions"]) == ["groups:read", "users:read"]

    # Direct DB read — same expectation
    result = await db_session.execute(select(Group).where(Group.id == gid))
    assert sorted(result.scalar_one().permissions or []) == ["groups:read", "users:read"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_group_to_empty_permissions(async_client: AsyncClient, db_session):
    """Clearing all permissions via PATCH must result in an empty list, not a no-op."""
    headers = await _setup_admin(async_client)

    create = await async_client.post(
        "/api/v1/groups/",
        headers=headers,
        json={"name": "test_clear", "permissions": ["printers:read", "archives:read"]},
    )
    gid = create.json()["id"]

    update = await async_client.patch(
        f"/api/v1/groups/{gid}",
        headers=headers,
        json={"permissions": []},
    )
    assert update.status_code == 200
    assert update.json()["permissions"] == []

    got = await async_client.get(f"/api/v1/groups/{gid}", headers=headers)
    assert got.json()["permissions"] == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_group_without_permissions_field_preserves_existing(async_client: AsyncClient, db_session):
    """PATCH without a permissions field (None) must leave the existing list untouched."""
    headers = await _setup_admin(async_client)

    create = await async_client.post(
        "/api/v1/groups/",
        headers=headers,
        json={"name": "test_preserve", "permissions": ["printers:read", "archives:read"]},
    )
    gid = create.json()["id"]

    # Only update description
    update = await async_client.patch(
        f"/api/v1/groups/{gid}",
        headers=headers,
        json={"description": "updated"},
    )
    assert update.status_code == 200
    assert sorted(update.json()["permissions"]) == ["archives:read", "printers:read"]
    assert update.json()["description"] == "updated"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_group_invalid_permission_rejected(async_client: AsyncClient):
    """Invalid permission strings yield 400 and do not persist."""
    headers = await _setup_admin(async_client)

    create = await async_client.post(
        "/api/v1/groups/",
        headers=headers,
        json={"name": "test_bad", "permissions": ["printers:read"]},
    )
    gid = create.json()["id"]

    update = await async_client.patch(
        f"/api/v1/groups/{gid}",
        headers=headers,
        json={"permissions": ["printers:read", "bogus:permission"]},
    )
    assert update.status_code == 400
    assert "Invalid permissions" in update.json()["detail"]

    # Existing value unchanged
    got = await async_client.get(f"/api/v1/groups/{gid}", headers=headers)
    assert got.json()["permissions"] == ["printers:read"]
