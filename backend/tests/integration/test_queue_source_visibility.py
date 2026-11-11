"""Queue and webhook source checks use the accepted credential and its local owner."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.library import LibraryFile
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.slicer_pipeline import SlicerPipeline
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _key(db, owner=None, *, read=True, printer_ids=None):
    raw_key, key_hash, prefix = generate_api_key()
    db.add(
        APIKey(
            name="Queue source fixture",
            key_hash=key_hash,
            key_prefix=prefix,
            user_id=owner.id if owner else None,
            can_read_status=read,
            can_queue=True,
            printer_ids=printer_ids,
        )
    )
    await db.commit()
    return {"X-API-Key": raw_key}


async def test_queue_and_webhook_read_sources_as_the_key_owner(
    async_client, db_session, printer_factory, archive_factory
):
    await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    permissions = ["archives:read_own", "archives:reprint_own", "library:read_own", "queue:create"]
    owner = User(
        username="queue_key_owner",
        allowed_printer_ids=[visible.id],
        groups=[Group(name="Queue key owner", permissions=permissions)],
    )
    db_session.add(owner)
    await db_session.commit()
    own_archive = await archive_factory(visible.id, created_by_id=owner.id)
    other_archive = await archive_factory(visible.id)
    hidden_archive = await archive_factory(hidden.id, created_by_id=owner.id)
    files = [
        LibraryFile(
            filename=f"{name}.gcode.3mf",
            file_path=f"{name}.gcode.3mf",
            file_type="3mf",
            file_size=5,
            created_by_id=owner_id,
        )
        for name, owner_id in (("owned", owner.id), ("ownerless", None))
    ]
    db_session.add_all(files)
    await db_session.commit()
    key = await _key(db_session, owner, printer_ids=[visible.id, hidden.id])
    blind_key = await _key(db_session, read=False)
    queue = "/api/v1/queue/"
    webhook = "/api/v1/webhook/queue/add"
    for endpoint in (queue, webhook):
        for archive_id in (other_archive.id, hidden_archive.id, 999999):
            response = await async_client.post(
                endpoint, headers=key, json={"archive_id": archive_id, "printer_id": visible.id}
            )
            assert (response.status_code, response.json()["detail"]) == (404, "Archive not found")

        response = await async_client.post(
            endpoint, headers=key, json={"archive_id": own_archive.id, "printer_id": visible.id}
        )
        assert response.status_code == 200, response.text
        item = await db_session.get(PrintQueueItem, response.json()["id"])
        assert item.created_by_id == owner.id

        response = await async_client.post(
            endpoint, headers=blind_key, json={"archive_id": other_archive.id, "printer_id": visible.id}
        )
        assert (response.status_code, response.json()["detail"]) == (404, "Archive not found")

    for headers, file_id in ((key, files[1].id), (key, 999999), (blind_key, files[1].id)):
        response = await async_client.post(
            queue, headers=headers, json={"library_file_id": file_id, "printer_id": visible.id}
        )
        assert (response.status_code, response.json()["detail"]) == (404, "Library file not found")
    response = await async_client.post(
        queue, headers=key, json={"library_file_id": files[0].id, "printer_id": visible.id}
    )
    assert response.status_code == 200, response.text
    assert (
        await db_session.scalar(select(PrintQueueItem.created_by_id).where(PrintQueueItem.id == response.json()["id"]))
        == owner.id
    )


async def test_auth_disabled_webhook_keeps_its_printer_boundaries(
    async_client, db_session, printer_factory, archive_factory
):
    visible, hidden = await printer_factory(), await printer_factory()
    allowed = await archive_factory(visible.id)
    denied = await archive_factory(hidden.id)
    key = await _key(db_session, read=False, printer_ids=[visible.id])
    endpoint = "/api/v1/webhook/queue/add"
    response = await async_client.post(endpoint, headers=key, json={"archive_id": allowed.id, "printer_id": visible.id})
    assert response.status_code == 200, response.text
    response = await async_client.post(endpoint, headers=key, json={"archive_id": denied.id, "printer_id": visible.id})
    assert (response.status_code, response.json()["detail"]) == (404, "Archive not found")


async def test_model_targets_and_batches_stay_within_key_and_owner_grants(
    async_client, db_session, printer_factory, archive_factory
):
    from backend.app.api.routes.pipeline_runs import _pick_assignments

    await _setup_admin(async_client)
    visible = await printer_factory(model="X1C")
    await printer_factory(model="X1C")
    other_model = await printer_factory(model="P1S")
    owner = User(
        username="model-key-owner",
        allowed_printer_ids=[visible.id],
        groups=[
            Group(
                name="Queue and pipeline access",
                permissions=["archives:read_own", "archives:reprint_own", "queue:create", "queue:update_own"],
            )
        ],
    )
    foreign_owner_id = await db_session.scalar(select(User.id).where(User.username == "tokenadmin"))
    batch = PrintBatch(name="Another owner's batch", created_by_id=foreign_owner_id)
    pipeline = SlicerPipeline(
        name="Shared model pipeline",
        printer_preset_source="local",
        printer_preset_id="1",
        process_preset_source="local",
        process_preset_id="2",
        filament_presets_json="[]",
        target_kind="printer_class",
        target_model_class="X1C",
        fanout_strategy="round_robin",
    )
    db_session.add_all([owner, batch, pipeline])
    await db_session.commit()
    archive = await archive_factory(visible.id, created_by_id=owner.id)
    limited = await _key(db_session, owner, printer_ids=[visible.id])
    full = await _key(db_session, owner)
    queue = "/api/v1/queue/"

    for payload in (
        {"archive_id": archive.id, "target_model": visible.model},
        {"variants": [{"library_file_id": 123, "target_model": visible.model}]},
    ):
        response = await async_client.post(queue, headers=limited, json=payload)
        assert response.status_code == 400
        assert response.json()["detail"] == "This API key must target a specific printer"

    fixed = await async_client.post(queue, headers=limited, json={"archive_id": archive.id, "printer_id": visible.id})
    assert fixed.status_code == 200, fixed.text
    denied = await async_client.post(
        queue, headers=full, json={"archive_id": archive.id, "target_model": other_model.model}
    )
    assert denied.status_code == 400
    assert denied.json()["detail"] == "No active printers for model: P1S"
    eligible = await async_client.post(
        queue, headers=full, json={"archive_id": archive.id, "target_model": visible.model}
    )
    assert eligible.status_code == 200, eligible.text
    assert eligible.json()["created_by_id"] == owner.id

    foreign_batch = f"/api/v1/queue/batches/{batch.id}"
    assert (await async_client.patch(foreign_batch, headers=limited, json={"name": "Denied"})).status_code == 404
    assert (await async_client.post(f"{foreign_batch}/ungroup", headers=limited)).status_code == 404
    for path in ("check-eligibility", "run"):
        response = await async_client.post(
            f"/api/v1/slicer-pipelines/{pipeline.id}/{path}", headers=limited, json={"source_archive_id": archive.id}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "This API key must target a specific printer"
    assert await _pick_assignments(db_session, pipeline, 3, {visible.id}) == [(visible.id, None)] * 3
    with pytest.raises(HTTPException, match="must target a specific printer"):
        await _pick_assignments(db_session, pipeline, 3, {visible.id}, allow_model_target=False)
