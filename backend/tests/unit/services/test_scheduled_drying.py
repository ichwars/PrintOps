import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.database import Base
from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.drying_telemetry import DryingObservation
from backend.app.services.scheduled_drying import ScheduledDryingService, scheduled_drying_block_reason

NOW = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deterministic_scheduler_clock(monkeypatch):
    """Synthetic telemetry must not expire when the real calendar advances."""

    class SchedulerDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr("backend.app.services.scheduled_drying.datetime", SchedulerDateTime)


def fresh_state(now=NOW, kind="n3f", remaining=0):
    state = PrinterState(connected=True, state="IDLE", firmware_version="01.03.00.00")
    state.drying_telemetry.firmware_observed_at = now.timestamp()
    state.drying_telemetry.idle_observed_at = now.timestamp()
    state.drying_telemetry.modules[0] = (kind, "05.00.22.22")
    state.drying_telemetry.units[0] = DryingObservation(remaining, now.timestamp(), kind, True, False)
    return state


@pytest.mark.parametrize(
    "model,firmware,kind,reason",
    [
        ("P2S", "01.03.00.00", "n3f", None),
        ("X1C", "01.12.00.00", "ams", "unsupported_ams"),
        ("Unknown", "99.00.00.00", "n3f", "unsupported_printer"),
        ("P1S", "99.00.00.00", "n3f", "unsupported_printer"),
        ("P2S", "01.01.00.00", "n3f", "unsupported_printer"),
        ("P2S", "invalid", "n3f", "unsupported_printer"),
    ],
)
def test_strict_actual_model_firmware_and_ams_gate(model, firmware, kind, reason):
    state = fresh_state(kind=kind)
    state.firmware_version = firmware
    printer = SimpleNamespace(model=model, is_active=True)
    assert scheduled_drying_block_reason(printer, state, 0, 45, NOW) == reason


@pytest.mark.parametrize("field", ["idle_observed_at", "firmware_observed_at"])
def test_unknown_telemetry_never_enables_a_plan(field):
    state = fresh_state()
    setattr(state.drying_telemetry, field, 0)
    assert scheduled_drying_block_reason(SimpleNamespace(model="P2S", is_active=True), state, 0, 45, NOW)


@pytest.fixture
async def scenario(test_engine, db_session, printer_factory):
    printer = await printer_factory(model="P2S")
    plan = DryingSchedule(
        printer_id=printer.id,
        ams_id=0,
        local_time="06:30",
        timezone="Europe/Berlin",
        filament="PLA",
        temperature=45,
        duration_hours=4,
        enabled=True,
    )
    db_session.add(plan)
    await db_session.commit()
    state = fresh_state()
    manager = SimpleNamespace(get_status=lambda _: state, send_drying_command=MagicMock(return_value=True))
    service = ScheduledDryingService(async_sessionmaker(test_engine, expire_on_commit=False), manager)
    return printer, plan, state, manager, service


async def runs(db_session):
    db_session.expire_all()
    return list((await db_session.execute(select(DryingScheduleRun).order_by(DryingScheduleRun.id))).scalars())


@pytest.mark.asyncio
async def test_duplicate_ticks_and_scheduler_instances_publish_once(scenario, db_session):
    _, _, _, manager, service = scenario
    other = ScheduledDryingService(service.session_factory, manager)
    await asyncio.gather(service.tick(NOW), other.tick(NOW))
    await service.tick(NOW + timedelta(seconds=30))
    assert manager.send_drying_command.call_count == 1
    assert manager.send_drying_command.call_args.kwargs["qos"] == 0
    assert [run.status for run in await runs(db_session)] == ["awaiting_ack"]


@pytest.mark.asyncio
async def test_independent_worker_loops_share_one_database_claim(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'workers.db'}"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        printer = Printer(
            name="Drying worker fixture",
            serial_number="TEST-DRYING",
            model="P2S",
            ip_address="127.0.0.1",
            access_code="TEST-ONLY",
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
    await engine.dispose()
    barrier = threading.Barrier(2)
    manager = SimpleNamespace(get_status=lambda _: fresh_state(), send_drying_command=MagicMock(return_value=True))

    def worker():
        async def run():
            worker_engine = create_async_engine(url, poolclass=NullPool)
            try:
                service = ScheduledDryingService(async_sessionmaker(worker_engine, expire_on_commit=False), manager)
                barrier.wait(timeout=10)
                await service.tick(NOW)
            finally:
                await worker_engine.dispose()

        asyncio.run(run())

    await asyncio.gather(asyncio.to_thread(worker), asyncio.to_thread(worker))
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        recorded = list((await db.execute(select(DryingScheduleRun))).scalars())
        assert len(recorded) == 1
        assert recorded[0].status == "awaiting_ack"
    await engine.dispose()
    assert manager.send_drying_command.call_count == 1


