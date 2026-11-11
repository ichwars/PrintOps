import asyncio

from backend.app.core.tasks import spawn_background_task
from backend.tests.conftest import _finish_query_cancellations, _stop_test_background_tasks


class Connection:
    async def _cancel(self):
        await asyncio.sleep(0)


async def test_fixture_waits_for_database_cancellations_and_leaves_other_tasks():
    cancel = asyncio.create_task(Connection()._cancel())
    event = asyncio.Event()
    unrelated = asyncio.create_task(event.wait())
    try:
        await _finish_query_cancellations()
        assert cancel.done()
        assert not unrelated.done()
    finally:
        event.set()
        await unrelated


async def test_fixture_cancels_application_background_work():
    task = spawn_background_task(asyncio.Event().wait())
    await _stop_test_background_tasks()
    assert task.cancelled()
