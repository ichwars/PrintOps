"""Physical inventory weights drive low-filament alerts through the scheduler."""

from datetime import datetime
from itertools import count

import httpx
import pytest
from sqlalchemy import select

from backend.app.models.notification import NotificationProvider
from backend.app.models.notification_template import NotificationTemplate
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.tests.integration.test_stock_alert_producer import (
    alert_scheduler as alert_scheduler,
    logs,
    model_engine as model_engine,
    run_alert_pass,
    test_engine as test_engine,
)


@pytest.fixture
async def low_scheduler(alert_scheduler, monkeypatch):
    clock = count(0, 31)
    monkeypatch.setattr("backend.app.services.filament_low_monitor.monotonic", lambda: next(clock))
    yield alert_scheduler


async def seed_low(db, printer, *, ams_id=255, tray_id=1):
    spool = Spool(material="PLA", color_name="Red", label_weight=250, weight_used=225, weight_used_baseline=225)
    db.add(spool)
    await db.flush()
    assignment = SpoolAssignment(spool_id=spool.id, printer_id=printer.id, ams_id=ams_id, tray_id=tray_id)
    provider = NotificationProvider(
        name="Low filament",
        provider_type="ntfy",
        on_filament_low=True,
        config='{"server":"http://notify.invalid","topic":"low"}',
    )
    db.add_all(
        [
            assignment,
            provider,
            NotificationTemplate(
                event_type="filament_low",
                name="Low",
                title_template="Low",
                body_template="{printer}|{slot}|{remaining_percent}|{color}",
            ),
        ]
    )
    await db.commit()
    return spool, assignment, provider


@pytest.mark.asyncio
@pytest.mark.parametrize("populated_queue", [False, True])
async def test_queue_pass_alerts_from_assigned_own_weight_even_after_counter_reset(
    db_session, printer_factory, low_scheduler, populated_queue
):
    printer = await printer_factory(name="Own printer")
    spool, assignment, _ = await seed_low(db_session, printer)
    if populated_queue:
        db_session.add(PrintQueueItem(status="pending", manual_start=True))
        await db_session.commit()
    scheduler, deliveries = low_scheduler
    await run_alert_pass(scheduler)
    assert [(log.event_type, log.message, log.success) for log in await logs(db_session)] == [
        ("filament_low", "Own printer|Ext-R|10|Red", True)
    ]
    assert deliveries == ["Own printer|Ext-R|10|Red"]
    await db_session.refresh(spool)
    await db_session.refresh(assignment)
    assert spool.weight_used == 225 and spool.weight_used_baseline == 225
    assert assignment.spool_id == spool.id


@pytest.mark.asyncio
async def test_low_alert_dedup_recovers_and_replacement_rearms(db_session, printer_factory, low_scheduler):
    printer = await printer_factory(name="Own")
    spool, assignment, _ = await seed_low(db_session, printer, ams_id=128, tray_id=0)
    scheduler, deliveries = low_scheduler
    await run_alert_pass(scheduler)
    await run_alert_pass(scheduler)
    assert deliveries == ["Own|HT-A|10|Red"]
    spool.weight_used = 100
    await db_session.commit()
    await run_alert_pass(scheduler)
    spool.weight_used = 225
    await db_session.commit()
    await run_alert_pass(scheduler)
    assert len(deliveries) == 2
    replacement = Spool(material="PETG", label_weight=500, weight_used=475, color_name="Blue")
    db_session.add(replacement)
    await db_session.flush()
    assignment.spool_id = replacement.id
    await db_session.commit()
    await run_alert_pass(scheduler)
    assert deliveries[-1] == "Own|HT-A|5|Blue"
    assert len(deliveries) == 3
    replacement.archived_at = datetime.utcnow()
    await db_session.commit()
    await run_alert_pass(scheduler)
    assert len(deliveries) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,used,global_threshold,override,expected",
    [
        (250, 225, "20", None, 1),
        (250, 200, "20", None, 0),
        (250, 190, "20", None, 0),
        (250, 200, "20", 25, 1),
        (250, 200, "30", 10, 0),
        (250, 225, "bad", None, 1),
        (250, 225, "nan", None, 1),
        (250, 225, "101", None, 1),
        (0, 0, "20", None, 0),
    ],
)
async def test_low_thresholds_use_physical_net_weight_and_valid_overrides(
    db_session, printer_factory, low_scheduler, label, used, global_threshold, override, expected
):
    printer = await printer_factory()
    spool, _, _ = await seed_low(db_session, printer, ams_id=0, tray_id=0)
    spool.label_weight = label
    spool.weight_used = used
    spool.low_stock_threshold_pct = override
    db_session.add(Settings(key="low_stock_threshold", value=global_threshold))
    await db_session.commit()
    scheduler, deliveries = low_scheduler
    await run_alert_pass(scheduler)
    assert len(deliveries) == expected