@pytest.mark.asyncio
async def test_real_running_then_stopped_observation_completes(scenario, db_session):
    _, _, state, _, service = scenario
    await service.tick(NOW)
    later = NOW + timedelta(seconds=10)
    state.drying_telemetry.units[0] = DryingObservation(240, later.timestamp(), "n3f", True, False)
    await service.tick(later)
    assert (await runs(db_session))[0].status == "running"
    stopped = NOW + timedelta(seconds=20)
    state.drying_telemetry.units[0] = DryingObservation(0, stopped.timestamp(), "n3f", True, False)
    await service.tick(stopped)
    run = (await runs(db_session))[0]
    assert run.status == "completed"
    assert run.active_printer_id is None


@pytest.mark.asyncio
async def test_cached_preclaim_positive_other_ams_and_missing_values_do_not_acknowledge(scenario, db_session):
    _, _, state, _, service = scenario
    await service.tick(NOW)
    state.drying_telemetry.units[0] = DryingObservation(240, NOW.timestamp(), "n3f", True, False)
    state.drying_telemetry.units[1] = DryingObservation(
        240, (NOW + timedelta(seconds=10)).timestamp(), "n3f", True, False
    )
    await service.tick(NOW + timedelta(seconds=10))
    assert (await runs(db_session))[0].status == "awaiting_ack"
    state.drying_telemetry.units[0] = DryingObservation(
        None, (NOW + timedelta(seconds=20)).timestamp(), "n3f", True, False
    )
    await service.tick(NOW + timedelta(seconds=20))
    assert (await runs(db_session))[0].status == "awaiting_ack"


@pytest.mark.asyncio
async def test_restart_after_uncertain_publish_never_resends_or_infers_elapsed_completion(scenario, db_session):
    printer, plan, _, manager, service = scenario
    printer_id = printer.id
    db_session.add(
        DryingScheduleRun(
            schedule_id=plan.id,
            printer_id=printer.id,
            active_printer_id=printer.id,
            ams_id=0,
            occurrence_day="2026-11-01",
            due_at=NOW.replace(tzinfo=None),
            claimed_at=NOW.replace(tzinfo=None),
            status="claimed",
            reason=None,
        )
    )
    await db_session.commit()
    restarted = ScheduledDryingService(service.session_factory, manager)
    await restarted.tick(NOW + timedelta(hours=4))
    run = (await runs(db_session))[0]
    assert run.status == "uncertain"
    assert run.active_printer_id == printer_id
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_failed_publish_retains_uncertain_ownership(scenario, db_session):
    printer, _, _, manager, service = scenario
    printer_id = printer.id
    manager.send_drying_command.side_effect = RuntimeError("connection lost")
    await service.tick(NOW)
    await service.tick(NOW + timedelta(seconds=30))
    run = (await runs(db_session))[0]
    assert run.status == "uncertain"
    assert run.active_printer_id == printer_id
    assert manager.send_drying_command.call_count == 1


@pytest.mark.asyncio
async def test_late_plan_is_skipped_without_catchup(scenario, db_session):
    _, _, _, manager, service = scenario
    await service.tick(NOW + timedelta(minutes=6))
    run = (await runs(db_session))[0]
    assert (run.status, run.reason) == ("skipped", "missed")
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_disabled_plan_never_claims(scenario, db_session):
    _, plan, _, manager, service = scenario
    plan.enabled = False
    await db_session.commit()
    await service.tick(NOW)
    assert await runs(db_session) == []
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_queued_owner_prevents_drying(scenario, db_session):
    printer, _, _, manager, service = scenario
    db_session.add(PrintQueueItem(printer_id=printer.id, status="pending"))
    await db_session.commit()
    await service.tick(NOW)
    assert (await runs(db_session))[0].reason == "queue_conflict"
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_stale_idle_or_drying_telemetry_skips(scenario, db_session):
    _, _, state, manager, service = scenario
    state.drying_telemetry.idle_observed_at = NOW.timestamp() - 61
    await service.tick(NOW)
    assert (await runs(db_session))[0].reason == "telemetry_stale"
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_observation_during_publication_is_not_start_confirmation(scenario, db_session):
    _, _, state, manager, service = scenario
    service.clock = lambda: NOW + timedelta(seconds=5)

    def publish(*args, **kwargs):
        state.drying_telemetry.units[0] = DryingObservation(
            240, (NOW + timedelta(seconds=5)).timestamp(), "n3f", True, False
        )
        service.clock = lambda: NOW + timedelta(seconds=6)
        return True

    manager.send_drying_command.side_effect = publish
    await service.tick(NOW)
    await service.tick(NOW + timedelta(seconds=10))
    assert (await runs(db_session))[0].status == "awaiting_ack"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "detached", "disconnected", "unavailable", "printing"])
