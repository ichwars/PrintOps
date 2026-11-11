"""An explicit firmware rejection ends either watchdog phase immediately."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.print_scheduler import PrintScheduler
from backend.tests.unit.test_scheduler_watchdog import db_session  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted_first", [False, True])
@pytest.mark.parametrize("kind", ["ack", "developer_mode"])
async def test_an_explicit_refusal_in_either_phase_never_forces_a_reconnect(db_session, accepted_first, kind):
    real_sleep = asyncio.sleep

    async def tick(_seconds):
        await real_sleep(0)

    client = MagicMock(last_start_refusal=None)
    reads = 0

    def status(_printer_id):
        nonlocal reads
        reads += 1
        refused = reads > 1 if accepted_first else True
        if refused and kind == "ack":
            client.last_start_refusal = ("FAIL", "refused")
        return SimpleNamespace(
            state="FINISH",
            subtask_id="new" if accepted_first else "old",
            hms_errors=[SimpleNamespace(full_code="0500050000010007")] if refused and kind == "developer_mode" else [],
        )

    with (
        patch("backend.app.services.print_scheduler.printer_manager.get_status", MagicMock(side_effect=status)),
        patch("backend.app.services.print_scheduler.printer_manager.get_client", MagicMock(return_value=client)),
        patch("backend.app.services.print_scheduler.async_session", db_session),
        patch("backend.app.core.database.async_session", db_session),
        patch("backend.app.services.print_scheduler.asyncio.sleep", AsyncMock(side_effect=tick)) as sleep,
    ):
        await asyncio.wait_for(
            PrintScheduler._watchdog_print_start(
                queue_item_id=1,
                printer_id=42,
                pre_state="FINISH",
                pre_subtask_id="old",
                timeout=120,
                phase_b_timeout=120,
                poll_interval=0.1,
            ),
            timeout=1,
        )
    assert sleep.await_count == (2 if accepted_first else 1)
    client.force_reconnect_stale_session.assert_not_called()
    async with db_session() as db:
        item = await db.get(PrintQueueItem, 1)
        assert item.status == ("failed" if kind == "developer_mode" else "pending")
        if kind == "developer_mode":
            assert "Developer Mode" in item.error_message
