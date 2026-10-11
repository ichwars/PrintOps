"""Preheat must relinquish only its own heaters when dispatch cannot proceed."""

import asyncio
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.heater_commands import set_heater_temperature
from backend.app.services.preheat_ownership import PreheatLease, PreheatOwnership
from backend.app.services.print_scheduler import PrintScheduler

_owners = []


@pytest.fixture
async def queue_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    case_counter = 0

    async def make_case(*, status="pending"):
        nonlocal case_counter
        case_counter += 1

        base_dir = tmp_path / f"case-{case_counter}"
        base_dir.mkdir()
        archive_rel = Path("archives") / f"job-{case_counter}.3mf"
        archive_abs = base_dir / archive_rel
        archive_abs.parent.mkdir(parents=True, exist_ok=True)
        archive_abs.write_bytes(b"archive payload")

        async with session_maker() as db:
            printer = Printer(
                name=f"Printer {case_counter}",
                serial_number=f"SERIAL-{case_counter}",
                ip_address="127.0.0.1",
                access_code="access-code",
                model="X1C",
            )
            db.add(printer)
            await db.flush()

            archive = PrintArchive(
                printer_id=printer.id,
                filename=f"job-{case_counter}.3mf",
                file_path=str(archive_rel),
                file_size=archive_abs.stat().st_size,
                content_hash=None,
                thumbnail_path=None,
                timelapse_path=None,
                print_time_seconds=120,
                status="completed",
            )
            db.add(archive)
            await db.flush()

            item = PrintQueueItem(
                printer_id=printer.id,
                archive_id=archive.id,
                status=status,
                bed_levelling=True,
                flow_cali=False,
                vibration_cali=True,
                layer_inspect=False,
                timelapse=False,
                use_ams=True,
                nozzle_offset_cali=True,
            )
            db.add(item)
            await db.commit()

            return SimpleNamespace(
                session_maker=session_maker,
                base_dir=base_dir,
                archive_path=archive_abs,
                printer_id=printer.id,
                archive_id=archive.id,
                queue_item_id=item.id,
                upload=AsyncMock(return_value=True),
                start_print=MagicMock(return_value=True),
                delete_file=AsyncMock(return_value=True),
            )

    try:
        yield make_case
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def cleanup_owners():
    yield
    for owner in _owners:
        monitors = [lease.monitor for lease in owner.leases.values() if lease.monitor]
        owner.stop()
        await asyncio.gather(*monitors, return_exceptions=True)
    _owners.clear()


async def dispatch(
    ctx,
    *,
    upload_result=False,
    upload_effect=None,
    start_result=True,
    preheat="on",
    soak=0,
    poll_seconds=3,
    persistence_failure=False,
    keep_warm=False,
):
    scheduler = PrintScheduler()
    state = SimpleNamespace(
        state="IDLE", connected=True, temperatures={"bed": 60, "bed_target": 0, "chamber": 20}, raw_data={}
    )
    client = MagicMock(state=state)
    client._heater_command_revisions = {}
    client.send_gcode.return_value = True
    ctx.heated = asyncio.Event()

    def bed_command(target):
        if target > 0:
            ctx.heated.set()
        return set_heater_temperature(client, "bed", target)

    client.set_bed_temperature.side_effect = bed_command
    client.set_chamber_temperature.side_effect = lambda target: set_heater_temperature(client, "chamber", target)
    pm = MagicMock()
    pm.is_connected.return_value = True
    pm.get_status.return_value = state
    pm.get_client.return_value = client
    pm.start_print.return_value = start_result
    owner = PreheatOwnership(ctx.base_dir / "owners", ctx.session_maker)
    owner.poll_seconds = poll_seconds
    if persistence_failure:
        owner.save = MagicMock(side_effect=OSError("ownership disk unavailable"))
    _owners.append(owner)
    ctx.owner, ctx.state, ctx.client, ctx.pm = owner, state, client, pm
    if keep_warm:
        state.state = "FINISH"
        lease = PreheatLease(owner, ctx.printer_id, ctx.queue_item_id, pm, purpose="keep_warm")
        lease.activate(600)
        assert lease.command(client, "bed", 60)
    upload = AsyncMock(return_value=upload_result, side_effect=upload_effect)
    patches = [
        patch("backend.app.services.print_scheduler.preheat_ownership", owner),
        patch("backend.app.services.preheat_stage.preheat_ownership", owner),
        patch("backend.app.services.print_scheduler.settings.base_dir", ctx.base_dir),
        patch("backend.app.services.print_scheduler.printer_manager", pm),
        patch("backend.app.services.print_scheduler.get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 1))),
        patch("backend.app.services.print_scheduler.upload_file_async", upload),
        patch("backend.app.services.print_scheduler.delete_file_async", AsyncMock(return_value=True)),
        patch("backend.app.services.print_scheduler.cache_3mf_download", MagicMock()),
        patch("backend.app.services.print_scheduler.spawn_background_task", MagicMock()),
        patch(
            "backend.app.services.print_scheduler.notification_service",
            MagicMock(on_queue_job_failed=AsyncMock(), on_queue_job_started=AsyncMock()),
        ),
        patch("backend.app.services.mqtt_relay.mqtt_relay.on_queue_job_started", AsyncMock()),
        patch.object(scheduler, "_propagate_owner_to_printer_manager", AsyncMock()),
        patch.object(scheduler, "_power_off_if_needed", AsyncMock()),
        patch.object(
            scheduler,
            "_get_int_setting",
            AsyncMock(side_effect=lambda db, key, default: soak if key == "preheat_soak_seconds" else 0),
        ),
    ]
    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        async with ctx.session_maker() as db:
            archive = await db.get(PrintArchive, ctx.archive_id)
            archive.bed_temperature = 60
            item = await db.get(PrintQueueItem, ctx.queue_item_id)
            item.preheat_override = preheat
            await db.commit()
            await scheduler._start_print(db, item)
    return scheduler, client, pm, upload


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_warm", [False, True])
async def test_failed_upload_rolls_back_bed_even_without_auto_off(queue_factory, keep_warm):
    ctx = await queue_factory()
    _, client, pm, _ = await dispatch(ctx, keep_warm=keep_warm)
    assert [call.args for call in client.set_bed_temperature.call_args_list] == [(60,), (0,)]
    pm.start_print.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [RuntimeError("FTP failed"), asyncio.CancelledError()])
