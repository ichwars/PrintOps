from datetime import timedelta
from decimal import Decimal

import pytest

from backend.app.core.auth import create_access_token, generate_api_key, get_password_hash
from backend.app.core.database import get_db
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.group import Group
from backend.app.models.location import Location
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.settings import Settings
from backend.app.models.small_part import SmallPartUnit
from backend.app.models.user import User
from backend.app.models.warehouse_article import WarehouseArticle

PROJECTS = "/api/v1/projects"
ARTICLES = "/api/v1/warehouse-articles"


@pytest.fixture
def client(async_client, monkeypatch):
    from backend.app.main import app

    # The shared client rolls back uncommitted writes. Project routes rely on
    # the normal request dependency to commit or roll back the whole request.
    monkeypatch.delitem(app.dependency_overrides, get_db)
    return async_client


@pytest.fixture
async def destination(db_session):
    location = Location(name="Finished stock", name_key="finished stock")
    article = WarehouseArticle(
        sku="FINISHED-1",
        name="Finished article",
        kind="finished",
        stock_source="own",
        unit_code="C62",
        minimum_stock=Decimal(6),
    )
    if await db_session.get(SmallPartUnit, "C62") is None:
        db_session.add(SmallPartUnit(code="C62", label="Piece", decimal_places=0))
        await db_session.flush()
    db_session.add_all([location, article])
    await db_session.commit()
    return {"article_id": article.id, "location_id": location.id}


