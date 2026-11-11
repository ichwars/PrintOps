"""Legacy clients send zero for omitted queue sources and project parents."""

import pytest
from sqlalchemy import select

from backend.app.models.library import LibraryFile
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_queue import PrintQueueItem

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("use_archive", [False, True])
async def test_queue_and_automatic_batch_store_missing_source_as_null(
    async_client, db_session, printer_factory, archive_factory, use_archive
):
    printer = await printer_factory()
    if use_archive:
        archive = await archive_factory(printer.id)
        archive_id, file_id = archive.id, 0
    else:
        file = LibraryFile(filename="part.gcode.3mf", file_path="library/part.gcode.3mf", file_size=5, file_type="3mf")
        db_session.add(file)
        await db_session.commit()
        archive_id, file_id = 0, file.id

    expected_sources = (archive_id or None, file_id or None)
    response = await async_client.post(
        "/api/v1/queue/",
        json={"archive_id": archive_id, "library_file_id": file_id, "printer_id": printer.id, "quantity": 2},
    )

    assert response.status_code == 200, response.text
    rows = await db_session.execute(select(PrintQueueItem.archive_id, PrintQueueItem.library_file_id))
    assert rows.all() == [expected_sources, expected_sources]
    batch = await db_session.execute(select(PrintBatch.archive_id, PrintBatch.library_file_id))
    assert batch.one() == expected_sources


async def test_zero_alone_does_not_supply_a_queue_source(async_client):
    response = await async_client.post("/api/v1/queue/", json={"archive_id": 0, "library_file_id": 0})
    assert response.status_code == 400
    assert response.json()["detail"] == "Either archive_id or library_file_id must be provided"


async def test_project_parent_zero_is_stored_as_no_parent(async_client):
    response = await async_client.post("/api/v1/projects/", json={"name": "Standalone", "parent_id": 0})
    assert response.status_code == 200, response.text
    assert response.json()["parent_id"] is None
