"""Unexpected firmware prints must interrupt unpublished queue dispatches."""

import asyncio
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.preheat_ownership import PreheatOwnership
from backend.app.services.print_scheduler import PrintScheduler


def single_plate_3mf(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"curr_bed_type": "Textured PEI Plate", "textured_plate_temp_initial_layer": [60]}),
        )
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/>'
            '<metadata key="curr_bed_type" value="Textured PEI Plate"/>'
            '<filament id="1" used_g="20" type="ASA"/></plate></config>',
        )


@pytest.fixture
async def external_print(tmp_path, test_engine, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}", poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    path = tmp_path / "queue.3mf"
    single_plate_3mf(path)
    async with factory() as db:
        printer = Printer(
            name="Queue race", serial_number="TEST-RACE", model="X1C", ip_address="192.0.2.1", access_code="test-only"
        )
        db.add(printer)
        await db.flush()
        archive = PrintArchive(
            printer_id=printer.id,
            filename="queue.3mf",
            file_path="queue.3mf",
            file_size=path.stat().st_size,
            bed_temperature=60,
            status="completed",
        )
        db.add(archive)
        await db.flush()
        item = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status="pending", preheat_override="on")
        db.add(item)
        await db.commit()
        printer_id, item_id = printer.id, item.id

    owner = PreheatOwnership(tmp_path / "owners", factory)
    owner.poll_seconds = 0.001
    client = BambuMQTTClient("192.0.2.1", "TEST-RACE", "test-only", model="X1C")
    client.state.connected = True
    client.state.state = "IDLE"
    client.state.temperatures = {"bed": 60, "bed_target": 0, "chamber": 20}
    published = []

    def publish(topic, payload, qos):
        published.append(json.loads(payload))

    client._client = SimpleNamespace(publish=publish)
    awaiting = {"value": False}
    manager = SimpleNamespace(
        get_status=lambda _: client.state,
        get_client=lambda _: client,
        is_connected=lambda _: True,
        is_awaiting_plate_clear=lambda _: awaiting["value"],
        set_awaiting_plate_clear=lambda pid, value: awaiting.update(value=value),
        start_print=lambda pid, filename, **kwargs: client.start_print(filename, **kwargs),
    )
    scheduler = PrintScheduler()
    integers = {"preheat_max_wait_seconds": 0, "preheat_soak_seconds": 0}
    scheduler._get_int_setting = AsyncMock(side_effect=lambda db, key, default: integers.get(key, default))
    scheduler._get_preheat_filament_targets = AsyncMock(return_value={})
    scheduler._propagate_owner_to_printer_manager = AsyncMock()
    scheduler._upload_print_file = AsyncMock(return_value=("queue.3mf", "/queue.3mf", 1, None))

    def discard(coroutine, **kwargs):
        coroutine.close()

    monkeypatch.setattr("backend.app.core.config.settings.base_dir", tmp_path)
    monkeypatch.setattr("backend.app.services.print_scheduler.printer_manager", manager)
    monkeypatch.setattr("backend.app.services.print_scheduler.preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.preheat_stage.preheat_ownership", owner)
    monkeypatch.setattr("backend.app.services.print_scheduler.async_session", factory)
    monkeypatch.setattr(
        "backend.app.services.print_scheduler.get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 1))
    )
    monkeypatch.setattr("backend.app.services.print_scheduler.spawn_background_task", discard)
    monkeypatch.setattr("backend.app.services.print_scheduler.cache_3mf_download", lambda *args: None)
    monkeypatch.setattr("backend.app.main.register_expected_print", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.app.services.print_scheduler.notification_service.on_queue_job_started", AsyncMock())
    monkeypatch.setattr("backend.app.services.mqtt_relay.mqtt_relay.on_queue_job_started", AsyncMock())
    context = SimpleNamespace(
        owner=owner,
        client=client,
        awaiting=awaiting,
        scheduler=scheduler,
        integers=integers,
        factory=factory,
        printer_id=printer_id,
        item_id=item_id,
        published=published,
        task=None,
    )
    yield context
    if context.task and not context.task.done():
        context.task.cancel()
        await asyncio.gather(context.task, return_exceptions=True)
    monitors = [lease.monitor for lease in owner.leases.values() if lease.monitor]
    owner.stop()
    await asyncio.gather(*monitors, return_exceptions=True)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("active_state", ["PREPARE", "SLICING", "RUNNING", "PAUSE"])
@pytest.mark.parametrize("phase", ["soak", "upload", "committed"])
async def test_short_manual_print_defers_claim_without_clearing_its_plate(
    external_print, monkeypatch, active_state, phase
):
    context = external_print
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause(_seconds):
        entered.set()
        await release.wait()

    async def upload(*args):
        entered.set()
        await release.wait()
        return "queue.3mf", "/queue.3mf", 1, None

    if phase == "soak":
        context.integers["preheat_soak_seconds"] = 600
        monkeypatch.setattr("backend.app.services.preheat_stage.asyncio.sleep", pause)
    elif phase == "upload":
        context.scheduler._upload_print_file = upload

    async def dispatch():
        async with context.factory() as db:
            if phase == "committed":
                original = db.commit

                async def commit():
                    await original()
                    async with context.factory() as verification:
                        status = await verification.scalar(
                            select(PrintQueueItem.status).where(PrintQueueItem.id == context.item_id)
                        )
                    if status == "printing":
                        entered.set()
                        await release.wait()

                monkeypatch.setattr(db, "commit", commit)
            item = await db.get(PrintQueueItem, context.item_id)
            await context.scheduler._dispatch_with_claim(db, item)

    context.task = asyncio.create_task(dispatch())
    await asyncio.wait_for(entered.wait(), 2)
    lease = context.owner.leases[context.printer_id]
    context.client.state.state = active_state
    context.client.state.subtask_id = "manual-print"
    await asyncio.wait_for(lease.monitor, 2)
    context.client.state.state = "FINISH"
    context.awaiting["value"] = True
    release.set()
    await asyncio.wait_for(context.task, 2)

    assert context.awaiting["value"]
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line"]
    assert context.published[0]["print"]["param"] == "M140 S60"
    assert context.client.state.temperatures["bed_target"] == 60
    assert not context.owner.blocks_power_off(context.printer_id)
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        assert (item.status, item.started_at, item.dispatching_at) == ("pending", None, None)


@pytest.mark.asyncio
async def test_published_queue_start_hands_off_without_interrupting(external_print):
    context = external_print
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        await context.scheduler._dispatch_with_claim(db, item)
    lease = context.owner.leases[context.printer_id]
    context.client.state.state = "PREPARE"
    await asyncio.wait_for(lease.monitor, 2)
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line", "project_file"]
    assert not context.owner.blocks_power_off(context.printer_id)
    assert context.client.state.temperatures["bed_target"] == 60
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        assert item.status == "printing"
        assert item.started_at is not None
        assert item.dispatching_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["cancelled", "deleted"])
