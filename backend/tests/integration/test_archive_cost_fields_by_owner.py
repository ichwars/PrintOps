"""Protect archive estimates that feed the cost of later runs."""

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def account(async_client, db_session):
    admin = await _setup_admin(async_client)
    owner = User(
        username="archive-owner",
        groups=[
            Group(
                name="Edit owned archives",
                permissions=[Permission.ARCHIVES_READ_OWN.value, Permission.ARCHIVES_UPDATE_OWN.value],
            )
        ],
    )
    db_session.add(owner)
    await db_session.commit()
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': owner.username})}"}
    return owner, owner_headers, {"Authorization": f"Bearer {admin}"}


async def test_owner_cannot_overwrite_or_clear_an_estimate(async_client, archive_factory, account):
    owner, headers, admin = account
    archive = await archive_factory(None, with_run=False, created_by_id=owner.id, filament_used_grams=100, cost=2.5)
    path = f"/api/v1/archives/{archive.id}"
    for body in ({"cost": 0.01}, {"cost": None}, {"filament_used_grams": 400}, {"filament_used_grams": None}):
        response = await async_client.patch(path, headers=headers, json={**body, "notes": "Uncommitted"})
        assert response.status_code == 403

    edited = await async_client.patch(path, headers=headers, json={"filament_used_grams": 100, "notes": "Allowed"})
    assert edited.status_code == 200
    assert (edited.json()["filament_used_grams"], edited.json()["cost"], edited.json()["notes"]) == (
        100,
        2.5,
        "Allowed",
    )
    assert (await async_client.patch(path, headers=admin, json={"filament_used_grams": 200})).status_code == 200
    repriced = await async_client.patch(path, headers=admin, json={"cost": 9.99})
    assert (repriced.json()["filament_used_grams"], repriced.json()["cost"]) == (200, 9.99)


@pytest.mark.parametrize("source", [None, "source.3mf"])
async def test_missing_weight_can_only_be_filled_without_a_reprint_source(
    async_client, archive_factory, account, source
):
    owner, headers, _ = account
    archive = await archive_factory(
        None,
        with_run=False,
        created_by_id=owner.id,
        filament_used_grams=None,
        cost=7.0,
        file_path="",
        source_3mf_path=source,
    )
    response = await async_client.patch(
        f"/api/v1/archives/{archive.id}", headers=headers, json={"filament_used_grams": 120}
    )
    assert response.status_code == (403 if source else 200)
    if source is None:
        assert (response.json()["filament_used_grams"], response.json()["cost"]) == (120, 7.0)


async def test_owned_api_key_does_not_inherit_all_archive_cost_rights(
    async_client, db_session, archive_factory, account
):
    owner, _, _ = account
    archive = await archive_factory(None, with_run=False, created_by_id=owner.id, filament_used_grams=100, cost=2.5)
    key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Archive automation",
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=owner.id,
            can_manage_archives=True,
        )
    )
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/archives/{archive.id}", headers={"X-API-Key": key}, json={"cost": 0.01}
    )
    assert response.status_code == 403
