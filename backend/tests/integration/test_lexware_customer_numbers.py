"""Customer number adoption is explicit, profile-scoped and collision safe."""

from copy import deepcopy

import pytest
from sqlalchemy import func, select

from backend.app.models.customer import Customer
from backend.app.services.lexware_imports import snapshot_hash
from backend.tests.integration.test_business_profiles_api import create_profile
from backend.tests.integration.test_customers_api import customer_payload
from backend.tests.integration.test_lexware_api import BASE, seed


async def import_fields(client, connection, resource, fields, **target):
    return await client.post(
        f"{BASE}/connections/{connection.id}/import",
        json={"resource_id": resource.id, "version_hash": resource.version_hash, "fields": fields, **target},
    )


async def test_linked_customer_can_adopt_number_without_changing_other_accounts_or_children(async_client, db_session):
    profile, connection, resource = await seed(async_client, db_session)
    other = await create_profile(async_client, name="Second profile", is_default=False)
    original = customer_payload(profile["id"])
    original["accounts"][0]["number"] = "LOCAL-1"
    original["accounts"].append({"business_profile_id": other["id"], "number": "OTHER-2", "preferred_currency": "EUR"})
    created = await async_client.post("/api/v1/customers/", json=original)
    assert created.status_code == 201, created.text
    customer = created.json()
    linked = await import_fields(
        async_client, connection, resource, [], customer_id=customer["id"], local_version=customer["version"]
    )
    assert linked.status_code == 200, linked.text
    before = (await async_client.get(f"/api/v1/customers/{customer['id']}")).json()
    preview = await async_client.post(f"{BASE}/connections/{connection.id}/preview", json={"resource_id": resource.id})
    assert {"field": "customer_number", "current": "LOCAL-1", "incoming": "50001"} in preview.json()["changes"]
    result = await import_fields(
        async_client, connection, resource, ["customer_number"], local_version=before["version"]
    )
    assert result.status_code == 200, result.text
    after = (await async_client.get(f"/api/v1/customers/{customer['id']}")).json()
    expected_accounts = deepcopy(before["accounts"])
    next(account for account in expected_accounts if account["business_profile_id"] == profile["id"])["number"] = (
        "50001"
    )
    assert after["accounts"] == expected_accounts
    for field in ("display_name", "notes", "tags", "addresses", "contacts", "tax_identifiers"):
        assert after[field] == before[field]
    assert after["version"] == before["version"] + 1
    listed = await async_client.get(
        "/api/v1/customers/", params={"business_profile_id": profile["id"], "search": "50001"}
    )
    assert listed.json()["items"][0]["account_number"] == "50001"
    stale = await import_fields(
        async_client, connection, resource, ["customer_number", "identity"], local_version=before["version"]
    )
    assert stale.status_code == 409


@pytest.mark.parametrize("existing", [False, True])
async def test_duplicate_number_does_not_create_or_modify_customer(async_client, db_session, existing):
    profile, connection, resource = await seed(async_client, db_session)
    occupied = customer_payload(profile["id"])
    occupied["accounts"][0]["number"] = "50001"
    assert (await async_client.post("/api/v1/customers/", json=occupied)).status_code == 201
    target = {}
    if existing:
        created = await async_client.post("/api/v1/customers/", json=customer_payload(profile["id"]))
        customer = created.json()
        target = {"customer_id": customer["id"], "local_version": customer["version"]}
    result = await import_fields(async_client, connection, resource, ["identity", "customer_number"], **target)
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "customer_number_conflict"
    assert await db_session.scalar(select(func.count(Customer.id))) == (2 if existing else 1)
    if existing:
        assert (await async_client.get(f"/api/v1/customers/{customer['id']}")).json() == customer
    await db_session.refresh(resource)
    assert resource.customer_id is None


async def test_unselected_number_uses_local_sequence(async_client, db_session):
    _, connection, resource = await seed(async_client, db_session)
    result = await import_fields(async_client, connection, resource, ["identity"])
    assert result.status_code == 200, result.text
    local = (await async_client.get(f"/api/v1/customers/{result.json()['customer_id']}")).json()
    assert local["accounts"][0]["number"] != "50001"


@pytest.mark.parametrize("number", [None, "", " " * 3])
async def test_missing_number_cannot_clear_local_number(async_client, db_session, number):
    profile, connection, resource = await seed(async_client, db_session)
    resource.payload = {**resource.payload, "roles": {"customer": {"number": number}}}
    resource.version_hash = snapshot_hash(resource.payload)
    await db_session.commit()
    created = await async_client.post("/api/v1/customers/", json=customer_payload(profile["id"]))
    customer = created.json()
    result = await import_fields(
        async_client,
        connection,
        resource,
        ["customer_number"],
        customer_id=customer["id"],
        local_version=customer["version"],
    )
    assert result.status_code == 422
    assert (await async_client.get(f"/api/v1/customers/{customer['id']}")).json() == customer
