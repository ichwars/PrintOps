from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.models.customer import Customer
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.services import lexware_connections as connections
from backend.app.services.lexware_imports import snapshot_hash
from backend.tests.integration.test_business_profiles_api import create_permission_user, create_profile
from backend.tests.integration.test_customers_api import customer_payload

BASE = "/api/v1/lexware"
ORG = "12345678-1234-4234-8234-123456789abc"


@pytest.mark.parametrize(
    "suffix,body",
    [
        ("", {"api_key": "private-test-key", "business_profile_id": 1}),
        ("/test", {"api_key": {"secret": "private-test-key"}}),
        ("/test", {"api_key": "private-test-key", "unexpected": "private-test-key"}),
    ],
)
async def test_invalid_credential_requests_never_echo_raw_inputs(async_client, suffix, body):
    result = await async_client.post(f"{BASE}/connections{suffix}", json=body)
    assert result.status_code == 422
    assert "private-test-key" not in result.text
    assert all("input" not in item for item in result.json()["detail"])


async def test_retained_lexware_links_prevent_deleting_local_owners(async_client, db_session):
    _, connection, resource = await seed(async_client, db_session)
    other = await create_profile(async_client, name="Linked profile", is_default=False)
    connection.business_profile_id = other["id"]
    await db_session.commit()
    profile_delete = await async_client.delete(f"/api/v1/business-profiles/{other['id']}")
    assert profile_delete.status_code == 409, profile_delete.text
    imported = await async_client.post(
        f"{BASE}/connections/{connection.id}/import",
        json={"resource_id": resource.id, "version_hash": resource.version_hash, "fields": ["identity"]},
    )
    assert imported.status_code == 200, imported.text
    customer_delete = await async_client.delete(f"/api/v1/customers/{imported.json()['customer_id']}")
    assert customer_delete.status_code == 409, customer_delete.text


@pytest.fixture
def mock_profile(monkeypatch):
    monkeypatch.setattr(
        connections, "test_api_key", AsyncMock(return_value={"organization_id": ORG, "company_name": "Lexware test"})
    )


async def seed(async_client, db_session):
    profile = await create_profile(async_client)
    connection = LexwareConnection(
        business_profile_id=profile["id"], organization_id=ORG, company_name="Test", encrypted_api_key="fernet:test"
    )
    db_session.add(connection)
    await db_session.flush()
    payload = {
        "id": str(uuid4()),
        "organizationId": ORG,
        "roles": {"customer": {"number": 50001}},
        "company": {"name": "Imported customer"},
        "addresses": {"billing": [{"street": "Teststr. 1", "zip": "10115", "city": "Berlin", "countryCode": "DE"}]},
    }
    resource = LexwareResource(
        connection_id=connection.id,
        kind="contacts",
        external_id=payload["id"],
        payload=payload,
        version_hash=snapshot_hash(payload),
    )
    db_session.add(resource)
    await db_session.commit()
    return profile, connection, resource


async def test_connection_encrypts_key_and_disconnect_preserves_data(async_client, db_session, mock_profile):
    profile = await create_profile(async_client)
    created = await async_client.post(
        f"{BASE}/connections",
        json={"business_profile_id": profile["id"], "organization_id": ORG, "api_key": "private-upstream-key"},
    )
    assert created.status_code == 201, created.text
    assert "private-upstream-key" not in created.text and "encrypted_api_key" not in created.text
    row = await db_session.get(LexwareConnection, created.json()["id"])
    assert row.encrypted_api_key.startswith("fernet:")
    assert connections.decrypt_api_key(row) == "private-upstream-key"
    result = await async_client.delete(f"{BASE}/connections/{row.id}")
    assert result.status_code == 204
    await db_session.refresh(row)
    assert row.encrypted_api_key is None and not row.enabled
    assert row.sync_status == "disconnected"


