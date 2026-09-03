import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.routes import lexware as lexware_routes
from backend.app.core.database import Base
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import Customer
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.models.number_sequence import NumberSequence
from backend.app.schemas.lexware import ConnectionCreate
from backend.app.services import business_profile as business_profile_service, lexware_connections as connections
from backend.app.services.lexware_imports import snapshot_hash
from backend.app.services.order_errors import ResourceInUseError
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


@pytest.mark.parametrize("first", ["create", "delete"])
async def test_connection_creation_serializes_with_profile_deletion_on_sqlite(tmp_path, first):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'lexware-profile-race.db'}", connect_args={"timeout": 2}
    )
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA journal_mode=WAL"))
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 0
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as setup_session:
        profile = BusinessProfile(
            name="Lexware race",
            legal_name="Lexware Race GmbH",
            country_code="DE",
            default_currency="EUR",
            timezone="Europe/Berlin",
            default_locale="de-DE",
            billing_mode="hybrid",
            is_default=False,
            is_active=True,
        )
        setup_session.add(profile)
        await setup_session.flush()
        setup_session.add(
            NumberSequence(
                business_profile_id=profile.id,
                key="customer",
                prefix="CUST",
                pattern="{PREFIX}-{#####}",
            )
        )
        await setup_session.commit()
        profile_id = profile.id
        profile_updated_at = profile.updated_at

    commit_pending = asyncio.Event()
    allow_commit = asyncio.Event()

    class PausingCommitSession(AsyncSession):
        async def commit(self):
            commit_pending.set()
            await allow_commit.wait()
            await super().commit()

    pausing_factory = async_sessionmaker(engine, class_=PausingCommitSession, expire_on_commit=False)
    contender_started = asyncio.Event()

    async def create_connection():
        async with (pausing_factory if first == "create" else factory)() as session:
            if first != "create":
                contender_started.set()
            return await lexware_routes.create_connection(
                ConnectionCreate(
                    business_profile_id=profile_id,
                    organization_id=ORG,
                    api_key="private-upstream-key",
                ),
                db=session,
                _=None,
            )

    async def delete_profile():
        async with (pausing_factory if first == "delete" else factory)() as session:
            if first != "delete":
                contender_started.set()
            await business_profile_service.delete_business_profile(session, profile_id)
            await session.commit()

    tasks = []
    try:
        with (
            patch.object(connections, "encrypt_api_key", return_value="fernet:test"),
            patch.object(
                connections,
                "test_api_key",
                AsyncMock(return_value={"organization_id": ORG, "company_name": "Lexware test"}),
            ),
        ):
            operations = {"create": create_connection, "delete": delete_profile}
            second = "delete" if first == "create" else "create"
            tasks.append(asyncio.create_task(operations[first]()))
            await asyncio.wait_for(commit_pending.wait(), timeout=2)
            tasks.append(asyncio.create_task(operations[second]()))
            await asyncio.wait_for(contender_started.wait(), timeout=2)
            completed, _ = await asyncio.wait({tasks[1]}, timeout=0.2)
            allow_commit.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=3)
            outcomes = dict(zip((first, second), results, strict=True))

        assert not completed, "the competing operation bypassed the uncommitted transaction"
        async with factory() as verify_session:
            stored_profile = await verify_session.get(BusinessProfile, profile_id)
            stored_connection = await verify_session.scalar(
                select(LexwareConnection.id).where(LexwareConnection.business_profile_id == profile_id)
            )
            if first == "create":
                assert outcomes["create"].business_profile_id == profile_id
                assert isinstance(outcomes["delete"], ResourceInUseError)
                assert stored_profile is not None and stored_connection is not None
                assert stored_profile.version == 1 and stored_profile.updated_at == profile_updated_at
            else:
                assert outcomes["delete"] is None
                assert isinstance(outcomes["create"], HTTPException)
                assert outcomes["create"].status_code == 409
                assert stored_profile is None and stored_connection is None
    finally:
        allow_commit.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


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


@pytest.mark.parametrize(
    ("permission", "allowed_kind", "denied_kind"),
    [
        ("customers:read", "contacts", "articles"),
        ("inventory:read", "articles", "contacts"),
    ],
)
async def test_resource_reads_keep_kind_specific_permissions(
    async_client, db_session, permission, allowed_kind, denied_kind
):
    _, connection, _ = await seed(async_client, db_session)
    token = await create_permission_user(
        db_session,
        username=f"{allowed_kind}-reader",
        permissions=[permission],
    )
    headers = {"Authorization": f"Bearer {token}"}

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        allowed = await async_client.get(
            f"{BASE}/connections/{connection.id}/resources?kind={allowed_kind}", headers=headers
        )
        denied = await async_client.get(
            f"{BASE}/connections/{connection.id}/resources?kind={denied_kind}", headers=headers
        )

    assert allowed.status_code == 200, allowed.text
    assert denied.status_code == 403


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
