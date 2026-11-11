"""Queue status sets keep their API filtering contract."""

import pytest

from backend.app.models.print_queue import PrintQueueItem

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize(
    "status_filter, expected",
    [
        ("pending, printing", {"pending", "printing"}),
        ("completed", {"completed"}),
        (", ,", set()),
        ("not-a-status", set()),
    ],
)
async def test_queue_accepts_status_sets(
    async_client, db_session, printer_factory, archive_factory, status_filter, expected
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    for position, status in enumerate(["pending", "printing", "completed"]):
        db_session.add(PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status=status, position=position))
    await db_session.commit()

    response = await async_client.get("/api/v1/queue/", params={"status": status_filter})

    assert response.status_code == 200, response.text
    assert {row["status"] for row in response.json()} == expected
