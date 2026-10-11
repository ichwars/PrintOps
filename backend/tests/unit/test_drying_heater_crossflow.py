"""Durable drying, heater ownership and power-off must share admission boundaries."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import backend.app.services.queue_keep_warm as keep_warm_module
import backend.app.services.scheduled_drying as drying_module
from backend.app.core.database import Base
from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.automatic_drying_state import start_drying
from backend.app.services.drying_ownership import printer_operation
from backend.app.services.preheat_ownership import PreheatLease, PreheatOwnership
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_keep_warm import QueueKeepWarm
from backend.app.services.scheduled_drying import ScheduledDryingService
from backend.app.services.smart_plug_manager import SmartPlugManager
from backend.tests.unit.services.test_scheduled_drying import NOW, fresh_state


@pytest.fixture
async def crossflow(tmp_path, test_engine, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admission.db'}", poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        printer = Printer(
            name="Admission",
            serial_number="TEST-ADMISSION",
            model="P2S",
            access_code="TEST-ONLY",
            ip_address="127.0.0.1",
        )
        db.add(printer)
        await db.flush()
        db.add(
            DryingSchedule(
                printer_id=printer.id,
                ams_id=0,
                local_time="06:30",
                timezone="Europe/Berlin",
                filament="PLA",
                temperature=45,
                duration_hours=4,
                enabled=True,
            )
        )
        await db.commit()
    state = fresh_state()
    state.state = "FINISH"
    state.temperatures = {"bed_target": 0, "nozzle": 20}
    client = MagicMock()
    client._heater_command_revisions = {}
    manager = MagicMock()
    manager.get_status.return_value = state
    manager.get_client.return_value = client
    manager.is_print_active.return_value = False
    manager.send_drying_command.return_value = True
    owner = PreheatOwnership(tmp_path / "owners")
    owner.item_status = AsyncMock(return_value="pending")
    keeper = QueueKeepWarm(owner)
    scheduler = SimpleNamespace(
        _drying_in_progress={},
        _get_bool_setting=AsyncMock(return_value=True),
        _get_int_setting=AsyncMock(return_value=10),
        _get_preheat_filament_targets=AsyncMock(return_value={"PLA": 45}),
        _get_printer=AsyncMock(return_value=printer),
    )
    head = SimpleNamespace(id=999, printer_id=printer.id)
    service = ScheduledDryingService(factory, manager)
    monkeypatch.setattr(drying_module, "preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.automatic_drying_state.preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.smart_plug_manager.preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.smart_plug_manager.printer_manager", manager)
    monkeypatch.setattr("backend.app.core.database.async_session", factory)
    monkeypatch.setattr(keep_warm_module, "compatible_keep_warm_target", lambda *args: 90)
    ctx = SimpleNamespace(
        factory=factory,
        printer=printer,
        state=state,
        manager=manager,
        client=client,
        owner=owner,
        keeper=keeper,
        scheduler=scheduler,
        head=head,
        drying=service,
    )
    yield ctx
    monitors = [lease.monitor for lease in owner.leases.values() if lease.monitor]
    owner.stop()
    await asyncio.gather(*monitors, return_exceptions=True)
    await engine.dispose()


async def refresh(ctx):
    async with ctx.factory() as db:
        await ctx.keeper.refresh(ctx.scheduler, db, [ctx.head], [], {}, True, ctx.manager)


async def recorded(ctx):
    async with ctx.factory() as db:
        return list((await db.execute(select(DryingScheduleRun))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["keep_warm", "drying"])
async def test_simultaneous_admission_has_one_owner_in_either_order(crossflow, monkeypatch, first):
    entered, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def pause_after_actual_row_lock(db, printer_id):
        async with printer_operation(db, printer_id):
            entered.set()
            await release.wait()
            yield

    first_module = keep_warm_module if first == "keep_warm" else drying_module
    monkeypatch.setattr(first_module, "printer_operation", pause_after_actual_row_lock)
    first_task = asyncio.create_task(refresh(crossflow) if first == "keep_warm" else crossflow.drying.tick(NOW))
    await asyncio.wait_for(entered.wait(), 2)
    second_task = asyncio.create_task(crossflow.drying.tick(NOW) if first == "keep_warm" else refresh(crossflow))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first_task, second_task)
    run = (await recorded(crossflow))[0]
    if first == "keep_warm":
        assert (run.status, run.reason, run.active_printer_id) == ("skipped", "printer_busy", None)
        assert crossflow.owner.blocks_power_off(crossflow.printer.id)
        crossflow.client.set_bed_temperature.assert_called_once_with(90)
        crossflow.manager.send_drying_command.assert_not_called()
    else:
        assert (run.status, run.active_printer_id) == ("awaiting_ack", crossflow.printer.id)
        assert not crossflow.owner.blocks_power_off(crossflow.printer.id)
        assert not crossflow.keeper.entries
        crossflow.client.set_bed_temperature.assert_not_called()
        crossflow.manager.send_drying_command.assert_called_once()


def hold_heater_owner(crossflow, kind):
    printer_id = crossflow.printer.id
    if kind == "retained":
        crossflow.owner.path(printer_id).parent.mkdir(parents=True)
        crossflow.owner.path(printer_id).write_text("unresolved prior heater intent")
    elif kind == "power_off":
        crossflow.owner.power_off_in_progress.add(printer_id)
    else:
        crossflow.owner.leases[printer_id] = PreheatLease(
            crossflow.owner, printer_id, crossflow.head.id, crossflow.manager, purpose=kind, recovered=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["dispatch", "keep_warm", "retained", "power_off"])
async def test_every_existing_heater_or_power_off_owner_blocks_daily_start(crossflow, kind):
    hold_heater_owner(crossflow, kind)
    await crossflow.drying.tick(NOW)
    assert (await recorded(crossflow))[0].reason == "printer_busy"
    crossflow.manager.send_drying_command.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["dispatch", "keep_warm", "retained", "power_off"])
async def test_legacy_automatic_drying_cannot_bypass_heater_ownership(crossflow, kind):
    hold_heater_owner(crossflow, kind)
    async with crossflow.factory() as db:
        assert not await start_drying(db, crossflow.manager, crossflow.printer.id, 0, 45, 4, "PLA")
    crossflow.manager.send_drying_command.assert_not_called()


@pytest.mark.asyncio
async def test_daily_reservation_blocks_dispatch_before_preheat_can_acquire(crossflow, monkeypatch):
    await crossflow.drying.tick(NOW)
    scheduler = PrintScheduler()
    scheduler._start_print = AsyncMock()
    monkeypatch.setattr("backend.app.services.print_scheduler.async_session", crossflow.factory)
    async with crossflow.factory() as db:
        item = PrintQueueItem(printer_id=crossflow.printer.id, status="pending")
        db.add(item)
        await db.commit()
        assert not await scheduler._dispatch_with_claim(db, item)
    scheduler._start_print.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "exception"])
async def test_power_off_finishing_ahead_of_daily_admission_invalidates_old_idle_proof(crossflow, outcome):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def turn_off(plug):
        entered.set()
        await finish.wait()
        if outcome == "exception":
            raise TimeoutError("Hardware reply lost")
        return outcome == "success"

    power = SimpleNamespace(turn_off=AsyncMock(side_effect=turn_off))
    off_task = asyncio.create_task(SmartPlugManager()._turn_off_if_safe(power, object(), crossflow.printer.id))
    await asyncio.wait_for(entered.wait(), 2)
    assert crossflow.printer.id in crossflow.owner.power_off_in_progress
    daily_task = asyncio.create_task(crossflow.drying.tick(NOW))
    await asyncio.sleep(0)
    finish.set()
    if outcome == "exception":
        with pytest.raises(TimeoutError):
            await off_task
    else:
        assert await off_task is (outcome == "success")
    await daily_task
    assert (await recorded(crossflow))[0].reason == "telemetry_stale"
    crossflow.manager.send_drying_command.assert_not_called()
