"""Automatic power cuts must respect live and unresolved preheat ownership."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.preheat_ownership import PreheatOwnership
from backend.app.services.smart_plug_manager import SmartPlugManager


@pytest.fixture
def plug_guard(tmp_path, monkeypatch):
    owner = PreheatOwnership(tmp_path)
    manager = SmartPlugManager()
    service = MagicMock(turn_off=AsyncMock(return_value=True), turn_on=AsyncMock(return_value=True))
    manager.get_service_for_plug = AsyncMock(return_value=service)
    manager._mark_auto_off_pending = AsyncMock()
    manager._mark_auto_off_executed = AsyncMock()
    pm = MagicMock()
    pm.is_print_active.return_value = False
    pm.get_status.return_value = SimpleNamespace(state="IDLE", temperatures={"nozzle": 20})
    monkeypatch.setattr("backend.app.services.smart_plug_manager.preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.smart_plug_manager.printer_manager", pm)
    return SimpleNamespace(owner=owner, manager=manager, service=service, pm=pm)


def block(guard):
    # A record can be unreadable, stale or waiting for reconnection. All of
    # these must interlock power cuts before startup recovery can resolve it.
    guard.owner.path(7).write_text("unverified record")


@pytest.mark.asyncio
async def test_delayed_off_skips_live_or_unknown_ownership(plug_guard):
    block(plug_guard)
    await plug_guard.manager._delayed_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 0)
    plug_guard.service.turn_off.assert_not_awaited()
    plug_guard.manager._mark_auto_off_pending.assert_awaited_once_with(1, False)


@pytest.mark.asyncio
async def test_delayed_off_rechecks_after_awaited_service_configuration(plug_guard):
    async def configure(*args):
        block(plug_guard)
        return plug_guard.service

    plug_guard.manager.get_service_for_plug.side_effect = configure
    await plug_guard.manager._delayed_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 0)
    plug_guard.service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_temperature_off_keeps_waiting_during_preheat(plug_guard):
    block(plug_guard)
    entered = asyncio.Event()

    async def pause(_):
        entered.set()
        await asyncio.Event().wait()

    with patch("backend.app.services.smart_plug_manager.asyncio.sleep", side_effect=pause):
        task = asyncio.create_task(
            plug_guard.manager._temp_based_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 50)
        )
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await task
    plug_guard.service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_temperature_off_rechecks_after_configuration(plug_guard):
    async def configure(*args):
        block(plug_guard)
        return plug_guard.service

    plug_guard.manager.get_service_for_plug.side_effect = configure
    with patch("backend.app.services.smart_plug_manager.asyncio.sleep", new=AsyncMock()):
        await plug_guard.manager._temp_based_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 50)
    plug_guard.service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("guarded", [True, False])
async def test_restart_pending_off_checks_ownership(plug_guard, guarded):
    if guarded:
        block(plug_guard)
    plug = SimpleNamespace(
        id=1,
        printer_id=7,
        name="Printer plug",
        auto_off_pending=True,
        auto_off_pending_since=None,
        off_delay_mode="time",
        controls_printer_power=True,
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [plug]
    with patch("backend.app.core.database.async_session") as factory:
        factory.return_value.__aenter__.return_value = db
        await plug_guard.manager.resume_pending_auto_offs()
    assert plug_guard.service.turn_off.await_count == (0 if guarded else 1)
    if guarded:
        assert not plug.auto_off_pending
        plug_guard.pm.mark_printer_offline.assert_not_called()


@pytest.mark.asyncio
async def test_restart_rechecks_ownership_after_service_configuration(plug_guard):
    async def configure(*args):
        block(plug_guard)
        return plug_guard.service

    plug_guard.manager.get_service_for_plug.side_effect = configure
    plug = SimpleNamespace(
        id=1,
        printer_id=7,
        name="Printer plug",
        auto_off_pending=True,
        auto_off_pending_since=None,
        off_delay_mode="time",
        controls_printer_power=True,
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [plug]
    with patch("backend.app.core.database.async_session") as factory:
        factory.return_value.__aenter__.return_value = db
        await plug_guard.manager.resume_pending_auto_offs()
    plug_guard.service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_off_does_not_cut_power_during_preheat(plug_guard):
    block(plug_guard)
    plug = SimpleNamespace(
        id=1,
        printer_id=7,
        name="Printer plug",
        schedule_on_time=None,
        schedule_off_time=datetime.now().strftime("%H:%M"),
        controls_printer_power=True,
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [plug]
    with patch("backend.app.core.database.async_session") as factory:
        factory.return_value.__aenter__.return_value = db
        await plug_guard.manager._check_schedules()
    plug_guard.service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_idle_delayed_off_still_works(plug_guard):
    await plug_guard.manager._delayed_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 0)
    plug_guard.service.turn_off.assert_awaited_once()
    plug_guard.manager._mark_auto_off_executed.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_service_await_holds_reciprocal_preheat_interlock(plug_guard):
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def turn_off(plug):
        entered.set()
        await finish.wait()
        return True

    plug_guard.service.turn_off.side_effect = turn_off
    task = asyncio.create_task(plug_guard.manager._delayed_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 0))
    await asyncio.wait_for(entered.wait(), 1)
    assert 7 in plug_guard.owner.power_off_in_progress
    finish.set()
    await task
    assert 7 not in plug_guard.owner.power_off_in_progress
