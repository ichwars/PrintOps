"""A hung printer file service cannot hold queue completion indefinitely."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services import print_sd_cleanup


@pytest.mark.asyncio
async def test_cleanup_stops_waiting_at_its_budget(monkeypatch):
    cancelled = asyncio.Event()

    async def stuck(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(print_sd_cleanup, "SD_CLEANUP_BUDGET_SECONDS", 0.01)
    monkeypatch.setattr(print_sd_cleanup, "_cleanup_after_print", stuck)
    log = MagicMock()
    await print_sd_cleanup.cleanup_after_print(1, "part", 99, log, MagicMock())
    assert cancelled.is_set()
    log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_successful_cleanup_can_finish(monkeypatch):
    cleanup = AsyncMock()
    monkeypatch.setattr(print_sd_cleanup, "_cleanup_after_print", cleanup)
    log = MagicMock()
    await print_sd_cleanup.cleanup_after_print(1, "part", 99, log, MagicMock())
    cleanup.assert_awaited_once()
    log.warning.assert_not_called()
