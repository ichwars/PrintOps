"""Queue appends and insertions keep one sequence across all printer targets."""

import pytest

from backend.tests.integration.test_print_queue_api import TestPrintQueueAPI as _QueueAPIFixtures


class TestGlobalQueuePositions:
    printer_factory = _QueueAPIFixtures.printer_factory
    archive_factory = _QueueAPIFixtures.archive_factory

    async def _enqueue(self, client, archive_id, **target):
        response = await client.post("/api/v1/queue/", json={"archive_id": archive_id, **target})
        assert response.status_code == 200, response.text
        return response.json()

    @pytest.mark.asyncio
    async def test_appends_to_distinct_targets_share_a_position_sequence(
        self, async_client, printer_factory, archive_factory
    ):
        first = await printer_factory(model="P1S")
        second = await printer_factory(model="P1S")
        archive = await archive_factory()
        jobs = [
            await self._enqueue(async_client, archive.id, printer_id=first.id),
            await self._enqueue(async_client, archive.id, target_model="P1S"),
            await self._enqueue(async_client, archive.id, printer_id=second.id),
        ]
        assert [job["position"] for job in jobs] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_top_insert_shifts_every_pending_target(self, async_client, printer_factory, archive_factory):
        first = await printer_factory(model="P1S")
        second = await printer_factory(model="P1S")
        archive = await archive_factory()
        await self._enqueue(async_client, archive.id, printer_id=first.id)
        await self._enqueue(async_client, archive.id, target_model="P1S")
        inserted = await self._enqueue(async_client, archive.id, printer_id=second.id, insert_at_top=True)
        response = await async_client.get("/api/v1/queue/")
        assert response.status_code == 200
        jobs = response.json()
        assert [job["id"] for job in jobs][0] == inserted["id"]
        assert [job["position"] for job in jobs] == [1, 2, 3]
