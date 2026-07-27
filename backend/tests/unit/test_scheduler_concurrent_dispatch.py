"""Concurrent queue dispatch as a refillable upload pool (#2555, #2602)."""

import asyncio
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.app.models  # noqa: F401 - populate Base.metadata
import backend.app.services.archive as archive_module
import backend.app.services.print_scheduler as scheduler_module
from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.services.print_scheduler import PrintScheduler

UPLOAD_SECONDS = 0.05


@pytest.fixture
async def farm(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def make_farm(printer_count: int, *, max_concurrent: int | None = None):
        base_dir = tmp_path / "farm"
        (base_dir / "archives").mkdir(parents=True, exist_ok=True)

        async with session_maker() as db:
            if max_concurrent is not None:
                db.add(Settings(key="queue_max_concurrent_uploads", value=str(max_concurrent)))

            printer_ids = []
            for n in range(printer_count):
                archive_rel = Path("archives") / f"job-{n}.3mf"
                (base_dir / archive_rel).write_bytes(b"archive payload")

                printer = Printer(
                    name=f"Printer {n}",
                    serial_number=f"SERIAL-{n}",
                    ip_address=f"10.0.0.{n + 1}",
                    access_code="access-code",
                    model="A1",
                )
                db.add(printer)
                await db.flush()

                archive = PrintArchive(
                    printer_id=printer.id,
                    filename=f"job-{n}.3mf",
                    file_path=str(archive_rel),
                    file_size=15,
                    print_time_seconds=120,
                    status="completed",
                )
                db.add(archive)
                await db.flush()

                db.add(
                    PrintQueueItem(
                        printer_id=printer.id,
                        archive_id=archive.id,
                        status="pending",
                        position=n,
                    )
                )
                printer_ids.append(printer.id)
            await db.commit()

        return SimpleNamespace(session_maker=session_maker, base_dir=base_dir, printer_ids=printer_ids)

    try:
        yield make_farm
    finally:
        await engine.dispose()


class _UploadRecorder:
    def __init__(self, *, fail_for_ip: str | None = None):
        self.in_flight = 0
        self.peak = 0
        self.order: list[str] = []
        self.fail_for_ip = fail_for_ip

    async def __call__(self, ip_address, access_code, local_path, remote_path, **kwargs):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        self.order.append(ip_address)
        try:
            await asyncio.sleep(UPLOAD_SECONDS)
            if self.fail_for_ip is not None and ip_address == self.fail_for_ip:
                raise OSError(f"simulated FTP failure for {ip_address}")
            return True
        finally:
            self.in_flight -= 1


@asynccontextmanager
async def _scheduler_ctx(ctx, upload, job_started=None):
    scheduler = PrintScheduler()
    job_started = job_started or AsyncMock()

    def _real_spawn(coro, *, name=None):
        return asyncio.create_task(coro, name=name)

    patches = [
        patch.object(scheduler_module.settings, "base_dir", ctx.base_dir),
        patch.object(archive_module.settings, "base_dir", ctx.base_dir),
        patch.object(archive_module.settings, "archive_dir", ctx.base_dir / "archive"),
        patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
        patch("backend.app.core.database.async_session", ctx.session_maker),
        patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(return_value=True)),
        patch("backend.app.services.print_scheduler.printer_manager.get_status", MagicMock(return_value=None)),
        patch("backend.app.services.print_scheduler.printer_manager.start_print", MagicMock(return_value=True)),
        patch("backend.app.services.print_scheduler.printer_manager.set_awaiting_plate_clear", MagicMock()),
        patch("backend.app.services.print_scheduler.upload_file_async", upload),
        patch("backend.app.services.print_scheduler.delete_file_async", AsyncMock(return_value=True)),
        patch(
            "backend.app.services.print_scheduler.get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 1.0))
        ),
        patch("backend.app.services.print_scheduler.cache_3mf_download", MagicMock()),
        patch("backend.app.services.print_scheduler.spawn_background_task", _real_spawn),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_started", job_started),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_failed", AsyncMock()),
        patch("backend.app.services.mqtt_relay.mqtt_relay.on_queue_job_started", AsyncMock()),
        patch.object(scheduler, "_is_printer_idle", MagicMock(return_value=True)),
        patch.object(scheduler, "_propagate_owner_to_printer_manager", AsyncMock()),
        patch.object(scheduler, "_power_off_if_needed", AsyncMock()),
        patch.object(scheduler, "_preheat_and_soak", AsyncMock()),
        patch.object(scheduler, "_check_auto_drying", AsyncMock()),
        patch.object(scheduler, "_watchdog_print_start", AsyncMock()),
    ]

    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        yield scheduler


