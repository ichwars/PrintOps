"""A webhook reprint keeps the slicer's AMS slots, as a reprint from the UI does (F9).

An archive printed through the virtual printer remembers which AMS slots the
slicer picked on its printer. Queued again for that printer from the UI, the
job reuses them; queued through the webhook it did not, and the scheduler
matched slots by colour and type again, possibly other spools.
"""

import pytest
from sqlalchemy import select

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.print_queue import PrintQueueItem


async def _webhook_key(db):
    raw, hashed, prefix = generate_api_key()
    db.add(APIKey(name="Test webhook", key_hash=hashed, key_prefix=prefix, can_queue=True))
    await db.commit()
    return {"X-API-Key": raw}


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def committing_request_session(async_client, test_engine):
    # The webhook relies on get_db's commit after yield. The shared test
    # override deliberately omits that commit; model this route's real contract.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.app.core.database import get_db
    from backend.app.main import app

    previous = app.dependency_overrides[get_db]
    maker = async_sessionmaker(test_engine, expire_on_commit=False)

    async def session():
        async with maker() as db:
            yield db
            await db.commit()

    app.dependency_overrides[get_db] = session
    yield
    app.dependency_overrides[get_db] = previous


async def _archive(db_session, archive_factory, printer_id: int):
    archive = await archive_factory(printer_id)
    archive.extra_data = {"slicer_ams_mapping": {"printer_id": printer_id, "mapping": [2, 0]}}
    await db_session.commit()
    return archive


@pytest.mark.parametrize("for_its_printer", [True, False])
async def test_the_webhook_reuses_the_slots_for_the_printer_they_were_picked_on(
    async_client, db_session, printer_factory, archive_factory, for_its_printer
):
    printer = await printer_factory()
    other = await printer_factory(name="Other")
    archive = await _archive(db_session, archive_factory, printer.id)

    response = await async_client.post(
        "/api/v1/webhook/queue/add",
        json={"printer_id": printer.id if for_its_printer else other.id, "archive_id": archive.id},
        headers=await _webhook_key(db_session),
    )

    assert response.status_code == 200, response.text
    item = await db_session.scalar(select(PrintQueueItem).where(PrintQueueItem.id == response.json()["id"]))
    # Slot numbers only mean something on the printer they were picked on
    assert item.ams_mapping == ("[2, 0]" if for_its_printer else None)