@pytest.mark.asyncio
async def test_printer_scope_and_disabled_subscription_do_not_silence_new_matching_subscriber(
    db_session, printer_factory, low_scheduler
):
    printer = await printer_factory(name="Target")
    other = await printer_factory(name="Other")
    _, _, provider = await seed_low(db_session, printer)
    provider.printer_id = other.id
    await db_session.commit()
    scheduler, deliveries = low_scheduler
    await run_alert_pass(scheduler)
    assert deliveries == []
    provider.printer_id = printer.id
    await db_session.commit()
    await run_alert_pass(scheduler)
    assert deliveries == ["Target|Ext-R|10|Red"]
    provider.enabled = False
    await db_session.commit()
    await run_alert_pass(scheduler)
    provider.enabled = True
    await db_session.commit()
    await run_alert_pass(scheduler)
    assert len(deliveries) == 1  # A disabled subscription does not prove recovery.


@pytest.mark.asyncio
async def test_spoolman_low_snapshot_is_throttled_native_weight_and_outage_dedup_preserved(
    db_session, printer_factory, low_scheduler, monkeypatch
):
    from backend.app.services.spoolman import SpoolmanClient

    printer = await printer_factory(name="External")
    _, _, provider = await seed_low(db_session, printer)
    db_session.add_all(
        [
            Settings(key="spoolman_enabled", value="true"),
            SpoolmanSlotAssignment(printer_id=printer.id, ams_id=255, tray_id=0, spoolman_spool_id=42),
        ]
    )
    await db_session.commit()
    raw = {
        "id": 42,
        "initial_weight": 250,
        "remaining_weight": 25,
        "used_weight": 225,
        "archived": False,
        "extra": {"bambu_weight_used_baseline": '"225"'},
        "filament": {"material": "PLA", "name": "PLA", "weight": 1000, "color_name": "Red", "vendor": {"name": "Own"}},
    }
    state = {"status": 200}
    reads = []

    def inventory_http(request):
        reads.append(request.url.path)
        return httpx.Response(state["status"], json=[raw])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(inventory_http))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.filament_low_monitor.get_spoolman_client", get_client)
    scheduler, deliveries = low_scheduler
    try:
        await run_alert_pass(scheduler)
        assert deliveries == ["External|Ext-L|10|Red"]
        assert reads == ["/api/v1/spool"]
        monkeypatch.setattr("backend.app.services.filament_low_monitor.monotonic", lambda: 1)
        await run_alert_pass(scheduler)
        assert len(reads) == 1
        clock = count(100, 31)
        monkeypatch.setattr("backend.app.services.filament_low_monitor.monotonic", lambda: next(clock))
        state["status"] = 503
        await run_alert_pass(scheduler)
        state["status"] = 200
        await run_alert_pass(scheduler)
        assert len(deliveries) == 1
        raw["remaining_weight"] = 250
        await run_alert_pass(scheduler)
        raw["remaining_weight"] = 25
        await run_alert_pass(scheduler)
        assert len(deliveries) == 2
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("assignment_exists,provider_enabled", [(False, True), (True, False)])
async def test_no_external_fetch_without_active_subscribed_assignments(
    db_session, printer_factory, low_scheduler, monkeypatch, assignment_exists, provider_enabled
):
    from backend.app.services.spoolman import SpoolmanClient

    printer = await printer_factory()
    _, _, provider = await seed_low(db_session, printer)
    provider.enabled = provider_enabled
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    if assignment_exists:
        db_session.add(SpoolmanSlotAssignment(printer_id=printer.id, ams_id=0, tray_id=0, spoolman_spool_id=42))
    await db_session.commit()
    reads = []

    def inventory_http(request):
        reads.append(request.url.path)
        return httpx.Response(200, json=[])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(inventory_http))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.filament_low_monitor.get_spoolman_client", get_client)
    try:
        scheduler, deliveries = low_scheduler
        await run_alert_pass(scheduler)
        assert reads == []
        assert deliveries == []
    finally:
        await client.close()
