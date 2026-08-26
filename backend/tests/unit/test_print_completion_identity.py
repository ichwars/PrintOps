"""Completion identity matching and stranded queue recovery (#86)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.print_completion_identity import (
    STRANDED_PRINTING_GRACE_SECONDS,
    StrandedPrintRecovery,
    completion_belongs_to_queue_item,
    subtask_name_from_filename,
    subtask_names_match,
    terminal_queue_status,
    update_queue_status_for_completion,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Benchy.gcode.3mf", "Benchy"),
        ("Benchy.3mf", "Benchy"),
        ("My.Model.3mf", "My.Model"),
        ("/cache/Nested Path/Benchy.gcode.3mf", "Benchy"),
    ],
)
def test_subtask_name_from_filename(filename, expected):
    assert subtask_name_from_filename(filename) == expected


def test_subtask_names_match_printer_variants():
    assert subtask_names_match(
        "H2D_Carbon_Filter_(V2)_Body & Solid Lid",
        "h2d_carbon_filter_(v2)_body_&_solid_lid",
    )


def test_subtask_names_match_truncated_echo():
    full = "169356_204314.STEP + " * 7
    assert subtask_names_match(full, full[:96] + "...")
    assert not subtask_names_match("Benchy_Calibration_Cube_Large", "Something_Else...")


@pytest.mark.asyncio
async def test_completion_rejects_another_archive():
    item = SimpleNamespace(id=4, archive_id=10)
    assert not await completion_belongs_to_queue_item(AsyncMock(), item, {}, event_archive_id=11)


@pytest.mark.asyncio
async def test_completion_uses_subtask_and_print_identity():
    archive = SimpleNamespace(
        id=10,
        filename="H2D Carbon Filter.gcode.3mf",
        print_name="H2D Carbon Filter",
        subtask_id="print-10",
    )
    db = AsyncMock()
    db.get.return_value = archive
    item = SimpleNamespace(id=4, archive_id=10)

    assert await completion_belongs_to_queue_item(
        db,
        item,
        {"subtask_name": "h2d_carbon_filter", "subtask_id": "print-10"},
        event_archive_id=10,
    )
    assert not await completion_belongs_to_queue_item(
        db,
        item,
        {"subtask_name": "Calibration Cube", "subtask_id": "print-99"},
        event_archive_id=None,
    )


@pytest.mark.asyncio
async def test_unverifiable_completion_is_not_rejected():
    item = SimpleNamespace(id=4, archive_id=None)
    assert await completion_belongs_to_queue_item(AsyncMock(), item, {}, event_archive_id=None)


@pytest.mark.asyncio
async def test_foreign_completion_does_not_mutate_printing_item():
    item = SimpleNamespace(
        id=4,
        printer_id=3,
        archive_id=10,
        library_file_id=None,
        status="printing",
        completed_at=None,
        error_message=None,
        auto_off_after=False,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.return_value = result

    updated = await update_queue_status_for_completion(
        db,
        printer_id=3,
        data={"status": "completed", "subtask_name": "Another Print"},
        event_archive_id=11,
        failure_summary="",
        bump_usage=AsyncMock(),
    )

    assert updated is None
    assert item.status == "printing"
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("state", "expected"),
    [("FINISH", "completed"), ("FAILED", "failed"), ("IDLE", "cancelled"), ("RUNNING", None)],
)
def test_terminal_queue_status(state, expected):
    assert terminal_queue_status(SimpleNamespace(state=state, connected=True)) == expected
    assert terminal_queue_status(SimpleNamespace(state=state, connected=False)) is None


@pytest.mark.asyncio
async def test_stranded_printing_item_closes_after_grace_period():
    item = SimpleNamespace(id=7, printer_id=3, status="printing", completed_at=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.return_value = result
    db.__aenter__.return_value = db
    clock = [10.0]
    recovery = StrandedPrintRecovery(
        session_factory=lambda: db,
        status_getter=lambda _printer_id: SimpleNamespace(state="FINISH", connected=True),
        monotonic=lambda: clock[0],
    )

    await recovery.tick()
    assert item.status == "printing"
    clock[0] += STRANDED_PRINTING_GRACE_SECONDS + 1
    await recovery.tick()

    assert item.status == "completed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_busy_printer_resets_recovery_clock():
    item = SimpleNamespace(id=7, printer_id=3, status="printing", completed_at=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.return_value = result
    db.__aenter__.return_value = db
    state = SimpleNamespace(state="FINISH", connected=True)
    clock = [10.0]
    recovery = StrandedPrintRecovery(
        session_factory=lambda: db,
        status_getter=lambda _printer_id: state,
        monotonic=lambda: clock[0],
    )

    await recovery.tick()
    clock[0] += STRANDED_PRINTING_GRACE_SECONDS + 1
    state.state = "RUNNING"
    await recovery.tick()
    state.state = "FINISH"
    await recovery.tick()

    assert item.status == "printing"


@pytest.mark.asyncio
async def test_scheduler_loop_runs_stranded_recovery():
    from backend.app.services.print_scheduler import PrintScheduler

    scheduler = PrintScheduler()
    scheduler._stranded_print_recovery.tick = AsyncMock()

    async def stop_after_one_pass():
        scheduler._running = False
        return False

    scheduler.check_queue = AsyncMock(side_effect=stop_after_one_pass)
    with (
        patch("backend.app.services.print_scheduler.clear_stale_dispatch_claims", new=AsyncMock()),
        patch("backend.app.services.print_scheduler.asyncio.sleep", new=AsyncMock()),
    ):
        await scheduler.run()

    scheduler._stranded_print_recovery.tick.assert_awaited_once()
