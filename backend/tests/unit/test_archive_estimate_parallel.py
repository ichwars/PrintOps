"""One file may start estimates for several printers before either finishes."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from backend.app.services import archive_cost_estimate as estimates


@pytest.mark.asyncio
async def test_completion_stops_all_estimates_for_the_same_archive():
    blocked = asyncio.Event()

    async def estimate(*args):
        await blocked.wait()

    @asynccontextmanager
    async def session():
        yield object()

    with (
        patch("backend.app.core.database.async_session", session),
        patch.object(estimates, "estimate_archive_cost_at_start", estimate),
    ):
        tasks = [estimates.schedule_archive_cost_estimate(pid, 12877, None) for pid in (1, 2)]
        await asyncio.sleep(0)
        await estimates.settle_archive_cost_estimate(12877)
    assert all(task.cancelled() for task in tasks)
