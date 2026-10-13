"""Passive ambient streaks use real scheduler dispatch and never own manual dries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.print_scheduler import PrintScheduler


def unit(ams_id=0, humidity=75, **extra):
    return {
        "id": ams_id,
        "module_type": "n3f",
        "dry_time": 0,
        "humidity_raw": humidity,
        "tray": [{"tray_type": "PLA"}],
        "dry_sf_reason": [],
        **extra,
    }


@pytest.fixture
def rig():
    scheduler = PrintScheduler()
    scheduler._is_printer_idle = MagicMock(return_value=True)
    settings = {"ambient_drying_enabled": "true", "ambient_drying_sustained_minutes": "2", "ams_humidity_fair": "60"}
    states = {1: PrinterState(raw_data={"ams": [unit()]}, firmware_version="01.03.00.00")}
    now = [1000.0]
    excluded = set()
    db = AsyncMock()
    db.scalar.return_value = None

    async def execute(stmt):
        result = MagicMock()
        keys = list(stmt.compile().params.values())
        if "FROM settings" in str(stmt):
            value = settings.get(keys[0])
            result.scalar_one_or_none.return_value = None if value is None else SimpleNamespace(value=value)
        elif "drying_schedule_runs" in str(stmt):
            result.scalars.return_value.all.return_value = [1] if db.scalar.return_value else []
        else:
            result.scalars.return_value = [SimpleNamespace(id=pid) for pid in states if pid not in excluded]
        return result

    db.execute.side_effect = execute
    with (
        patch("backend.app.services.print_scheduler.printer_manager") as manager,
        patch("backend.app.services.print_scheduler.time.monotonic", side_effect=lambda: now[0]),
        patch("backend.app.services.print_scheduler.async_session") as session,
    ):
        manager.get_status.side_effect = states.get
        manager.is_connected.return_value = True
        manager.get_model.return_value = "H2D"
        manager.send_drying_command.return_value = True
        session.return_value.__aenter__.return_value = db
        yield SimpleNamespace(
            scheduler=scheduler, settings=settings, states=states, now=now, db=db, manager=manager, excluded=excluded
        )


async def tick(rig, seconds=0, queue=(), busy=()):
    rig.now[0] += seconds
    await rig.scheduler._check_auto_drying(rig.db, list(queue), set(busy))


@pytest.mark.asyncio
async def test_short_spike_waits_without_claiming_drying(rig):
    await tick(rig)
    await tick(rig, 30)
    rig.states[1].raw_data["ams"][0]["humidity_raw"] = 60
    await tick(rig, 30)
    rig.manager.send_drying_command.assert_not_called()
    assert rig.scheduler._drying_in_progress == {}


@pytest.mark.asyncio
async def test_sustained_high_starts_at_duration_and_spends_streak(rig):
    await tick(rig)
    await tick(rig, 60)
    rig.manager.send_drying_command.assert_not_called()
    await tick(rig, 60)
    rig.manager.send_drying_command.assert_called_once_with(1, 0, 45, 12, mode=1, filament="PLA")
    assert rig.scheduler._ambient_humidity.streaks == {}
    rig.manager.send_drying_command.reset_mock()
    await tick(rig, 30)
    rig.manager.send_drying_command.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [None, "0"])
async def test_default_zero_starts_immediately(rig, configured):
    rig.settings["ambient_drying_sustained_minutes"] = configured
    await tick(rig)
    rig.manager.send_drying_command.assert_called_once_with(1, 0, 45, 12, mode=1, filament="PLA")


@pytest.mark.asyncio
async def test_per_printer_and_ams_independence(rig):
    rig.states[1].raw_data["ams"].append(unit(1, humidity=40))
    rig.states[2] = PrinterState(raw_data={"ams": [unit()]}, firmware_version="01.03.00.00")
    await tick(rig)
    rig.states[1].raw_data["ams"][1]["humidity_raw"] = 75
    rig.states[2].raw_data["ams"][0]["humidity_raw"] = 40
    await tick(rig, 60)
    await tick(rig, 60)
    assert rig.manager.send_drying_command.call_args_list == [((1, 0, 45, 12), {"mode": 1, "filament": "PLA"})]
    await tick(rig, 60)
    assert rig.manager.send_drying_command.call_args.args[:2] == (1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["low", "threshold", "tray", "disable", "disconnect", "missing_long", "stale"])
async def test_broken_continuity_requires_fresh_duration(rig, change):
    await tick(rig)
    await tick(rig, 60)
    ams = rig.states[1].raw_data["ams"][0]
    if change == "low":
        ams["humidity_raw"] = 60
    elif change == "threshold":
        rig.settings["ams_humidity_fair"] = "70"
    elif change == "tray":
        ams["tray"] = [{"tray_type": "PETG"}]
    elif change == "disable":
        rig.settings["ambient_drying_enabled"] = "false"
    elif change == "disconnect":
        rig.manager.is_connected.return_value = False
    elif change == "missing_long":
        ams.pop("humidity_raw")
    await tick(rig, 121 if change == "stale" else 30)
    ams["humidity_raw"] = 75
    rig.settings["ambient_drying_enabled"] = "true"
    rig.manager.is_connected.return_value = True
    await tick(rig, 121 if change == "missing_long" else 30)
    rig.manager.send_drying_command.assert_not_called()
    await tick(rig, 60)
    await tick(rig, 60)
    assert rig.manager.send_drying_command.call_count >= 1


@pytest.mark.asyncio
async def test_missing_reading_is_not_low_but_cannot_start(rig):
    await tick(rig)
    await tick(rig, 60)
    ams = rig.states[1].raw_data["ams"][0]
    ams.pop("humidity_raw")
    await tick(rig, 60)
    rig.manager.send_drying_command.assert_not_called()
    ams["humidity_raw"] = 75
    await tick(rig, 30)
    rig.manager.send_drying_command.assert_called_once()


@pytest.mark.asyncio
async def test_queue_and_print_only_are_exempt(rig):
    rig.settings.update(queue_drying_enabled="true", ambient_drying_enabled="true")
    scheduled = SimpleNamespace(printer_id=1, scheduled_time=object(), manual_start=False)
    await tick(rig, queue=[scheduled])
    rig.manager.send_drying_command.assert_called_once()
    rig.manager.send_drying_command.reset_mock()
    rig.scheduler._drying_in_progress.clear()
    rig.settings.update(queue_drying_enabled="false", ambient_drying_enabled="false", print_drying_enabled="true")
    await tick(rig, busy=[1])
    rig.manager.send_drying_command.assert_called_once_with(1, 0, 40, 12, mode=1, filament="PLA")


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["reservation", "plate", "busy", "power", "firmware", "model", "block"])
async def test_elapsed_streak_cannot_bypass_safety(rig, denial):
    if denial == "reservation":
        rig.db.scalar.return_value = 1
        rig.db.scalars.return_value.all.return_value = [1]
    elif denial == "plate":
        rig.scheduler._is_printer_idle.return_value = False
    elif denial == "power":
        rig.states[1].raw_data["ams"][0]["dry_sf_reason"] = [1]
    elif denial == "firmware":
        rig.settings["print_drying_enabled"] = "true"
        rig.states[1].firmware_version = "01.00.00.00"
    elif denial == "model":
        rig.manager.get_model.return_value = "A1"
    elif denial == "block":
        rig.settings["queue_drying_block"] = "true"
    pending = [SimpleNamespace(printer_id=1, scheduled_time=None, manual_start=True)] if denial == "block" else []
    busy = [1] if denial in {"busy", "firmware"} else []
    await tick(rig, queue=pending, busy=busy)
    await tick(rig, 60, queue=pending, busy=busy)
    await tick(rig, 60, queue=pending, busy=busy)
    rig.manager.send_drying_command.assert_not_called()
    assert rig.scheduler._drying_in_progress == {}


@pytest.mark.asyncio
async def test_manual_cycle_never_becomes_owned_or_stopped(rig):
    rig.states[1].raw_data["ams"][0]["dry_time"] = 100
    await tick(rig)
    assert rig.scheduler._drying_in_progress == {}
    rig.settings["ambient_drying_enabled"] = "false"
    await tick(rig)
    rig.manager.send_drying_command.assert_not_called()


@pytest.mark.asyncio
async def test_stop_only_automatic_ams_and_cleans_streak(rig):
    rig.settings["ambient_drying_sustained_minutes"] = "0"
    rig.states[1].raw_data["ams"].append(unit(1, dry_time=100))
    await tick(rig)
    rig.states[1].raw_data["ams"][0]["dry_time"] = 100
    rig.manager.send_drying_command.reset_mock()
    await rig.scheduler._stop_drying(1)
    rig.manager.send_drying_command.assert_called_once_with(1, 0, 0, 0, mode=0)
    assert rig.scheduler._ambient_humidity.streaks == {}
    assert rig.scheduler._drying_owned_ams == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("removal", ["printer", "ams", "running"])
async def test_cleanup_observation_on_disappearance_or_running_cycle(rig, removal):
    await tick(rig)
    assert rig.scheduler._ambient_humidity.streaks
    if removal == "printer":
        rig.states.clear()
    elif removal == "ams":
        rig.states[1].raw_data["ams"] = []
    else:
        rig.states[1].raw_data["ams"][0]["dry_time"] = 100
    await tick(rig, 30)
    assert rig.scheduler._ambient_humidity.streaks == {}


@pytest.mark.asyncio
async def test_ambient_midprint_waits_and_keeps_temperature_cap(rig):
    rig.settings["print_drying_enabled"] = "true"
    await tick(rig, busy=[1])
    await tick(rig, 60, busy=[1])
    rig.manager.send_drying_command.assert_not_called()
    await tick(rig, 60, busy=[1])
    rig.manager.send_drying_command.assert_called_once_with(1, 0, 40, 12, mode=1, filament="PLA")


@pytest.mark.asyncio
async def test_interval_scaled_gap_and_exact_boundary(rig):
    rig.scheduler._check_interval = 45
    rig.settings["ambient_drying_sustained_minutes"] = "4"
    await tick(rig)
    await tick(rig, 180)  # Exactly four intervals retains continuity.
    rig.manager.send_drying_command.assert_not_called()
    await tick(rig, 60)
    rig.manager.send_drying_command.assert_called_once()


@pytest.mark.asyncio
async def test_failed_start_keeps_passive_streak_and_does_not_claim(rig):
    rig.manager.send_drying_command.return_value = False
    await tick(rig)
    await tick(rig, 60)
    await tick(rig, 60)
    assert rig.scheduler._drying_in_progress == {}
    assert rig.scheduler._drying_owned_ams == {}
    assert rig.scheduler._ambient_humidity.streaks
    rig.manager.send_drying_command.return_value = True
    await tick(rig, 30)
    assert rig.scheduler._drying_owned_ams == {1: {0}}
    assert rig.scheduler._ambient_humidity.streaks == {}


@pytest.mark.asyncio
async def test_running_cycle_spends_wait_and_low_humidity_does_not_stop(rig):
    await tick(rig)
    await tick(rig, 60)
    await tick(rig, 60)
    ams = rig.states[1].raw_data["ams"][0]
    ams.update(dry_time=100, humidity_raw=20)
    rig.manager.send_drying_command.reset_mock()
    await tick(rig, 60)
    rig.manager.send_drying_command.assert_not_called()
    assert rig.scheduler._drying_owned_ams == {1: {0}}
    assert rig.scheduler._ambient_humidity.streaks == {}
    ams["dry_time"] = 0
    await tick(rig, 30)
    assert rig.scheduler._drying_owned_ams == {}
    assert rig.scheduler._drying_in_progress == {}


@pytest.mark.asyncio
async def test_reserved_printer_is_skipped_before_passive_observation(rig):
    rig.db.scalar.return_value = 1
    await tick(rig)
    assert rig.scheduler._ambient_humidity.streaks == {}
    rig.manager.get_status.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_stop_resets_passive_wait(rig):
    await tick(rig)
    rig.scheduler.stop()
    assert rig.scheduler._ambient_humidity.streaks == {}


@pytest.mark.asyncio
async def test_inactive_printer_cleans_ownership_without_command(rig):
    rig.settings["ambient_drying_sustained_minutes"] = "0"
    await tick(rig)
    rig.states[1].raw_data["ams"][0]["dry_time"] = 100
    rig.excluded.add(1)
    rig.manager.send_drying_command.reset_mock()
    await tick(rig, 30)
    assert rig.scheduler._drying_owned_ams == {}
    assert rig.scheduler._drying_in_progress == {}
    rig.manager.send_drying_command.assert_not_called()
