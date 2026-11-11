"""A server-side archive copy requires the same right as a reprint."""

from datetime import datetime, timezone

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.library import LibraryFile
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_archives_read_and_library_upload_do_not_authorize_reslicing(
    async_client, db_session, printer_factory, archive_factory
):
    await _setup_admin(async_client)
    printer = await printer_factory()
    archive = await archive_factory(printer.id, file_path="archives/permission-fixture/source.3mf")
    base_permissions = ["archives:read_all", "library:upload"]
    reader = User(username="archive_slice_reader", groups=[Group(name="Slice reader", permissions=base_permissions)])
    writer = User(
        username="archive_slice_writer",
        groups=[Group(name="Slice reprint", permissions=[*base_permissions, "archives:reprint_all"])],
    )
    db_session.add_all([reader, writer])
    await db_session.flush()

    keys = []
    for owner, can_queue in ((reader, True), (writer, False), (writer, True)):
        key, key_hash, prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="Slice permission",
                key_hash=key_hash,
                key_prefix=prefix,
                user_id=owner.id,
                can_manage_library=True,
                can_queue=can_queue,
            )
        )
        keys.append({"X-API-Key": key})
    await db_session.commit()
    reader_headers, writer_headers = (
        {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"} for user in (reader, writer)
    )
    path = f"/api/v1/archives/{archive.id}/slice"
    body = {"printer_preset_id": 1, "process_preset_id": 2, "filament_preset_id": 3}
    for headers in (reader_headers, *keys[:2]):
        response = await async_client.post(path, headers=headers, json=body)
        assert response.status_code == 403
        assert "archives:reprint" in response.json()["detail"]
    for headers in (writer_headers, keys[2]):
        response = await async_client.post(path, headers=headers, json=body)
        assert (response.status_code, response.json()["detail"]) == (404, "Archive source file missing on disk")


async def test_archive_pipeline_and_batch_use_the_same_source_gate(
    async_client, db_session, printer_factory, archive_factory
):
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    printer = await printer_factory()
    archive = await archive_factory(printer.id, file_path="archives/permission-fixture/pipeline-source.3mf")
    base_permissions = ["archives:read_all", "library:read_own", "pipelines:read", "pipelines:run", "queue:create"]
    reader = User(username="pipeline_reader", groups=[Group(name="Pipeline reader", permissions=base_permissions)])
    writer = User(
        username="pipeline_writer",
        groups=[Group(name="Pipeline reprint", permissions=[*base_permissions, "archives:reprint_all"])],
    )
    db_session.add_all([reader, writer])
    await db_session.flush()
    private_file = LibraryFile(
        filename="model.stl", file_path="model.stl", file_type="stl", file_size=5, created_by_id=writer.id
    )
    db_session.add(private_file)
    await db_session.commit()
    denied, allowed = (
        {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"} for user in (reader, writer)
    )
    pipeline = await async_client.post(
        "/api/v1/slicer-pipelines/",
        headers=admin,
        json={
            "name": "Archive pipeline",
            "printer_preset": {"source": "local", "id": "1"},
            "process_preset": {"source": "local", "id": "2"},
            "filament_presets": [{"source": "local", "id": "3"}],
        },
    )
    assert pipeline.status_code == 201, pipeline.text
    base = f"/api/v1/slicer-pipelines/{pipeline.json()['id']}"
    body = {"source_archive_id": archive.id}
    for operation in ("check-eligibility", "run"):
        response = await async_client.post(f"{base}/{operation}", headers=denied, json=body)
        assert response.status_code == 403
        response = await async_client.post(f"{base}/{operation}", headers=allowed, json=body)
        assert (response.status_code, response.json()["detail"]) == (404, "Archive source file missing on disk")

    batches = "/api/v1/queue/batches"
    body = {"name": "Order", "archive_id": archive.id}
    assert (await async_client.post(batches, headers=denied, json=body)).status_code == 403
    assert (await async_client.post(batches, headers=allowed, json=body)).status_code == 200
    body = {"name": "Library order", "library_file_id": private_file.id}
    assert (await async_client.post(batches, headers=denied, json=body)).status_code == 404
    assert (await async_client.post(batches, headers=allowed, json=body)).status_code == 200

    archive.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    body = {"name": "Deleted order", "archive_id": archive.id}
    assert (await async_client.post(batches, headers=allowed, json=body)).status_code == 404
    queued = await async_client.post(
        "/api/v1/queue/", headers=allowed, json={"archive_id": archive.id, "printer_id": printer.id}
    )
    assert (queued.status_code, queued.json()["detail"]) == (404, "Archive not found")
    empty = await async_client.post(
        batches, headers=allowed, json={"name": "Empty order", "archive_id": 0, "library_file_id": 0}
    )
    assert empty.status_code == 200
    assert empty.json()["archive_id"] is empty.json()["library_file_id"] is None
