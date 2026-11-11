"""History pages and deletion share filters and keep local batch source rules."""

from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.core.auth import generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.print_batch import PrintBatch, PrintBatchPlate
from backend.app.models.print_queue import PrintQueueItem
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_pages_keep_batch_siblings_and_location_filters(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory(name="Remote printer", location="Annex")
    archive = await archive_factory(printer.id, print_name="Job")
    batch = PrintBatch(name="Order history")
    db_session.add(batch)
    await db_session.flush()
    older = PrintQueueItem(
        printer_id=printer.id,
        batch_id=batch.id,
        archive_id=archive.id,
        status="failed",
        completed_at=datetime(2026, 11, 10),
    )
    newer = PrintQueueItem(
        printer_id=printer.id,
        batch_id=batch.id,
        archive_id=archive.id,
        status="completed",
        completed_at=datetime(2026, 11, 11),
    )
    other_location = PrintQueueItem(printer_id=printer.id, status="cancelled", target_location="Workshop")
    active = PrintQueueItem(printer_id=printer.id, status="printing")
    db_session.add_all([older, newer, other_location, active])
    await db_session.commit()

    async def page(**params):
        response = await async_client.get("/api/v1/queue/history", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    first = await page(limit=1, location="Annex")
    assert first["total"] == 2 and first["locations"] == ["Annex", "Workshop"]
    assert [item["id"] for item in first["items"]] == [newer.id]
    assert [item["id"] for item in first["related_items"]] == [older.id]
    assert [item["id"] for item in (await page(limit=1, offset=1, location="Annex"))["items"]] == [older.id]
    assert [item["id"] for item in (await page(limit=1, location="Annex", reverse=True))["items"]] == [older.id]
    assert (await page(limit=0))["total"] == 3
    assert (await page(limit=0))["items"] == []


async def test_bulk_clear_keeps_last_source_and_respects_history_filters(async_client, db_session, printer_factory):
    printer = await printer_factory(location="Annex")
    batch = PrintBatch(name="Open batch", quantity=2)
    db_session.add(batch)
    await db_session.flush()
    db_session.add(PrintBatchPlate(batch_id=batch.id, plate_id=None, quantity_target=2))
    first = PrintQueueItem(printer_id=printer.id, batch_id=batch.id, status="failed", position=1)
    last = PrintQueueItem(printer_id=printer.id, batch_id=batch.id, status="failed", position=2)
    active = PrintQueueItem(printer_id=printer.id, status="printing")
    outside = PrintQueueItem(printer_id=printer.id, status="failed", target_location="Workshop")
    db_session.add_all([first, last, active, outside])
    await db_session.commit()

    response = await async_client.post("/api/v1/queue/history/clear", params={"location": "Annex", "status": "failed"})
    assert response.status_code == 200, response.text
    assert response.json() == {"cleared": 1, "kept": 1}
    rows = dict((await db_session.execute(select(PrintQueueItem.id, PrintQueueItem.status))).all())
    assert rows == {last.id: "cancelled", active.id: "printing", outside.id: "failed"}


async def test_history_clear_intersects_read_own_with_delete_all(async_client, db_session, printer_factory):
    printer = await printer_factory()
    admin = await _admin_token(async_client, "_queue_history")
    _, user_id = await _make_user(
        async_client,
        admin,
        username="history_own_reader",
        permissions=[Permission.QUEUE_READ_OWN.value, Permission.QUEUE_DELETE_ALL.value],
    )
    token, token_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Queue history key",
            key_hash=token_hash,
            key_prefix=prefix,
            user_id=user_id,
            can_read_status=True,
            can_queue=True,
            printer_ids=[printer.id],
        )
    )
    own = PrintQueueItem(printer_id=printer.id, created_by_id=user_id, status="failed")
    other = PrintQueueItem(printer_id=printer.id, status="failed")
    db_session.add_all([own, other])
    await db_session.commit()
    headers = {"X-API-Key": token}
    response = await async_client.get("/api/v1/queue/history", headers=headers)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [own.id]
    cleared = await async_client.post("/api/v1/queue/history/clear", headers=headers)
    assert cleared.status_code == 200 and cleared.json() == {"cleared": 1, "kept": 0}, cleared.text
    assert list(await db_session.scalars(select(PrintQueueItem.id))) == [other.id]
