"""Batch progress and operations use the complete set of assigned printers."""

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def batch_scope(async_client, db_session, printer_factory, archive_factory):
    admin = await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    project = Project(name="Scoped batch project")
    db_session.add(project)
    await db_session.commit()
    allowed = await archive_factory(visible.id, project_id=project.id)
    restricted = await archive_factory(hidden.id, project_id=project.id)
    member = User(
        username="batch_member",
        allowed_printer_ids=[visible.id],
        groups=[
            Group(
                name="Scoped batch access",
                permissions=[
                    "archives:read_all",
                    "archives:reprint_all",
                    "projects:read",
                    "queue:create",
                    "queue:read_all",
                    "queue:update_own",
                    "queue:update_all",
                    "queue:delete_all",
                ],
            )
        ],
    )
    secret, key_hash, prefix = generate_api_key()
    key = APIKey(name="Scoped batches", key_hash=key_hash, key_prefix=prefix, can_queue=True, printer_ids=[visible.id])
    db_session.add_all([member, key])
    await db_session.commit()
    return (
        visible,
        hidden,
        allowed,
        restricted,
        project,
        {"Authorization": f"Bearer {create_access_token({'sub': member.username})}"},
        {"X-API-Key": "invalid", "Authorization": f"Bearer {secret}"},
        {"Authorization": f"Bearer {admin}"},
    )


async def _batch(db, name, *printer_ids):
    batch = PrintBatch(name=name)
    db.add(batch)
    await db.flush()
    for printer_id in printer_ids:
        db.add(PrintQueueItem(batch_id=batch.id, printer_id=printer_id, status="pending"))
    await db.commit()
    return batch


async def test_mixed_batch_is_hidden_on_read_and_write_routes(async_client, db_session, batch_scope):
    visible, hidden, archive, _, _, member, key, admin = batch_scope
    own = await _batch(db_session, "Visible order", visible.id, None)
    mixed = await _batch(db_session, "Mixed order", visible.id, hidden.id)
    base = "/api/v1/queue/batches"

    for credentials in (member, key):
        listing = await async_client.get(base, headers=credentials)
        assert listing.status_code == 200
        assert [batch["id"] for batch in listing.json()] == [own.id]
        path = f"{base}/{mixed.id}"
        for method, suffix, kwargs in (
            ("GET", "", {}),
            ("PATCH", "", {"json": {"name": "Hidden change"}}),
            ("POST", "/dispatch", {"json": {}}),
            ("POST", "/ungroup", {}),
            ("DELETE", "", {}),
        ):
            response = await async_client.request(method, f"{path}{suffix}", headers=credentials, **kwargs)
            assert response.status_code == 404, (method, suffix, response.text)
        denied = await async_client.post(
            "/api/v1/queue/",
            headers=credentials,
            json={"batch_id": mixed.id, "printer_id": visible.id, "archive_id": archive.id},
        )
        assert denied.status_code == 404

    own_response = await async_client.patch(f"{base}/{own.id}", headers=member, json={"name": "Visible change"})
    assert own_response.status_code == 200
    visible_to_admin = await async_client.get(f"{base}/{mixed.id}", headers=admin)
    assert visible_to_admin.json()["name"] == "Mixed order"
    assert (
        len(list(await db_session.scalars(select(PrintQueueItem.id).where(PrintQueueItem.batch_id == mixed.id)))) == 2
    )


async def test_grouping_and_project_previews_apply_selected_printer_scope(async_client, db_session, batch_scope):
    visible, hidden, allowed_archive, _, project, _, key, _ = batch_scope
    visible_job = PrintQueueItem(printer_id=visible.id, status="pending")
    hidden_job = PrintQueueItem(printer_id=hidden.id, status="pending")
    db_session.add_all([visible_job, hidden_job])
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/queue/batches",
        headers=key,
        json={"name": "Group allowed jobs", "item_ids": [visible_job.id, hidden_job.id]},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(visible_job)
    await db_session.refresh(hidden_job)
    assert visible_job.batch_id == response.json()["id"]
    assert hidden_job.batch_id is None

    listing = await async_client.get("/api/v1/projects/", headers=key)
    assert listing.status_code == 200
    card = next(item for item in listing.json() if item["id"] == project.id)
    assert [item["id"] for item in card["archives"]] == [allowed_archive.id]
