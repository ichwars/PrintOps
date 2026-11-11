"""Drying blocks and pre-drying apply to each authorized model candidate."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_drying import queue_printer_sets
from backend.tests.unit.test_scheduler_model_filament_short_3137 import (
    _add_item,
    _get_item,
    _run,
    queue_db,  # noqa: F401
)

pytestmark = pytest.mark.asyncio


async def _block_drying(ctx, enabled=True):
    async with ctx.session_maker() as db:
        db.add(Settings(key="queue_drying_block", value=str(enabled).lower()))
        await db.commit()


@pytest.mark.parametrize("pinned", [False, True])
@pytest.mark.parametrize("block", [False, True])
async def test_fixed_and_model_jobs_follow_the_same_drying_hold(queue_db, pinned, block):
    await _block_drying(queue_db, block)
    item_id = await _add_item(queue_db, printer_id=1 if pinned else None)
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[1] = 100
    launched = MagicMock()
    await _run(queue_db, scheduler, short=set(), launched=launched)
    item = await _get_item(queue_db, item_id)
    if pinned and block:
        launched.assert_not_called()
        assert item.printer_id == 1
    else:
        launched.assert_called_once()
        assert item.printer_id == (2 if block else 1)


async def test_a_model_job_waits_when_its_only_idle_printer_is_drying(queue_db):
    await _block_drying(queue_db)
    item_id = await _add_item(queue_db)
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[1] = 100
    launched = MagicMock()
    await _run(queue_db, scheduler, short=set(), launched=launched, idle=lambda pid: pid == 1)
    launched.assert_not_called()
    item = await _get_item(queue_db, item_id)
    assert item.printer_id is None
    assert item.status == "pending"
    assert "Busy:" in item.waiting_reason and "(drying)" in item.waiting_reason


async def test_a_low_filament_hold_is_not_released_onto_a_drying_printer(queue_db):
    await _block_drying(queue_db)
    item_id = await _add_item(queue_db, printer_id=1, manual_start=True, filament_short=True)
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[2] = 100
    await _run(queue_db, scheduler, short={1}, launched=MagicMock())
    assert (await _get_item(queue_db, item_id)).printer_id == 3


async def test_a_parked_timer_does_not_hold_a_model_job(queue_db):
    await _block_drying(queue_db)
    item_id = await _add_item(queue_db)
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[1] = 100
    with patch("backend.app.services.queue_drying.only_parked_countdowns", return_value=True):
        await _run(queue_db, scheduler, short=set(), launched=MagicMock())
    assert (await _get_item(queue_db, item_id)).printer_id == 1


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("supported", [False, True])
async def test_dispatch_stops_only_owned_drying_unless_concurrent_mode_is_enabled_and_supported(enabled, supported):
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[1] = 100
    scheduler._get_bool_setting = AsyncMock(return_value=enabled)
    order = []
    scheduler._stop_drying = AsyncMock(side_effect=lambda pid: order.append("stop"))
    scheduler._start_print_owned = AsyncMock(side_effect=lambda *args: order.append("print"))

    @asynccontextmanager
    async def dispatch(*args):
        order.append("admission")
        yield

    with (
        patch("backend.app.services.print_scheduler.preheat_ownership.blocks_power_off", return_value=False),
        patch("backend.app.services.print_scheduler.preheat_ownership.dispatch", dispatch),
        patch("backend.app.services.queue_drying.supports_drying_while_printing", return_value=supported),
    ):
        await scheduler._start_print(AsyncMock(), SimpleNamespace(id=7, printer_id=1))
    assert order == (["admission", "print"] if enabled and supported else ["stop", "admission", "print"])


@pytest.mark.parametrize("manual", [False, True])
async def test_a_scheduled_model_job_counts_on_each_eligible_printer_in_its_location(queue_db, manual):
    async with queue_db.session_maker() as db:
        printers = (await db.scalars(select(Printer).order_by(Printer.id))).all()
        printers[0].model, printers[0].location = "x1c", "Lab"
        printers[1].location = "Lab"
        printers[2].location = "Other"
        await db.commit()
    item_id = await _add_item(
        queue_db,
        target_location="Lab",
        scheduled_time=datetime.now(timezone.utc) + timedelta(hours=1),
        manual_start=manual,
    )
    async with queue_db.session_maker() as db:
        item = await db.scalar(
            select(PrintQueueItem)
            .where(PrintQueueItem.id == item_id)
            .options(
                selectinload(PrintQueueItem.library_file),
                selectinload(PrintQueueItem.archive),
                selectinload(PrintQueueItem.variants),
            )
        )
        scheduled, ready = await queue_printer_sets(PrintScheduler(), db, [item])
    assert ready == set()
    assert scheduled == (set() if manual else {1, 2})


@pytest.mark.parametrize("allowed", [[], [2], None])
async def test_model_predrying_uses_current_creator_grants(queue_db, allowed):
    async with queue_db.session_maker() as db:
        user = User(username="owner", is_active=True, allowed_printer_ids=allowed)
        db.add(user)
        await db.commit()
        user_id = user.id
    # Source validity is already covered by the queue candidate builder. Here
    # two candidate models exercise the union and the SQL scope intersection.
    scheduler = PrintScheduler()
    scheduler._queue_model_candidates = MagicMock(return_value=[SimpleNamespace(target_model="X1C")])
    item = SimpleNamespace(
        printer_id=None,
        target_model="X1C",
        created_by_id=user_id,
        target_location=None,
        scheduled_time=datetime.now(timezone.utc) - timedelta(minutes=1),
        manual_start=False,
    )
    async with queue_db.session_maker() as db:
        with patch("backend.app.services.queue_filament_mapping.is_auth_enabled", AsyncMock(return_value=True)):
            scheduled, pending = await queue_printer_sets(scheduler, db, [item])
    expected = set(allowed) if allowed is not None else {1, 2, 3}
    assert scheduled == pending == expected


async def test_variants_count_for_each_model_without_widening_printer_grants(queue_db):
    async with queue_db.session_maker() as db:
        printer = await db.get(Printer, 3)
        printer.model = "H2C"
        user = User(username="owner", is_active=True, allowed_printer_ids=[2, 3])
        db.add(user)
        await db.commit()
        user_id = user.id
    scheduler = PrintScheduler()
    scheduler._queue_model_candidates = MagicMock(
        return_value=[
            SimpleNamespace(target_model="X1C"),
            SimpleNamespace(target_model="H2C"),
        ]
    )
    item = SimpleNamespace(
        printer_id=None,
        target_model=None,
        variants=[object()],
        created_by_id=user_id,
        target_location=None,
        scheduled_time=datetime.now(timezone.utc) - timedelta(minutes=1),
        manual_start=False,
    )
    async with queue_db.session_maker() as db:
        with patch("backend.app.services.queue_filament_mapping.is_auth_enabled", AsyncMock(return_value=True)):
            assert await queue_printer_sets(scheduler, db, [item]) == ({2, 3}, {2, 3})


async def test_a_parked_countdown_never_releases_a_durable_daily_drying_reservation(queue_db):
    from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun

    await _block_drying(queue_db)
    item_id = await _add_item(queue_db)
    now = datetime.now(timezone.utc)
    async with queue_db.session_maker() as db:
        plan = DryingSchedule(
            printer_id=1,
            ams_id=0,
            local_time="08:00",
            timezone="Europe/Berlin",
            filament="PLA",
            temperature=45,
            duration_hours=1,
        )
        db.add(plan)
        await db.flush()
        db.add(
            DryingScheduleRun(
                schedule_id=plan.id,
                printer_id=1,
                active_printer_id=1,
                ams_id=0,
                occurrence_day="2026-11-09",
                due_at=now,
                claimed_at=now,
                status="uncertain",
            )
        )
        await db.commit()
    scheduler = PrintScheduler()
    scheduler._drying_in_progress[1] = 100
    with patch("backend.app.services.queue_drying.only_parked_countdowns", return_value=True):
        await _run(queue_db, scheduler, short=set(), launched=MagicMock())
    assert (await _get_item(queue_db, item_id)).printer_id == 2