async def test_lost_or_conflicting_observation_retains_uncertain_owner(scenario, db_session, change):
    _, _, state, manager, service = scenario
    await service.tick(NOW)
    state.drying_telemetry.units[0] = DryingObservation(
        240, (NOW + timedelta(seconds=10)).timestamp(), "n3f", True, False
    )
    await service.tick(NOW + timedelta(seconds=10))
    if change == "missing":
        state.drying_telemetry.units[0] = DryingObservation(
            None, (NOW + timedelta(seconds=20)).timestamp(), "n3f", True, False
        )
    elif change == "detached":
        state.drying_telemetry.modules.clear()
    elif change == "disconnected":
        state.connected = False
    elif change == "unavailable":
        manager.get_status = lambda _: None
    else:
        state.state = "RUNNING"
    await service.tick(NOW + timedelta(seconds=20))
    run = (await runs(db_session))[0]
    assert run.status == "uncertain"
    assert run.active_printer_id is not None
    assert run.finished_at is None


@pytest.mark.asyncio
async def test_disabled_plan_still_observes_owned_running_cycle(scenario, db_session):
    _, plan, state, manager, service = scenario
    await service.tick(NOW)
    plan.enabled = False
    await db_session.commit()
    state.drying_telemetry.units[0] = DryingObservation(
        20, (NOW + timedelta(seconds=10)).timestamp(), "n3f", True, False
    )
    await service.tick(NOW + timedelta(seconds=10))
    state.drying_telemetry.units[0] = DryingObservation(
        0, (NOW + timedelta(seconds=20)).timestamp(), "n3f", True, False
    )
    await ScheduledDryingService(service.session_factory, manager).tick(NOW + timedelta(seconds=20))
    assert (await runs(db_session))[0].status == "completed"
    assert manager.send_drying_command.call_count == 1


@pytest.mark.asyncio
async def test_two_enabled_plans_cannot_own_same_printer(scenario, db_session):
    printer, _, _, manager, service = scenario
    db_session.add(
        DryingSchedule(
            printer_id=printer.id,
            ams_id=0,
            local_time="06:30",
            timezone="Europe/Berlin",
            filament="PETG",
            temperature=65,
            duration_hours=12,
            enabled=True,
        )
    )
    await db_session.commit()
    await service.tick(NOW)
    outcomes = await runs(db_session)
    assert [run.status for run in outcomes] == ["awaiting_ack", "skipped"]
    assert outcomes[1].reason == "drying_owner_conflict"
    assert manager.send_drying_command.call_count == 1


@pytest.mark.asyncio
async def test_dst_gap_creates_explained_skip_and_repeated_hour_never_replays(scenario, db_session):
    _, plan, state, manager, service = scenario
    plan.local_time = "02:30"
    await db_session.commit()
    spring = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    service.clock = lambda: spring
    await service.tick(spring)
    assert (await runs(db_session))[0].reason == "dst_gap"
    first = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    service.clock = lambda: first
    state.drying_telemetry = fresh_state(first).drying_telemetry
    await service.tick(first)
    await service.tick(first + timedelta(hours=1))
    assert manager.send_drying_command.call_count == 1
    assert len(await runs(db_session)) == 2


@pytest.mark.asyncio
async def test_corrupt_stored_plan_and_naive_clock_never_publish(scenario, db_session):
    _, plan, _, manager, service = scenario
    await service.tick(NOW.replace(tzinfo=None))
    assert await runs(db_session) == []
    await db_session.execute(update(DryingSchedule).values(timezone="invalid/timezone"))
    await db_session.commit()
    await service.tick(NOW)
    assert (await runs(db_session))[0].reason == "invalid_plan"
    assert manager.send_drying_command.call_count == 0


@pytest.mark.asyncio
async def test_midnight_grace_belongs_to_previous_local_day_and_does_not_replay(scenario, db_session):
    _, plan, state, manager, service = scenario
    plan.local_time, plan.timezone = "23:59", "UTC"
    await db_session.commit()
    midnight = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    state.drying_telemetry = fresh_state(midnight).drying_telemetry
    await service.tick(midnight)
    await service.tick(midnight + timedelta(seconds=30))
    assert (await runs(db_session))[0].occurrence_day == "2026-11-01"
    assert manager.send_drying_command.call_count == 1


@pytest.mark.asyncio
async def test_claimed_parameters_survive_plan_edits(scenario, db_session):
    import json

    _, _, _, _, service = scenario
    await service.tick(NOW)
    await db_session.execute(update(DryingSchedule).values(temperature=65, duration_hours=12, filament="PETG"))
    await db_session.commit()
    run = (await runs(db_session))[0]
    saved = json.loads(run.parameters_json)
    assert (saved["temperature"], saved["duration_hours"], saved["filament"]) == (45, 4, "PLA")