async def test_external_interruption_never_revives_a_cancelled_or_deleted_row(external_print, monkeypatch, mutation):
    context = external_print
    uploading, release_upload, interrupted, release_defer = (asyncio.Event() for _ in range(4))
    original = context.owner.defer_interrupted

    async def defer(lease, db=None):
        interrupted.set()
        await release_defer.wait()
        await original(lease, db)

    async def upload(*args):
        uploading.set()
        await release_upload.wait()
        return "queue.3mf", "/queue.3mf", 1, None

    monkeypatch.setattr(context.owner, "defer_interrupted", defer)
    context.scheduler._upload_print_file = upload

    async def dispatch():
        async with context.factory() as db:
            item = await db.get(PrintQueueItem, context.item_id)
            await context.scheduler._dispatch_with_claim(db, item)

    context.task = asyncio.create_task(dispatch())
    await asyncio.wait_for(uploading.wait(), 2)
    context.client.state.state = "RUNNING"
    await asyncio.wait_for(interrupted.wait(), 2)
    async with context.factory() as db:
        statement = (
            delete(PrintQueueItem) if mutation == "deleted" else update(PrintQueueItem).values(status="cancelled")
        )
        await db.execute(statement.where(PrintQueueItem.id == context.item_id))
        await db.commit()
    release_defer.set()
    await asyncio.wait_for(context.task, 2)
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line"]
    assert context.client.state.temperatures["bed_target"] == 60
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        if mutation == "deleted":
            assert item is None
        else:
            assert item.status == "cancelled"
            assert item.dispatching_at is None
