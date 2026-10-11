"""Every keep-warm exit must retain or unwind bounded heater ownership."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.heater_commands import set_heater_temperature
from backend.app.services.preheat_ownership import PreheatOwnership
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_keep_warm import QueueKeepWarm
from backend.tests.unit.test_queue_keep_warm import compatible  # noqa: F401


@pytest.fixture
async def lifecycle(compatible):
    owner = PreheatOwnership(compatible.path / "owners")
    owner.item_status = AsyncMock(return_value="pending")
    owner.poll_seconds = 0.001
    keeper = QueueKeepWarm(owner)
    client = MagicMock(state=compatible.state)
    client._heater_command_revisions = {}
    client.send_gcode.return_value = True
    client.set_bed_temperature.side_effect = lambda target: set_heater_temperature(client, "bed", target)
    pm = MagicMock()
    pm.get_status.return_value = compatible.state
    pm.get_client.return_value = client
    pm.is_connected.return_value = True
    pm.is_awaiting_plate_clear.return_value = True
    scheduler = PrintScheduler()
    values = {"queue_keep_bed_warm": True, "preheat_enabled": True}
    scheduler._get_bool_setting = AsyncMock(side_effect=lambda db, key, default=False: values.get(key, default))
    scheduler._get_int_setting = AsyncMock(return_value=10)
    scheduler._get_preheat_filament_targets = AsyncMock(return_value={"ASA": 45, "PA": 50})
    scheduler._get_printer = AsyncMock(return_value=compatible.printer)
    db = AsyncMock()
    db.scalar.return_value = None
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = compatible.previous
    context = SimpleNamespace(
        data=compatible,
        owner=owner,
        keeper=keeper,
        client=client,
        pm=pm,
        scheduler=scheduler,
        db=db,
        flags=values,
    )
    yield context
    monitors = [lease.monitor for lease in owner.leases.values() if lease.monitor]
    owner.stop()
    await asyncio.gather(*monitors, return_exceptions=True)


async def refresh(ctx, *, items=None, selected=None, interlocked=None, plate_clear=True):
    await ctx.keeper.refresh(
        ctx.scheduler,
        ctx.db,
        [ctx.data.next] if items is None else items,
        selected or [],
        interlocked or {},
        plate_clear,
        ctx.pm,
    )


@pytest.mark.asyncio
async def test_compatible_hold_sends_only_real_bed_target_once_and_never_renews_deadline(lifecycle):
    await refresh(lifecycle)
    lease = lifecycle.owner.leases[7]
    deadline = lease.expires_at
    await refresh(lifecycle)
    assert lease.expires_at == deadline
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)
    assert lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["queue_keep_bed_warm", "preheat_enabled"])
async def test_disabled_feature_or_preheat_does_not_heat(lifecycle, flag):
    lifecycle.flags[flag] = False
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature.assert_not_called()
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_no_plate_clear_gate_does_not_heat(lifecycle):
    await refresh(lifecycle, plate_clear=False)
    lifecycle.client.set_bed_temperature.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["queue_end", "disabled", "interlock", "incompatible", "manual_abort"])
async def test_queue_end_disabled_incompatible_or_abort_releases_owned_bed(lifecycle, reason):
    await refresh(lifecycle)
    if reason == "queue_end":
        await refresh(lifecycle, items=[])
    elif reason == "disabled":
        lifecycle.flags["queue_keep_bed_warm"] = False
        await refresh(lifecycle)
    elif reason == "interlock":
        await refresh(lifecycle, interlocked={7: "Open door"})
    elif reason == "incompatible":
        lifecycle.data.next.preheat_override = "off"
        await refresh(lifecycle)
    else:
        lifecycle.owner.item_status.return_value = "cancelled"
        await asyncio.wait_for(lifecycle.owner.leases[7].monitor, 1)
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_hold_deadline_stops_once_without_failing_or_reheating_next_job(lifecycle):
    await refresh(lifecycle)
    lease = lifecycle.owner.leases[7]
    lease.expires_at = 0
    await asyncio.wait_for(lease.monitor, 1)
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    await refresh(lifecycle)
    await refresh(lifecycle)
    assert lifecycle.client.set_bed_temperature.call_count == 2
    assert lifecycle.data.next.status == "pending"


@pytest.mark.asyncio
async def test_selected_hold_stays_owned_until_worker_claims(lifecycle):
    await refresh(lifecycle)
    await refresh(lifecycle, selected=[lifecycle.data.next.id])
    assert lifecycle.owner.blocks_power_off(7)
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)


@pytest.mark.asyncio
async def test_claim_failure_releases_hold_without_starting_preheat(lifecycle):
    await refresh(lifecycle)
    with (
        patch("backend.app.services.print_scheduler.preheat_ownership", lifecycle.owner),
        patch.object(lifecycle.scheduler, "_claim_for_dispatch", AsyncMock(return_value=False)),
    ):
        assert not await lifecycle.scheduler._dispatch_with_claim(lifecycle.db, lifecycle.data.next)
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_vanished_row_releases_selected_hold(lifecycle):
    await refresh(lifecycle)
    lifecycle.db.get.return_value = None
    with (
        patch("backend.app.services.print_scheduler.preheat_ownership", lifecycle.owner),
        patch("backend.app.services.print_scheduler.async_session") as factory,
    ):
        factory.return_value.__aenter__.return_value = lifecycle.db
        await lifecycle.scheduler._dispatch_one(lifecycle.data.next.id)
    lifecycle.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
async def test_failed_adopted_dispatch_rolls_back_after_source_or_preheat_skip(lifecycle):
    await refresh(lifecycle)
    async with lifecycle.owner.dispatch(lifecycle.data.next, lifecycle.pm):
        assert lifecycle.owner.leases[7].purpose == "handoff"
        lifecycle.owner.release_skipped_preheat()
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_manual_same_target_during_hold_is_never_stopped(lifecycle):
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature(90)
    await refresh(lifecycle, items=[])
    assert lifecycle.client.set_bed_temperature.call_count == 2
    assert lifecycle.data.state.temperatures["bed_target"] == 90


@pytest.mark.asyncio
async def test_manual_same_target_releases_hold_and_cannot_be_adopted_or_rearmed(lifecycle):
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature(90)
    assert not lifecycle.owner.can_adopt(lifecycle.data.next)
    await refresh(lifecycle, selected=[lifecycle.data.next.id])
    await refresh(lifecycle)
    assert lifecycle.client.set_bed_temperature.call_count == 2
    assert lifecycle.data.state.temperatures["bed_target"] == 90
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["reservation", "telemetry", "malformed"])
async def test_drying_reservation_or_telemetry_prevents_hold(lifecycle, source):
    if source == "reservation":
        lifecycle.scheduler._drying_in_progress[7] = 1
    else:
        lifecycle.data.state.raw_data["ams"][0]["dry_time"] = 60 if source == "telemetry" else "unknown"
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature.assert_not_called()


@pytest.mark.asyncio
async def test_drying_started_during_hold_releases_only_owned_bed(lifecycle):
    await refresh(lifecycle)
    lifecycle.scheduler._drying_in_progress[7] = 1
    await refresh(lifecycle, selected=[lifecycle.data.next.id])
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_replaced_mqtt_session_cannot_adopt_or_stop_unknown_hold(lifecycle):
    await refresh(lifecycle)
    lifecycle.pm.get_client.return_value = MagicMock()
    assert not lifecycle.owner.can_adopt(lifecycle.data.next)
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)
    assert lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_adopted_preheat_extends_ownership_without_duplicate_heat_and_rolls_back_failed_upload(lifecycle):
    await refresh(lifecycle)
    async with lifecycle.owner.dispatch(lifecycle.data.next, lifecycle.pm) as lease:
        lease.activate(1200)
        assert lease.purpose == "dispatch"
        assert lease.command(lifecycle.client, "bed", 90)
        lifecycle.client.set_bed_temperature.assert_called_once_with(90)
        # Returning without publish represents a failed source/upload stage.
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_real_preheat_adoption_retains_used_asa_target_with_unused_pa_mapping(lifecycle, caplog):
    lifecycle.data.previous.ams_mapping = lifecycle.data.next.ams_mapping = "[0, 1]"
    await refresh(lifecycle)
    caplog.set_level("INFO", logger="backend.app.services.preheat_stage")
    with (
        patch("backend.app.services.print_scheduler.preheat_ownership", lifecycle.owner),
        patch("backend.app.services.preheat_stage.preheat_ownership", lifecycle.owner),
        patch("backend.app.services.print_scheduler.printer_manager", lifecycle.pm),
        patch("backend.app.services.print_scheduler.get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 1))),
        patch.object(lifecycle.scheduler, "_get_int_setting", AsyncMock(return_value=0)),
    ):
        async with lifecycle.owner.dispatch(lifecycle.data.next, lifecycle.pm) as lease:
            await lifecycle.scheduler._preheat_and_soak(
                lifecycle.db, lifecycle.data.next, lifecycle.data.printer, lifecycle.data.next.archive
            )
            assert lease.purpose == "dispatch"
            lifecycle.client.set_bed_temperature.assert_called_once_with(90)
            assert any("chamber_target=45" in record.message for record in caplog.records)
            lifecycle.client.set_chamber_temperature.assert_not_called()
    lifecycle.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
async def test_adopted_publish_retains_owner_until_firmware_confirms_print(lifecycle):
    await refresh(lifecycle)
    async with lifecycle.owner.dispatch(lifecycle.data.next, lifecycle.pm) as lease:
        lease.activate(1200)
        lease.dispatched()
    assert lifecycle.owner.blocks_power_off(7)
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)
    lifecycle.data.state.state = "RUNNING"
    await asyncio.wait_for(lease.monitor, 1)
    assert not lifecycle.owner.blocks_power_off(7)
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)


@pytest.mark.asyncio
async def test_failed_handoff_persistence_preserves_original_deadline_and_rolls_back(lifecycle):
    await refresh(lifecycle)
    lease = lifecycle.owner.leases[7]
    deadline = lease.expires_at
    async with lifecycle.owner.dispatch(lifecycle.data.next, lifecycle.pm):
        with (
            patch.object(lifecycle.owner, "save", side_effect=OSError("storage failed")),
            pytest.raises(OSError),
        ):
            lease.activate(1200)
        assert lease.expires_at == deadline
        assert lifecycle.owner.leases[7] is lease
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_real_print_starts_during_hold_hands_off_without_off(lifecycle):
    await refresh(lifecycle)
    lifecycle.data.state.state = "PREPARE"
    await asyncio.wait_for(lifecycle.owner.leases[7].monitor, 1)
    lifecycle.client.set_bed_temperature.assert_called_once_with(90)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_service_command_error_rolls_back_intent(lifecycle):
    lifecycle.client.set_bed_temperature.side_effect = [RuntimeError("MQTT publish failed"), True]
    await refresh(lifecycle)
    lifecycle.client.set_bed_temperature.assert_called_with(0)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [80, 90])
async def test_manual_target_during_intent_persistence_is_never_overwritten(lifecycle, target):
    original = lifecycle.owner.save

    def manual_during_save(lease):
        original(lease)
        lifecycle.client.set_bed_temperature(target)

    with patch.object(lifecycle.owner, "save", side_effect=manual_during_save):
        await refresh(lifecycle)
    lifecycle.client.set_bed_temperature.assert_called_once_with(target)
    assert not lifecycle.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_smart_plug_off_is_blocked_during_compatible_hold(lifecycle):
    from backend.app.services.smart_plug_manager import SmartPlugManager

    await refresh(lifecycle)
    plug_manager = SmartPlugManager()
    service = MagicMock(turn_off=AsyncMock(return_value=True))
    plug_manager.get_service_for_plug = AsyncMock(return_value=service)
    plug_manager._mark_auto_off_pending = AsyncMock()
    lifecycle.pm.is_print_active.return_value = False
    with (
        patch("backend.app.services.smart_plug_manager.preheat_ownership", lifecycle.owner),
        patch("backend.app.services.smart_plug_manager.printer_manager", lifecycle.pm),
    ):
        await plug_manager._delayed_off(1, "tasmota", "127.0.0.1", None, None, None, 7, 0)
    service.turn_off.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_latest", [False, True])
@pytest.mark.parametrize("source_kind", ["archive", "library"])
async def test_real_database_loads_prior_variants_and_rejects_unknown_failed_latest(
    lifecycle, db_session, failed_latest, source_kind
):
    printer = Printer(
        id=7, name="Keep warm", serial_number="warm-7", model="X1C", ip_address="127.0.0.1", access_code="test-code"
    )
    db_session.add(printer)
    for identity, source in enumerate((lifecycle.data.previous, lifecycle.data.next), start=1):
        archive = PrintArchive(
            printer_id=7,
            filename=source.archive.filename,
            file_path=source.archive.file_path,
            file_size=(lifecycle.data.path / source.archive.file_path).stat().st_size,
            bed_type=source.archive.bed_type,
            sliced_for_model="X1C",
            status="completed",
            subtask_id="finished-task",
        )
        library = None
        if identity == 2 and source_kind == "library":
            library = LibraryFile(
                filename=source.archive.filename,
                file_path=source.archive.file_path,
                file_type="3mf",
                file_size=(lifecycle.data.path / source.archive.file_path).stat().st_size,
                file_metadata={"sliced_for_model": "X1C"},
            )
        item = PrintQueueItem(
            id=identity,
            printer_id=7,
            archive=archive if library is None else None,
            library_file=library,
            status=source.status,
            plate_id=1,
            ams_mapping="[0]",
            completed_at=source.completed_at if identity == 1 else None,
        )
        db_session.add(item)
    if failed_latest:
        db_session.add(PrintQueueItem(id=3, printer_id=7, status="failed", completed_at=None))
    await db_session.commit()
    db_session.expunge_all()
    items, _ = await lifecycle.scheduler._pending_queue_items(db_session)
    following = items[0]
    await lifecycle.keeper.refresh(lifecycle.scheduler, db_session, [following], [], {}, True, lifecycle.pm)
    if failed_latest:
        lifecycle.client.set_bed_temperature.assert_not_called()
    else:
        lifecycle.client.set_bed_temperature.assert_called_once_with(90)
