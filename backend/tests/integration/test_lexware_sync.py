from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core import database
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.services import lexware_documents, lexware_sync
from backend.app.services.lexware_client import LexwareError
from backend.tests.integration.test_lexware_api import seed


@pytest.mark.parametrize("other_org", [False, True])
async def test_articles_may_omit_organization_but_never_claim_another(async_client, db_session, monkeypatch, other_org):
    _, connection, resource = await seed(async_client, db_session)
    monkeypatch.setattr(database, "async_session", async_sessionmaker(db_session.bind, expire_on_commit=False))
    monkeypatch.setattr(lexware_sync, "decrypt_api_key", lambda _: "fake")
    article = {"id": "32345678-1234-4234-8234-123456789abc", "title": "Article", "type": "PRODUCT"}
    if other_org:
        article["organizationId"] = "42345678-1234-4234-8234-123456789abc"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_pages(self, path, params=None):
            return [article] if path == "/v1/articles" else [resource.payload]

    monkeypatch.setattr(lexware_sync, "LexwareClient", FakeClient)
    monkeypatch.setattr(lexware_documents, "fetch_vouchers", AsyncMock(return_value=[]))
    await lexware_sync.sync_connection(connection.id)
    await db_session.refresh(connection)
    stored = await db_session.scalar(select(LexwareResource).where(LexwareResource.external_id == article["id"]))
    assert connection.sync_status == ("error" if other_org else "success")
    assert (stored is not None) is not other_org


async def configure(monkeypatch, db_session, connection, resource, *, fail=False, disconnect=False):
    monkeypatch.setattr(database, "async_session", async_sessionmaker(db_session.bind, expire_on_commit=False))
    monkeypatch.setattr(lexware_sync, "decrypt_api_key", lambda _: "fake")
    changed = {**resource.payload, "company": {"name": "Updated upstream"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.guard = kwargs["before_request"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_pages(self, path, params=None):
            await self.guard()
            if fail and path == "/v1/articles":
                raise LexwareError("simulated unavailable service")
            return [changed] if path == "/v1/contacts" else []

    async def vouchers(client):
        if disconnect:
            async with database.async_session() as db:
                await db.execute(
                    update(LexwareConnection)
                    .where(LexwareConnection.id == connection.id)
                    .values(
                        enabled=False,
                        encrypted_api_key=None,
                        version=LexwareConnection.version + 1,
                        sync_status="disconnected",
                    )
                )
                await db.commit()
        return []

    monkeypatch.setattr(lexware_sync, "LexwareClient", FakeClient)
    monkeypatch.setattr(lexware_documents, "fetch_vouchers", vouchers)
    return changed


async def test_success_publishes_snapshot_but_does_not_create_customer(async_client, db_session, monkeypatch):
    _, connection, resource = await seed(async_client, db_session)
    await configure(monkeypatch, db_session, connection, resource)
    await lexware_sync.sync_connection(connection.id)
    await db_session.refresh(resource)
    await db_session.refresh(connection)
    assert resource.payload["company"]["name"] == "Updated upstream"
    assert resource.customer_id is None
    assert connection.sync_status == "success" and connection.last_success_at
    response = await async_client.get("/api/v1/lexware/connections")
    assert response.json()[0]["last_success_at"].endswith("Z")
    response = await async_client.get(f"/api/v1/lexware/connections/{connection.id}/resources?kind=contacts")
    assert response.json()[0]["updated_at"].endswith(("Z", "+00:00"))


async def test_partial_failure_preserves_entire_previous_snapshot(async_client, db_session, monkeypatch):
    _, connection, resource = await seed(async_client, db_session)
    digest = resource.version_hash
    await configure(monkeypatch, db_session, connection, resource, fail=True)
    await lexware_sync.sync_connection(connection.id)
    await db_session.refresh(resource)
    await db_session.refresh(connection)
    assert resource.version_hash == digest
    assert resource.payload["company"]["name"] == "Imported customer"
    assert connection.sync_status == "error" and connection.last_success_at is None


async def test_disconnect_during_fetch_prevents_late_publication(async_client, db_session, monkeypatch):
    _, connection, resource = await seed(async_client, db_session)
    digest = resource.version_hash
    await configure(monkeypatch, db_session, connection, resource, disconnect=True)
    await lexware_sync.sync_connection(connection.id)
    await db_session.refresh(resource)
    await db_session.refresh(connection)
    assert resource.version_hash == digest
    assert connection.sync_status == "disconnected" and connection.encrypted_api_key is None


async def test_unreadable_credentials_report_error_without_discarding_snapshot(async_client, db_session, monkeypatch):
    _, connection, resource = await seed(async_client, db_session)
    monkeypatch.setattr(database, "async_session", async_sessionmaker(db_session.bind, expire_on_commit=False))
    digest = resource.version_hash
    # The deliberately invalid encrypted test key must not escape as an unhandled background-task error.
    await lexware_sync.sync_connection(connection.id)
    await db_session.refresh(connection)
    await db_session.refresh(resource)
    assert connection.sync_status == "error"
    assert "decrypt" in connection.last_error
    assert resource.version_hash == digest
