from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from starlette.requests import Request

from backend.app.api.routes import lexware as lexware_routes
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.warehouse_article import WarehouseArticle
from backend.app.schemas.lexware import LexwareImportRequest
from backend.app.services import warehouse_articles
from backend.app.services.lexware_imports import snapshot_hash
from backend.tests.integration.test_customers_api import customer_payload
from backend.tests.integration.test_lexware_api import BASE, ORG, seed
from backend.tests.integration.test_lexware_article_import import local_article


@pytest.mark.parametrize("existing_customer", [False, True])
async def test_customer_import_uses_profile_defaults_only_for_new_customers(
    async_client, db_session, existing_customer
):
    profile, connection, resource = await seed(async_client, db_session)
    profile_row = await db_session.get(BusinessProfile, profile["id"])
    profile_row.default_currency = "CHF"
    profile_row.default_locale = "fr-CH"
    await db_session.commit()

    customer = None
    if existing_customer:
        payload = customer_payload(profile["id"])
        payload["preferred_locale"] = "en-GB"
        payload["accounts"][0]["preferred_currency"] = "USD"
        created = await async_client.post("/api/v1/customers/", json=payload)
        assert created.status_code == 201, created.text
        customer = created.json()

    imported = await async_client.post(
        f"{BASE}/connections/{connection.id}/import",
        json={
            "resource_id": resource.id,
            "version_hash": resource.version_hash,
            "customer_id": customer["id"] if customer else None,
            "local_version": customer["version"] if customer else None,
            "fields": ["identity", "customer_number"],
        },
    )
    assert imported.status_code == 200, imported.text
    local = (await async_client.get(f"/api/v1/customers/{imported.json()['customer_id']}")).json()
    assert local["preferred_locale"] == ("en-GB" if customer else "fr-CH")
    assert local["accounts"][0]["preferred_currency"] == ("USD" if customer else "CHF")
    assert local["accounts"][0]["number"] == "50001"
    if customer:
        assert local["accounts"] == [{**customer["accounts"][0], "number": "50001"}]


async def test_article_import_preserves_stale_version_and_rolls_back(async_client, db_session, monkeypatch):
    _, connection, resource = await seed(async_client, db_session)
    resource.kind = "articles"
    resource.payload = {
        "id": resource.external_id,
        "organizationId": ORG,
        "title": "Updated article",
        "type": "PRODUCT",
        "unitName": "Piece",
        "price": {"netPrice": "10.00", "taxRate": "19"},
    }
    resource.version_hash = snapshot_hash(resource.payload)
    await db_session.commit()
    article = await local_article(async_client, db_session)
    connection_id, resource_id = connection.id, resource.id
    command = LexwareImportRequest(
        resource_id=resource_id,
        article_id=article["id"],
        version_hash=resource.version_hash,
        local_version=article["version"],
        fields=["sale_price"],
        confirmed_unit_code="C62",
    )
    real_update = warehouse_articles.update_article

    async def update_after_version_change(db, article_id, data):
        # Advance the persisted version between the import and article checks.
        # Keep this staged in the request transaction to also verify rollback.
        await db.execute(
            update(WarehouseArticle)
            .where(WarehouseArticle.id == article_id)
            .values(version=WarehouseArticle.version + 1)
            .execution_options(synchronize_session=False)
        )
        return await real_update(db, article_id, data)

    monkeypatch.setattr(warehouse_articles, "update_article", update_after_version_change)
    monkeypatch.setattr(lexware_routes, "_require", AsyncMock())
    # Invoke the endpoint without request teardown masking a missing rollback.
    with pytest.raises(HTTPException) as raised:
        await lexware_routes.import_resource(
            connection_id,
            command,
            Request({"type": "http", "headers": []}),
            db=db_session,
            _=None,
        )

    assert raised.value.status_code == 409
    assert raised.value.detail == {
        "code": "stale_version",
        "message": "Artikel wurde geändert. Bitte neu laden",
    }
    assert not db_session.in_transaction()
    persisted = await db_session.get(WarehouseArticle, article["id"])
    assert persisted.version == article["version"]
    assert persisted.sale_price == Decimal(article["sale_price"])
    await db_session.refresh(resource)
    assert resource.article_id is None
    assert resource.imported_hash is None
    assert resource.imported_baseline == {}