async def test_contact_import_is_explicit_idempotent_and_adopts_customer_number(async_client, db_session):
    profile, connection, resource = await seed(async_client, db_session)
    preview = await async_client.post(f"{BASE}/connections/{connection.id}/preview", json={"resource_id": resource.id})
    assert preview.status_code == 200, preview.text
    assert preview.json()["source"]["customer_number"] == "50001"
    assert await db_session.scalar(select(func.count(Customer.id))) == 0
    body = {
        "resource_id": resource.id,
        "version_hash": resource.version_hash,
        "local_version": None,
        "fields": ["identity", "addresses", "customer_number"],
    }
    first = await async_client.post(f"{BASE}/connections/{connection.id}/import", json=body)
    assert first.status_code == 200, first.text
    again = await async_client.post(f"{BASE}/connections/{connection.id}/import", json=body)
    assert again.json()["unchanged"] is True
    assert again.json()["customer_id"] == first.json()["customer_id"]
    local = (await async_client.get(f"/api/v1/customers/{first.json()['customer_id']}")).json()
    assert local["accounts"][0]["number"] == "50001"
    assert local["addresses"][0]["city"] == "Berlin"


async def test_customer_updates_preserve_notes_tags_accounts_and_reject_stale_preview(async_client, db_session):
    profile, connection, resource = await seed(async_client, db_session)
    original = customer_payload(profile["id"])
    created = await async_client.post("/api/v1/customers/", json=original)
    assert created.status_code == 201, created.text
    customer = created.json()
    preview = await async_client.post(
        f"{BASE}/connections/{connection.id}/preview", json={"resource_id": resource.id, "customer_id": customer["id"]}
    )
    assert preview.status_code == 200, preview.text
    body = {
        "resource_id": resource.id,
        "version_hash": resource.version_hash,
        "local_version": customer["version"],
        "customer_id": customer["id"],
        "fields": ["identity"],
    }
    stale = await async_client.post(
        f"{BASE}/connections/{connection.id}/import", json={**body, "version_hash": "0" * 64}
    )
    assert stale.status_code == 409
    result = await async_client.post(f"{BASE}/connections/{connection.id}/import", json=body)
    assert result.status_code == 200, result.text
    updated = (await async_client.get(f"/api/v1/customers/{customer['id']}")).json()
    assert updated["notes"] == customer["notes"]
    assert updated["tags"] == customer["tags"]
    assert updated["addresses"] == customer["addresses"]
    assert updated["accounts"] == customer["accounts"]
    assert updated["display_name"] == "Imported customer"
    conflict = await async_client.post(
        f"{BASE}/connections/{connection.id}/import", json={**body, "fields": ["contacts"]}
    )
    assert conflict.status_code == 409


async def test_accounting_admin_without_customer_access_cannot_read_or_import(async_client, db_session):
    profile, connection, resource = await seed(async_client, db_session)
    token = await create_permission_user(
        db_session, username="integration-only", permissions=["accounting_integrations:manage"]
    )
    headers = {"Authorization": f"Bearer {token}"}
    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        resources = await async_client.get(
            f"{BASE}/connections/{connection.id}/resources?kind=contacts", headers=headers
        )
        assert resources.status_code == 403
        preview = await async_client.post(
            f"{BASE}/connections/{connection.id}/preview", headers=headers, json={"resource_id": resource.id}
        )
        assert preview.status_code == 403


async def test_archived_contact_is_not_imported(async_client, db_session):
    _, connection, resource = await seed(async_client, db_session)
    resource.payload = {**resource.payload, "archived": True}
    resource.version_hash = snapshot_hash(resource.payload)
    await db_session.commit()
    result = await async_client.post(
        f"{BASE}/connections/{connection.id}/import",
        json={"resource_id": resource.id, "version_hash": resource.version_hash, "fields": ["identity"]},
    )
    assert result.status_code == 409
    assert await db_session.scalar(select(func.count(Customer.id))) == 0
