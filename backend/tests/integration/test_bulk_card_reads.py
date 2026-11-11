"""Fleet reads apply the same visibility, ordering, and redaction as single cards."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from backend.app.core.auth import generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.library import LibraryFolder
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_card_reads_match_single_routes_and_keep_order(
    async_client, db_session, printer_factory, smart_plug_factory
):
    a = await printer_factory(name="First", model="X1C")
    b = await printer_factory(name="Second", model="X1C")
    await smart_plug_factory(printer_id=a.id, plug_type="rest", rest_status_path="state")
    db_session.add(PrintQueueItem(printer_id=b.id, status="pending", position=1))
    await db_session.commit()
    ids = f"{b.id},{a.id},{b.id},99999"
    statuses = await async_client.get("/api/v1/bulk/printer-statuses", params={"ids": ids})
    assert statuses.status_code == 200, statuses.text
    assert [entry["id"] for entry in statuses.json()] == [b.id, a.id]

    for printer in (a, b):
        status = await async_client.get(f"/api/v1/printers/{printer.id}/status")
        assert next(entry for entry in statuses.json() if entry["id"] == printer.id) == status.json()

    for endpoint, single in (
        ("slot-presets", lambda printer_id: f"/printers/{printer_id}/slot-presets"),
        ("ams-labels", lambda printer_id: f"/printers/{printer_id}/ams-labels"),
        ("ha-sensor-readings", lambda printer_id: f"/ha-sensors/by-printer/{printer_id}/readings"),
        ("printer-queues", lambda printer_id: f"/queue/?printer_id={printer_id}&status=pending"),
    ):
        response = await async_client.get(f"/api/v1/bulk/{endpoint}", params={"ids": ids, "status": "pending"})
        assert response.status_code == 200, (endpoint, response.text)
        assert set(response.json()) == {str(a.id), str(b.id)}
        for printer in (a, b):
            row = await async_client.get(f"/api/v1{single(printer.id)}")
            assert row.status_code == 200 and response.json()[str(printer.id)] == row.json()


async def test_key_intersection_and_secret_redaction_match_single_routes(
    async_client, db_session, printer_factory, smart_plug_factory, monkeypatch
):
    a, only_user, only_key = await printer_factory(), await printer_factory(), await printer_factory()
    admin = await _admin_token(async_client, "_fleet_bulk")
    _, user_id = await _make_user(
        async_client,
        admin,
        username="fleet_bulk_reader",
        permissions=[
            Permission.PRINTERS_READ.value,
            Permission.SMART_PLUGS_READ.value,
            Permission.FIRMWARE_READ.value,
            Permission.QUEUE_READ_OWN.value,
        ],
    )
    await db_session.execute(update(User).where(User.id == user_id).values(allowed_printer_ids=[a.id, only_user.id]))
    key, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Fleet card key",
            key_hash=key_hash,
            key_prefix=prefix,
            user_id=user_id,
            can_read_status=True,
            can_queue=True,
            printer_ids=[a.id, only_key.id],
        )
    )
    await smart_plug_factory(
        printer_id=a.id,
        plug_type="rest",
        password="fixture-password",
        rest_on_url="https://plug.example.test/on?secret=fixture",
        rest_headers='{"Authorization":"Bearer fixture"}',
    )
    own_job = PrintQueueItem(printer_id=a.id, created_by_id=user_id, position=1, status="pending")
    db_session.add_all([own_job, PrintQueueItem(printer_id=a.id, position=2, status="pending")])
    await db_session.commit()

    firmware = AsyncMock(
        side_effect=lambda printer: {
            "printer_id": printer.id,
            "printer_name": printer.name,
            "model": printer.model,
            "current_version": None,
            "latest_version": None,
            "update_available": False,
        }
    )
    monkeypatch.setattr("backend.app.api.routes.bulk.printer_firmware_update", firmware)
    headers = {"X-API-Key": key}
    query = {"ids": f"{a.id},{only_user.id},{only_key.id}", "status": "pending"}
    for endpoint in (
        "printer-statuses",
        "slot-presets",
        "ams-labels",
        "card-plugs",
        "ha-sensor-readings",
        "firmware-updates",
        "printer-queues",
    ):
        response = await async_client.get(f"/api/v1/bulk/{endpoint}", params=query, headers=headers)
        assert response.status_code == 200, (endpoint, response.text)
        data = response.json()
        if isinstance(data, list):
            assert len(data) == 1
            assert data[0].get("id", data[0].get("printer_id")) == a.id
        else:
            assert set(data) == {str(a.id)}
        if endpoint == "card-plugs":
            plug = data[str(a.id)]["plug"]
            assert plug["password"] is None and plug["rest_headers"] is None and plug["rest_on_url"] is None
            single = await async_client.get(f"/api/v1/smart-plugs/by-printer/{a.id}", headers=headers)
            assert single.json() == plug
        if endpoint == "printer-queues":
            single = await async_client.get(f"/api/v1/queue/?printer_id={a.id}&status=pending", headers=headers)
            assert single.json() == data[str(a.id)]
            assert [entry["id"] for entry in single.json()] == [own_job.id]

    for hidden_id in (only_user.id, only_key.id):
        denied = await async_client.get(f"/api/v1/printers/{hidden_id}/slot-presets", headers=headers)
        assert denied.status_code == 404


async def test_archive_folder_bulk_shape_and_invalid_ids(async_client, db_session, printer_factory, archive_factory):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    db_session.add(LibraryFolder(name="Fixture folder", archive_id=archive.id))
    await db_session.commit()
    response = await async_client.get("/api/v1/bulk/archive-folders", params={"ids": f"{archive.id},99999"})
    assert response.status_code == 200, response.text
    single = await async_client.get(f"/api/v1/library/folders/by-archive/{archive.id}")
    assert response.json() == {str(archive.id): single.json(), "99999": []}
    assert single.json()[0]["name"] == "Fixture folder"
    for invalid in ("1,-1", "1,²", "2147483648", "1,zzz"):
        response = await async_client.get("/api/v1/bulk/printer-statuses", params={"ids": invalid})
        assert response.status_code == 422
