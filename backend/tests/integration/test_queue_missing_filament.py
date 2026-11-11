"""Start preflight holds missing filament and permits explicit acknowledgement."""

import pytest
from httpx import AsyncClient

from backend.tests.integration.test_print_queue_api import TestPrintQueueAPI as QueueApiFixtures


class TestQueueMissingFilament:
    printer_factory = QueueApiFixtures.printer_factory
    archive_factory = QueueApiFixtures.archive_factory
    queue_item_factory = QueueApiFixtures.queue_item_factory

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_queue_item_skip_filament_check(
        self, async_client: AsyncClient, queue_item_factory, db_session
    ):
        """#2799: the print dialog sends it on edit when the mapping deliberately
        puts a slot on another material."""
        item = await queue_item_factory()
        response = await async_client.patch(f"/api/v1/queue/{item.id}", json={"skip_filament_check": True})
        assert response.status_code == 200
        assert response.json()["skip_filament_check"] is True

        # Omitted on a later edit, it stays as it was.
        response = await async_client.patch(f"/api/v1/queue/{item.id}", json={"manual_start": True})
        assert response.json()["skip_filament_check"] is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_start_with_a_filament_not_loaded_offers_print_anyway(
        self, async_client: AsyncClient, queue_item_factory, db_session
    ):
        """#2799: Start on an item whose filament has no tray answers 409 with the
        missing filaments instead of releasing it to be held again."""
        from unittest.mock import AsyncMock, patch

        item = await queue_item_factory(manual_start=True)
        with patch(
            "backend.app.services.print_scheduler.scheduler.missing_filament_for_start",
            AsyncMock(return_value=["PETG #2850E0"]),
        ):
            response = await async_client.post(f"/api/v1/queue/{item.id}/start")

        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "unmatched_filament", "missing": ["PETG #2850E0"]}
        await db_session.refresh(item)
        assert item.manual_start is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_failing_filament_check_does_not_break_start(
        self, async_client: AsyncClient, queue_item_factory, db_session
    ):
        """The check is a convenience; the scheduler still holds the item if the
        filament is missing, so an error in it must not turn Start into a 500."""
        from unittest.mock import AsyncMock, patch

        item = await queue_item_factory(manual_start=True)
        with patch(
            "backend.app.services.print_scheduler.scheduler.missing_filament_for_start",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = await async_client.post(f"/api/v1/queue/{item.id}/start")

        assert response.status_code == 200
        assert response.json()["manual_start"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_print_anyway_past_a_filament_not_loaded(
        self, async_client: AsyncClient, queue_item_factory, db_session
    ):
        """The retry with skip_filament_check is not asked again, and is remembered."""
        from unittest.mock import AsyncMock, patch

        item = await queue_item_factory(manual_start=True)
        check = AsyncMock(return_value=["PETG #2850E0"])
        with patch("backend.app.services.print_scheduler.scheduler.missing_filament_for_start", check):
            response = await async_client.post(f"/api/v1/queue/{item.id}/start?skip_filament_check=true")

        assert response.status_code == 200
        check.assert_not_awaited()
        result = response.json()
        assert result["manual_start"] is False
        assert result["skip_filament_check"] is True