async def _drain(scheduler: PrintScheduler):
    tasks = [task for (task, _pid) in scheduler._inflight.values()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)


async def _statuses(ctx):
    async with ctx.session_maker() as db:
        rows = (await db.execute(select(PrintQueueItem).order_by(PrintQueueItem.position))).scalars().all()
        return [row.status for row in rows]


async def _pending_count(ctx) -> int:
    async with ctx.session_maker() as db:
        return await db.scalar(
            select(func.count()).select_from(PrintQueueItem).where(PrintQueueItem.status == "pending")
        )


async def _run_to_completion(ctx, upload, *, max_ticks: int = 20):
    ticks = 0
    async with _scheduler_ctx(ctx, upload) as scheduler:
        while ticks < max_ticks:
            await scheduler.check_queue()
            await _drain(scheduler)
            ticks += 1
            if await _pending_count(ctx) == 0 and not scheduler._inflight:
                break
    return ticks


@pytest.mark.asyncio
async def test_uploads_to_different_printers_overlap(farm):
    ctx = await farm(4, max_concurrent=4)
    upload = _UploadRecorder()

    await _run_to_completion(ctx, upload)

    assert upload.peak == 4
    assert await _statuses(ctx) == ["printing"] * 4


@pytest.mark.asyncio
async def test_pool_cap_holds_across_refills(farm):
    ctx = await farm(7, max_concurrent=3)
    upload = _UploadRecorder()

    ticks = await _run_to_completion(ctx, upload)

    assert upload.peak == 3
    assert len(upload.order) == 7
    assert ticks >= 3
    assert await _statuses(ctx) == ["printing"] * 7


@pytest.mark.asyncio
async def test_freed_slot_refills_on_next_tick(farm):
    ctx = await farm(2, max_concurrent=1)
    upload = _UploadRecorder()

    async with _scheduler_ctx(ctx, upload) as scheduler:
        assert await scheduler.check_queue() is True
        assert len(scheduler._inflight) == 1

        assert await scheduler.check_queue() is True
        assert len(scheduler._inflight) == 1

        await _drain(scheduler)
        assert not scheduler._inflight

        assert await scheduler.check_queue() is True
        assert len(scheduler._inflight) == 1
        await _drain(scheduler)

    assert upload.peak == 1
    assert await _statuses(ctx) == ["printing", "printing"]


@pytest.mark.asyncio
async def test_inflight_item_is_not_reselected(farm):
    ctx = await farm(1, max_concurrent=4)
    upload = _UploadRecorder()

    async with _scheduler_ctx(ctx, upload) as scheduler:
        assert await scheduler.check_queue() is True
        inflight_before = set(scheduler._inflight)

        assert await scheduler.check_queue() is True
        assert set(scheduler._inflight) == inflight_before

        await _drain(scheduler)

    assert upload.order == ["10.0.0.1"]
    assert await _statuses(ctx) == ["printing"]


@pytest.mark.asyncio
async def test_empty_queue_reports_no_dispatch(farm):
    ctx = await farm(0, max_concurrent=3)

    async with _scheduler_ctx(ctx, _UploadRecorder()) as scheduler:
        assert await scheduler.check_queue() is False


@pytest.mark.asyncio
async def test_one_failing_upload_does_not_cancel_siblings(farm):
    ctx = await farm(4, max_concurrent=4)
    upload = _UploadRecorder(fail_for_ip="10.0.0.2")

    await _run_to_completion(ctx, upload)

    statuses = await _statuses(ctx)
    assert statuses[1] == "failed"
    assert [status for idx, status in enumerate(statuses) if idx != 1] == ["printing"] * 3