@pytest.mark.asyncio
async def test_completion_books_good_parts_once(client, db_session, destination):
    created = await client.post(f"{PROJECTS}/", json={"name": "Production", "target_parts_count": 9})
    assert created.status_code == 200
    project_id = created.json()["id"]
    project_url = f"{PROJECTS}/{project_id}"
    article_url = f"{ARTICLES}/{destination['article_id']}"
    bound = await client.patch(project_url, json={"production_output": destination})
    assert bound.status_code == 200, bound.text
    assert bound.json()["production_output"] == destination

    run = PrintLogEntry(project_id=project_id, quantity=8, status="completed", confirm_requested=True)
    db_session.add_all([run, PrintLogEntry(project_id=project_id, quantity=2, status="failed")])
    await db_session.commit()

    before = (await client.get(article_url)).json()["balance"]
    assert Decimal(before["available"]) == 0 and before["is_low_stock"]
    pending = await client.patch(project_url, json={"status": "completed"})
    assert pending.status_code == 409
    assert (await client.get(project_url)).json()["status"] == "active"
    assert (await client.get(f"{article_url}/ledger")).json() == []

    run.good_quantity = 6
    run.reject_quantity = 2
    await db_session.commit()
    for status in ("completed", "completed", "active", "completed"):
        response = await client.patch(project_url, json={"status": status})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status

    after = (await client.get(article_url)).json()["balance"]
    assert Decimal(after["available"]) == Decimal(after["physical"]) == 6
    assert not after["is_low_stock"]
    [entry] = (await client.get(f"{article_url}/ledger")).json()
    assert entry["entry_kind"] == "receipt" and Decimal(entry["physical_delta"]) == 6
    assert entry["location_id"] == destination["location_id"]
    assert f"Projekt #{project_id}" in entry["reason"] and f"Drucklauf #{run.id}" in entry["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("historical", [False, True])
async def test_booking_prevents_later_changes_to_the_received_quantity(client, db_session, destination, historical):
    created = await client.post(f"{PROJECTS}/", json={"name": "Production", "production_output": destination})
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    archive = PrintArchive(filename="project.3mf", file_path="project.3mf", file_size=1, status="completed", quantity=8)
    db_session.add(archive)
    await db_session.flush()
    run = PrintLogEntry(archive_id=archive.id, project_id=project_id, quantity=8, status="completed")
    db_session.add(run)
    await db_session.commit()
    outcome_path = f"/api/v1/archives/{archive.id}"
    if historical:
        outcome_path += f"/runs/{run.id}"
    outcome_path += "/outcome"
    original = {"run_id": run.id, "good_quantity": 6, "reject_quantity": 2}
    assert (await client.post(outcome_path, json=original)).status_code == 200
    completed = await client.patch(f"{PROJECTS}/{project_id}", json={"status": "completed"})
    assert completed.status_code == 200, completed.text

    corrected = await client.post(outcome_path, json={**original, "good_quantity": 4, "reject_quantity": 4})
    assert corrected.status_code == 409, corrected.text
    await db_session.refresh(run)
    assert (run.good_quantity, run.reject_quantity) == (6, 2)
    [entry] = (await client.get(f"{ARTICLES}/{destination['article_id']}/ledger")).json()
    assert Decimal(entry["physical_delta"]) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("clear_from_archive", [False, True])
async def test_cleanup_retains_only_stock_booked_runs(
    client, db_session, destination, archive_factory, printer_factory, clear_from_archive
):
    created = await client.post(f"{PROJECTS}/", json={"name": "Production", "production_output": destination})
    project_id = created.json()["id"]
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    booked = PrintLogEntry(
        archive_id=archive.id, project_id=project_id, quantity=6, good_quantity=6, reject_quantity=0, status="completed"
    )
    other = PrintLogEntry(archive_id=archive.id, quantity=1, status="completed")
    db_session.add_all([booked, other])
    await db_session.commit()
    booked_id, other_id = booked.id, other.id

    completed = await client.patch(f"{PROJECTS}/{project_id}", json={"status": "completed"})
    assert completed.status_code == 200, completed.text
    protected = await client.delete(f"/api/v1/print-log/{booked_id}")
    assert protected.status_code == 409, protected.text
    if clear_from_archive:
        cleared = await client.delete(f"/api/v1/archives/{archive.id}?purge_stats=true")
        assert cleared.status_code == 200, cleared.text
    else:
        cleared = await client.delete("/api/v1/print-log/")
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["deleted"] == 1
    assert await db_session.get(PrintLogEntry, booked_id, populate_existing=True) is not None
    assert await db_session.get(PrintLogEntry, other_id, populate_existing=True) is None
    [entry] = (await client.get(f"{ARTICLES}/{destination['article_id']}/ledger")).json()
    assert Decimal(entry["physical_delta"]) == 6


@pytest.mark.asyncio
async def test_project_editor_needs_inventory_write_for_linked_production(client, db_session, destination):
    created = await client.post(f"{PROJECTS}/", json={"name": "Production", "production_output": destination})
    assert created.json()["production_output"] == destination
    project_url = f"{PROJECTS}/{created.json()['id']}"
    db_session.add(Settings(key="auth_enabled", value="true"))
    editor = User(username="project_editor", password_hash=get_password_hash("test password"), is_active=True)
    editor.groups.append(Group(name="Project editors", permissions=["projects:create", "projects:update"]))
    db_session.add(editor)
    await db_session.commit()

    valid = create_access_token({"sub": editor.username})
    expired = create_access_token({"sub": editor.username}, expires_delta=-timedelta(minutes=5))
    for token, code in [(None, 401), ("invalid", 401), (expired, 401), (valid, 403)]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        assert (await client.patch(project_url, json={"status": "completed"}, headers=headers)).status_code == code
        assert (
            await client.post(
                f"{PROJECTS}/",
                json={"name": "Production", "production_output": destination},
                headers=headers,
            )
        ).status_code == code

    updated = await client.patch(
        project_url, json={"notes": "Production note"}, headers={"Authorization": f"Bearer {valid}"}
    )
    assert updated.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("projects, inventory, expected", [(True, False, 403), (False, True, 403), (True, True, 200)])
async def test_api_key_requires_both_scopes_to_set_production_destination(
    client, db_session, destination, projects, inventory, expected
):
    key, digest, prefix = generate_api_key()
    db_session.add_all(
        [
            Settings(key="auth_enabled", value="true"),
            APIKey(
                name="Automation",
                key_hash=digest,
                key_prefix=prefix,
                can_manage_projects=projects,
                can_manage_inventory=inventory,
            ),
        ]
    )
    await db_session.commit()

    response = await client.post(
        f"{PROJECTS}/",
        json={"name": "Production", "production_output": destination},
        headers={"X-API-Key": key},
    )
    assert response.status_code == expected, response.text
