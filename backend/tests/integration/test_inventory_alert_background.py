"""Blocked external alert transports must not hold up queue selection."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.services.notification_service import notification_service
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.spoolman import SpoolmanClient
from backend.tests.integration.test_stock_alert_producer import seed_stock


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_stage", ["forecast", "provider"])
async def test_blocked_alert_transport_leaves_dispatch_fast_and_shutdown_drains_task(
    tmp_path, test_engine, monkeypatch, blocked_stage
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/alerts.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    entered = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()
    reads = []

    async def blocked_http(request):
        reads.append(request.url.path)
        entered.set()
        try:
            await release.wait()
        finally:
            cancelled.set()
        return httpx.Response(200, json=[])

    client = httpx.AsyncClient(transport=httpx.MockTransport(blocked_http))
    monkeypatch.setattr("backend.app.services.print_scheduler.async_session", sessions)
    monkeypatch.setattr(notification_service, "_template_cache", {})
    if blocked_stage == "provider":
        monkeypatch.setattr(notification_service, "_http_client", client)
    else:
        spoolman = SpoolmanClient("http://inventory.invalid")
        spoolman._client = client

        async def get_client():
            return spoolman

        monkeypatch.setattr("backend.app.services.stock_alert_monitor.get_spoolman_client", get_client)
    scheduler = PrintScheduler()
    first_pass = None
    dispatched = []
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await seed_stock(db)
            if blocked_stage == "forecast":
                db.add(Settings(key="spoolman_enabled", value="true"))
            printer = Printer(name="Ready", serial_number="READY", ip_address="192.0.2.1", access_code="test")
            db.add(printer)
            await db.commit()
        # First empty pass starts the alert transport; queue selection itself
        # must finish while that real HTTP request is still waiting.
        first_pass = asyncio.create_task(scheduler.check_queue())
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert await asyncio.wait_for(asyncio.shield(first_pass), timeout=0.3) is False
        alert_task = scheduler._inventory_alert_task
        assert not alert_task.done()
        async with sessions() as db:
            item = PrintQueueItem(printer_id=printer.id, status="pending", position=1)
            db.add(item)
            await db.commit()

        # Replace only hardware boundaries: printer telemetry and upload
        # submission. Real DB queue ordering/eligibility and keep-warm run.
        monkeypatch.setattr("backend.app.services.print_scheduler.printer_manager.is_connected", lambda _id: True)
        monkeypatch.setattr(
            "backend.app.services.print_scheduler.printer_manager.get_status",
            lambda _id: SimpleNamespace(state="IDLE", raw_data={}, ams_mapping=None),
        )
        monkeypatch.setattr(
            "backend.app.services.print_scheduler.printer_manager.is_awaiting_plate_clear", lambda _id: False
        )
        monkeypatch.setattr(scheduler, "_launch_uploads", lambda ids, printers, limit: dispatched.extend(ids))
        assert await asyncio.wait_for(scheduler.check_queue(), timeout=0.3) is True
        assert dispatched == [item.id]
        assert scheduler._inventory_alert_task is alert_task
        assert len(reads) == 1
        scheduler.stop()
        await scheduler.close_inventory_alerts()
        assert cancelled.is_set()
        assert alert_task.done() and alert_task.cancelled()
        assert not any(task.get_name() == "inventory-alerts" for task in asyncio.all_tasks())
    finally:
        await scheduler.close_inventory_alerts()
        release.set()
        if first_pass is not None and not first_pass.done():
            first_pass.cancel()
            await asyncio.gather(first_pass, return_exceptions=True)
        await client.aclose()
        await engine.dispose()
