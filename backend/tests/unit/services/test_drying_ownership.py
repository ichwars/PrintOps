from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.smart_plug import SmartPlug
from backend.app.services.automatic_drying_state import start_drying, stop_drying
from backend.app.services.drying_ownership import claim_queue_item
from backend.app.services.smart_plug_manager import SmartPlugManager


@pytest.fixture
async def reserved(test_engine, db_session, printer_factory):
    printer = await printer_factory(model="P2S")
    plan = DryingSchedule(
        printer_id=printer.id,
        ams_id=0,
        local_time="06:30",
        timezone="UTC",
        filament="PLA",
        temperature=45,
        duration_hours=4,
        enabled=False,
    )
    db_session.add(plan)
    await db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    run = DryingScheduleRun(
        schedule_id=plan.id,
        printer_id=printer.id,
        active_printer_id=printer.id,
        ams_id=0,
        occurrence_day=now.date().isoformat(),
        due_at=now,
        claimed_at=now,
        status="uncertain",
    )
    plug = SmartPlug(
        name="Printer power",
        printer_id=printer.id,
        ip_address="192.0.2.2",
        controls_printer_power=True,
        enabled=True,
        schedule_enabled=True,
        schedule_on_time="99:00",
        schedule_off_time=datetime.now().strftime("%H:%M"),
        auto_off_pending=True,
        auto_off_pending_since=now,
        off_delay_mode="time",
    )
    db_session.add_all([run, plug])
    await db_session.commit()
    return printer, run, plug, async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("executor", ["schedule", "delay", "temperature", "restart"])
async def test_all_automatic_power_off_executors_honor_durable_drying(reserved, executor):
    printer, _, plug, factory = reserved
    manager = SmartPlugManager()
    service = SimpleNamespace(turn_off=AsyncMock(return_value=True))
    with (
        patch("backend.app.core.database.async_session", factory),
        patch.object(manager, "get_service_for_plug", AsyncMock(return_value=service)),
        patch.object(manager, "_mark_auto_off_executed", AsyncMock()),
        patch("backend.app.services.smart_plug_manager.printer_manager") as printers,
        patch("backend.app.services.smart_plug_manager.asyncio.sleep", AsyncMock()),
    ):
        printers.is_print_active.return_value = False
        printers.get_status.return_value = SimpleNamespace(state="IDLE", temperatures={"nozzle": 20})
        if executor == "schedule":
            await manager._check_schedules()
        elif executor == "delay":
            await manager._delayed_off(plug.id, "tasmota", plug.ip_address, None, None, None, printer.id, 0)
        elif executor == "temperature":
            await manager._temp_based_off(plug.id, "tasmota", plug.ip_address, None, None, None, printer.id, 55)
        else:
            await manager.resume_pending_auto_offs()
        service.turn_off.assert_not_awaited()
        printers.mark_printer_offline.assert_not_called()


@pytest.mark.asyncio
async def test_accessory_power_and_released_reservations_do_not_block_off(reserved, db_session):
    printer, run, plug, _ = reserved
    manager = SmartPlugManager()
    service = SimpleNamespace(turn_off=AsyncMock(return_value=True))
    assert await manager._turn_off_if_safe(service, plug, printer.id, False, db_session)
    run.active_printer_id = None
    await db_session.commit()
    assert await manager._turn_off_if_safe(service, plug, printer.id, True, db_session)
    # Restart resume writes completion through another session; release the row lock first.
    assert not db_session.in_transaction()
    assert service.turn_off.await_count == 2


@pytest.mark.asyncio
async def test_new_queue_dispatch_and_legacy_drying_start_or_stop_are_blocked(reserved, db_session):
    printer, _, _, factory = reserved
    printer_id = printer.id
    item = PrintQueueItem(printer_id=printer_id, status="pending")
    db_session.add(item)
    await db_session.commit()
    assert not await claim_queue_item(db_session, item.id)
    await db_session.refresh(item)
    assert item.dispatching_at is None
    manager = SimpleNamespace(
        send_drying_command=AsyncMock(),
        get_status=lambda _: SimpleNamespace(raw_data={"ams": [{"id": "0", "dry_time": 240}]}),
    )
    assert not await start_drying(db_session, manager, printer.id, 0, 45, 4, "PLA")
    # Roll back the guard's read/write transaction before using a separate session.
    await db_session.rollback()
    await stop_drying({}, printer_id, manager, factory)
    manager.send_drying_command.assert_not_called()
