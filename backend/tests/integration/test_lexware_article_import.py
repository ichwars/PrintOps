from decimal import Decimal

from backend.app.models.project import Project
from backend.app.models.small_part import SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticle
from backend.app.services.lexware_imports import snapshot_hash
from backend.tests.integration.test_lexware_api import BASE, ORG, seed


async def local_article(async_client, db_session, **options):
    db_session.add(SmallPartUnit(code="C62", label="Stück", decimal_places=0))
    await db_session.commit()
    created = await async_client.post(
        "/api/v1/warehouse-articles",
        json={
            "sku": "TEST-WARE",
            "name": "One piece",
            "kind": "finished",
            "unit_code": "C62",
            "sale_price": "1.00",
            "unit_cost": "0.25",
            **options,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


async def test_existing_article_requires_reviewed_unit_and_keeps_purchase_cost(async_client, db_session):
    _, connection, resource = await seed(async_client, db_session)
    resource.kind = "articles"
    resource.payload = {
        "id": resource.external_id,
        "organizationId": ORG,
        "title": "Box of ten",
        "type": "PRODUCT",
        "unitName": "Box of ten",
        "price": {"netPrice": "10.00", "taxRate": "19"},
    }
    resource.version_hash = snapshot_hash(resource.payload)
    await db_session.commit()
    article = await local_article(async_client, db_session)
    preview = await async_client.post(
        f"{BASE}/connections/{connection.id}/preview", json={"resource_id": resource.id, "article_id": article["id"]}
    )
    assert preview.json()["current"]["unit_code"] == "C62"
    assert preview.json()["source"]["unit_name"] == "Box of ten"
    command = {
        "resource_id": resource.id,
        "article_id": article["id"],
        "version_hash": resource.version_hash,
        "local_version": article["version"],
        "fields": ["sale_price"],
    }
    denied = await async_client.post(f"{BASE}/connections/{connection.id}/import", json=command)
    assert denied.status_code == 422
    wrong_unit = await async_client.post(
        f"{BASE}/connections/{connection.id}/import", json={**command, "confirmed_unit_code": "KG"}
    )
    assert wrong_unit.status_code == 422
    accepted = await async_client.post(
        f"{BASE}/connections/{connection.id}/import", json={**command, "confirmed_unit_code": "C62"}
    )
    assert accepted.status_code == 200, accepted.text
    local = await db_session.get(WarehouseArticle, article["id"], populate_existing=True)
    assert local.sale_price == Decimal("10")
    assert local.unit_cost == Decimal("0.25") and local.unit_code == "C62"


async def test_project_reference_blocks_deletion_until_explicitly_removed(async_client, db_session):
    project = Project(name="Warehouse production")
    db_session.add(project)
    await db_session.commit()
    article = await local_article(async_client, db_session, project_id=project.id)
    blocked = await async_client.delete(f"/api/v1/projects/{project.id}")
    assert blocked.status_code == 409, blocked.text
    changed = await async_client.patch(
        f"/api/v1/warehouse-articles/{article['id']}", json={"project_id": None, "version": article["version"]}
    )
    assert changed.status_code == 200, changed.text
    deleted = await async_client.delete(f"/api/v1/projects/{project.id}")
    assert deleted.status_code == 200, deleted.text