async def test_upload_exception_or_task_cancel_rolls_back_owned_heat(queue_factory, exception):
    ctx = await queue_factory()
    if isinstance(exception, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await dispatch(ctx, upload_effect=exception)
    else:
        await dispatch(ctx, upload_effect=exception)
    ctx.client.set_bed_temperature.assert_called_with(0)
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("upload_result", [True, False])
@pytest.mark.parametrize("keep_warm", [False, True])
async def test_cancel_during_upload_preserves_cancellation_and_rolls_back(queue_factory, upload_result, keep_warm):
    ctx = await queue_factory()

    async def cancel(*args, **kwargs):
        async with ctx.session_maker() as db:
            item = await db.get(PrintQueueItem, ctx.queue_item_id)
            item.status = "cancelled"
            await db.commit()
        return upload_result

    # Exercise the post-upload CAS independently from watchdog task cancellation.
    await dispatch(ctx, upload_effect=cancel, keep_warm=keep_warm, poll_seconds=60)
    async with ctx.session_maker() as db:
        assert (await db.get(PrintQueueItem, ctx.queue_item_id)).status == "cancelled"
    ctx.pm.start_print.assert_not_called()
    ctx.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
async def test_cancel_during_soak_stops_before_any_upload(queue_factory):
    ctx = await queue_factory()
    task = asyncio.create_task(dispatch(ctx, soak=300, poll_seconds=0.001))
    while not hasattr(ctx, "heated"):
        await asyncio.sleep(0)
    await asyncio.wait_for(ctx.heated.wait(), 1)
    async with ctx.session_maker() as db:
        item = await db.get(PrintQueueItem, ctx.queue_item_id)
        item.status = "cancelled"
        await db.commit()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    ctx.pm.start_print.assert_not_called()
    ctx.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_warm", [False, True])
async def test_watchdog_cancel_during_blocked_upload_stops_owned_heat(queue_factory, keep_warm):
    ctx = await queue_factory()
    uploading = asyncio.Event()
    never_finish = asyncio.Event()

    async def blocked_upload(*args, **kwargs):
        uploading.set()
        await never_finish.wait()
        return True

    task = asyncio.create_task(dispatch(ctx, upload_effect=blocked_upload, poll_seconds=0.001, keep_warm=keep_warm))
    await asyncio.wait_for(uploading.wait(), 1)
    async with ctx.session_maker() as db:
        item = await db.get(PrintQueueItem, ctx.queue_item_id)
        item.status = "cancelled"
        await db.commit()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    async with ctx.session_maker() as db:
        assert (await db.get(PrintQueueItem, ctx.queue_item_id)).status == "cancelled"
    ctx.pm.start_print.assert_not_called()
    ctx.client.set_bed_temperature.assert_called_with(0)
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_dispatch_deadline_cancels_soak_and_fails_pending_item(queue_factory):
    ctx = await queue_factory()
    task = asyncio.create_task(dispatch(ctx, soak=300, poll_seconds=0.001))
    while not hasattr(ctx, "heated"):
        await asyncio.sleep(0)
    await asyncio.wait_for(ctx.heated.wait(), 1)
    ctx.owner.leases[ctx.printer_id].expires_at = 0
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    async with ctx.session_maker() as db:
        item = await db.get(PrintQueueItem, ctx.queue_item_id)
        assert item.status == "failed"
        assert "deadline" in item.error_message
    ctx.pm.start_print.assert_not_called()
    ctx.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_warm", [False, True])
async def test_successful_upload_only_transfers_on_confirmed_print_start(queue_factory, keep_warm):
    ctx = await queue_factory()
    await dispatch(ctx, upload_result=True, poll_seconds=0.001, keep_warm=keep_warm)
    ctx.pm.start_print.assert_called_once()
    assert ctx.owner.blocks_power_off(ctx.printer_id)
    ctx.client.set_bed_temperature.assert_called_once_with(60)
    ctx.state.state = "PREPARE"
    await asyncio.wait_for(ctx.owner.leases[ctx.printer_id].monitor, 1)
    assert not ctx.owner.blocks_power_off(ctx.printer_id)
    ctx.client.set_bed_temperature.assert_called_once_with(60)


@pytest.mark.asyncio
async def test_print_command_failure_rolls_back(queue_factory):
    ctx = await queue_factory()
    await dispatch(ctx, upload_result=True, start_result=False)
    ctx.client.set_bed_temperature.assert_called_with(0)
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_skipped_preheat_releases_adopted_hold_before_upload(queue_factory):
    ctx = await queue_factory()

    async def upload_after_release(*args, **kwargs):
        assert ctx.state.temperatures["bed_target"] == 0
        assert not ctx.owner.blocks_power_off(ctx.printer_id)
        return True

    await dispatch(ctx, upload_effect=upload_after_release, preheat="off", keep_warm=True)
    ctx.pm.start_print.assert_called_once()
    assert [call.args for call in ctx.client.set_bed_temperature.call_args_list] == [(60,), (0,)]


@pytest.mark.asyncio
@pytest.mark.parametrize("preheat,status", [("off", "pending"), ("on", "cancelled")])
async def test_skipped_or_cancelled_dispatch_never_owns_heat(queue_factory, preheat, status):
    ctx = await queue_factory(status=status)
    await dispatch(ctx, upload_result=True, preheat=preheat)
    ctx.client.set_bed_temperature.assert_not_called()
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_manual_target_changed_during_upload_survives_failure(queue_factory):
    ctx = await queue_factory()

    async def change_target(*args, **kwargs):
        ctx.client.set_bed_temperature(80)
        return False

    await dispatch(ctx, upload_effect=change_target)
    assert [call.args for call in ctx.client.set_bed_temperature.call_args_list] == [(60,), (80,)]
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_real_print_started_during_upload_survives_failure(queue_factory):
    ctx = await queue_factory()

    async def print_started(*args, **kwargs):
        ctx.state.state = "RUNNING"
        return False

    await dispatch(ctx, upload_effect=print_started)
    ctx.client.set_bed_temperature.assert_called_once_with(60)
    ctx.pm.start_print.assert_not_called()
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_unavailable_journal_skips_heat_but_preserves_normal_dispatch(queue_factory):
    ctx = await queue_factory()
    await dispatch(ctx, upload_result=True, persistence_failure=True)
    ctx.client.set_bed_temperature.assert_not_called()
    ctx.pm.start_print.assert_called_once()
    assert not ctx.owner.blocks_power_off(ctx.printer_id)


@pytest.mark.asyncio
async def test_queue_removed_during_soak_stops_heat(queue_factory):
    ctx = await queue_factory()
    task = asyncio.create_task(dispatch(ctx, soak=300, poll_seconds=0.001))
    while not hasattr(ctx, "heated"):
        await asyncio.sleep(0)
    await asyncio.wait_for(ctx.heated.wait(), 1)
    async with ctx.session_maker() as db:
        await db.delete(await db.get(PrintQueueItem, ctx.queue_item_id))
        await db.commit()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    ctx.pm.start_print.assert_not_called()
    ctx.client.set_bed_temperature.assert_called_with(0)
