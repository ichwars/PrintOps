"""Scheduler -> own forecast -> real notification logs and HTTP boundary."""

from datetime import datetime, timedelta
from itertools import count

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.notification import NotificationLog, NotificationProvider
from backend.app.models.notification_template import NotificationTemplate
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.notification_service import notification_service
from backend.app.services.print_scheduler import PrintScheduler


@pytest.fixture
async def alert_scheduler(test_engine, monkeypatch):
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr("backend.app.services.print_scheduler.async_session", sessions)
    deliveries = []
    clock = count(0, 4000)
    monkeypatch.setattr("backend.app.services.stock_alert_monitor.monotonic", lambda: next(clock))

    def deliver(request):
        deliveries.append(request.content.decode())
        return httpx.Response(200, json={"id": "delivered"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    monkeypatch.setattr(notification_service, "_http_client", client)
    monkeypatch.setattr(notification_service, "_template_cache", {})
    yield PrintScheduler(), deliveries
    await client.aclose()


async def seed_stock(db, *, stock=80, margin=14, lead=7):
    now = datetime.utcnow()
    spool = Spool(
        material="PLA",
        brand="Own",
        color_name="Red",
        label_weight=1000,
        weight_used=1000 - stock,
        created_at=now - timedelta(days=100),
    )
    db.add(spool)
    await db.flush()
    db.add_all(
        [
            NotificationProvider(
                name="Own alerts",
                provider_type="ntfy",
                config='{"server":"http://notify.invalid","topic":"stock"}',
                on_stock_reorder_alert=True,
                on_stock_break_alert=True,
            ),
            Settings(key="forecast_global_lead_time_days", value=str(lead)),
            FilamentSkuSettings(
                material="PLA",
                brand="Own",
                color_name="Red",
                safety_margin_value=margin,
                safety_margin_unit="days",
                lead_time_days=0,
            ),
            *[SpoolUsageHistory(spool_id=spool.id, weight_used=10, created_at=now - timedelta(days=d)) for d in (2, 1)],
            *[
                NotificationTemplate(
                    event_type=event,
                    name=event,
                    title_template=event,
                    body_template="{material}|{brand}|{stock_g}|{rate_g_day}|{days_left}|{lead_time_days}",
                )
                for event in ("stock_reorder_alert", "stock_break_alert")
            ],
        ]
    )
    await db.commit()
    return spool


@pytest.mark.asyncio
@pytest.mark.parametrize("populated_queue", [False, True])
async def test_periodic_queue_pass_produces_stock_alert_with_own_history(db_session, alert_scheduler, populated_queue):
    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session)
    if populated_queue:
        db_session.add(PrintQueueItem(status="pending", manual_start=True))
        await db_session.commit()
    await scheduler.check_queue()
    logs = list((await db_session.scalars(select(NotificationLog))).all())
    assert [(log.event_type, log.message, log.success) for log in logs] == [
        ("stock_reorder_alert", "PLA Red|Own|80|10.0|8|", True)
    ]
    assert deliveries == ["PLA Red|Own|80|10.0|8|"]


async def logs(db):
    return list((await db.scalars(select(NotificationLog).order_by(NotificationLog.id))).all())


@pytest.mark.asyncio
async def test_dedup_survives_restart_escalates_and_rearms_on_recovery(db_session, alert_scheduler):
    scheduler, deliveries = alert_scheduler
    spool = await seed_stock(db_session)
    await scheduler.check_queue()
    await scheduler.check_queue()
    await PrintScheduler().check_queue()
    assert len(deliveries) == 1
    spool.weight_used = 940
    await db_session.commit()
    await scheduler.check_queue()
    assert [log.event_type for log in await logs(db_session)] == ["stock_reorder_alert", "stock_break_alert"]
    spool.weight_used = 100
    await db_session.commit()
    await scheduler.check_queue()
    spool.weight_used = 920
    await db_session.commit()
    await scheduler.check_queue()
    assert [log.event_type for log in await logs(db_session)] == [
        "stock_reorder_alert",
        "stock_break_alert",
        "stock_reorder_alert",
    ]
    await db_session.refresh(spool)
    assert spool.weight_used == 920  # Alerting never adjusts stock or buys supplies.


@pytest.mark.asyncio
async def test_disabled_provider_does_no_external_inventory_work_and_reenable_rearms(
    db_session, alert_scheduler, monkeypatch
):
    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session)
    await scheduler.check_queue()
    provider = await db_session.scalar(select(NotificationProvider))
    provider.enabled = False
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()

    from backend.app.services.spoolman import SpoolmanClient

    reads = []

    def inventory_http(request):
        reads.append(request.url.path)
        return httpx.Response(200, json=[])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(inventory_http))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.stock_alert_monitor.get_spoolman_client", get_client)
    await scheduler.check_queue()
    await db_session.refresh(provider)
    assert provider.last_error is None
    assert reads == []
    await client.close()
    assert len(deliveries) == 1
    provider.enabled = True
    setting = await db_session.scalar(select(Settings).where(Settings.key == "spoolman_enabled"))
    setting.value = "false"
    await db_session.commit()
    await scheduler.check_queue()
    assert len(deliveries) == 2


@pytest.mark.asyncio
async def test_baseline_reset_excludes_old_history_and_snoozing_rearms(db_session, alert_scheduler):
    scheduler, deliveries = alert_scheduler
    spool = await seed_stock(db_session)
    spool.weight_used_baseline = spool.weight_used
    await db_session.commit()
    await scheduler.check_queue()
    assert deliveries == []
    spool.weight_used_baseline = 0
    sku = await db_session.scalar(select(FilamentSkuSettings))
    sku.alerts_snoozed = True
    await db_session.commit()
    await scheduler.check_queue()
    assert deliveries == []
    sku.alerts_snoozed = False
    await db_session.commit()
    await scheduler.check_queue()
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_preferred_procurement_offer_on_legacy_alias_sets_actual_lead(db_session, alert_scheduler):
    from backend.app.models.procurement import ProcurementOffer, Supplier
    from backend.app.services.filament_sku_identity import backfill_material_numbers

    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session, stock=80, margin=0, lead=0)
    duplicate = FilamentSkuSettings(material="PLA", brand="Own", color_name="Red")
    supplier = Supplier(name="Preferred", name_key="preferred")
    db_session.add_all([duplicate, supplier])
    await db_session.flush()
    db_session.add(
        ProcurementOffer(
            supplier_id=supplier.id,
            filament_sku_settings_id=duplicate.id,
            resource_key=f"filament:{duplicate.id}",
            lead_time_days=12,
            is_preferred=True,
        )
    )
    await db_session.commit()
    await backfill_material_numbers(db_session)
    await db_session.commit()
    await scheduler.check_queue()
    assert [(log.event_type, log.message) for log in await logs(db_session)] == [
        ("stock_break_alert", "PLA Red|Own|80|10.0|8|12")
    ]


@pytest.mark.asyncio
async def test_forecast_uses_free_stock_from_real_order_reservation(async_client, db_session, alert_scheduler):
    from backend.app.models.stock_reservation import StockReservationAllocation
    from backend.tests.integration.test_order_reservation_lifecycle import _accepted_order

    order, _, reserved_spool = await _accepted_order(async_client, db_session)
    await seed_stock(db_session)
    # Keep the original PLA group healthy; alert only on the order's reserved PETG.
    pla = await db_session.scalar(select(Spool).where(Spool.material == "PLA"))
    pla.weight_used = 0
    allocation = await db_session.scalar(
        select(StockReservationAllocation).where(StockReservationAllocation.spool_id == reserved_spool.id)
    )
    reserved_spool.label_weight = 1000
    reserved_spool.weight_used = 1000 - float(allocation.allocated_quantity) - 80
    reserved_spool.brand = "Own"
    reserved_spool.created_at = datetime.utcnow() - timedelta(days=100)
    db_session.add(FilamentSkuSettings(material="PETG", brand="Own", safety_margin_value=14))
    for day in (2, 1):
        db_session.add(
            SpoolUsageHistory(
                spool_id=reserved_spool.id, weight_used=10, created_at=datetime.utcnow() - timedelta(days=day)
            )
        )
    await db_session.commit()
    scheduler, deliveries = alert_scheduler
    await scheduler.check_queue()
    petg = [log for log in await logs(db_session) if log.message.startswith("PETG|")]
    assert [(log.event_type, log.message) for log in petg] == [("stock_reorder_alert", "PETG|Own|80|10.0|8|")]
    await db_session.refresh(allocation)
    assert float(allocation.consumed_quantity) == 0
    assert order["reservations"]  # No reservation/procurement writes belong to the monitor.


@pytest.mark.asyncio
async def test_new_break_subscription_is_not_suppressed_by_reorder_fallback(db_session, alert_scheduler):
    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session, stock=60)
    provider = await db_session.scalar(select(NotificationProvider))
    provider.on_stock_break_alert = False
    await db_session.commit()
    await scheduler.check_queue()
    assert [log.event_type for log in await logs(db_session)] == ["stock_reorder_alert"]
    provider.on_stock_break_alert = True
    await db_session.commit()
    await scheduler.check_queue()
    assert [log.event_type for log in await logs(db_session)] == ["stock_reorder_alert", "stock_break_alert"]


@pytest.mark.asyncio
async def test_spoolman_own_baseline_outage_and_recovery_without_local_history_collision(
    db_session, alert_scheduler, monkeypatch
):
    import json

    from backend.app.services.spoolman import SpoolmanClient

    scheduler, deliveries = alert_scheduler
    local_spool = await seed_stock(db_session)
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()
    raw = {
        "id": local_spool.id,
        "registered": (datetime.utcnow() - timedelta(days=10)).isoformat(),
        "initial_weight": 250,
        "remaining_weight": 50,
        "used_weight": 200,
        "archived": False,
        "extra": {"bambu_weight_used_baseline": json.dumps("150")},
        "filament": {
            "id": 7,
            "material": "PLA",
            "name": "PLA Matte",
            "weight": 1000,
            "color_name": "Red",
            "vendor": {"name": "Own"},
        },
    }
    status = {"code": 200}
    reads = []

    def inventory_http(request):
        reads.append(request.url.path)
        return httpx.Response(status["code"], json=[raw])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(inventory_http))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.stock_alert_monitor.get_spoolman_client", get_client)
    try:
        await scheduler.check_queue()
        assert [(log.event_type, log.message) for log in await logs(db_session)] == [
            ("stock_reorder_alert", "PLA Matte Red|Own|50|5.0|10|")
        ]
        status["code"] = 503
        await scheduler.check_queue()
        status["code"] = 200
        await scheduler.check_queue()
        assert len(deliveries) == 1
        raw["remaining_weight"] = 250
        await scheduler.check_queue()
        raw["remaining_weight"] = 50
        await scheduler.check_queue()
        assert len(deliveries) == 2
        assert reads
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("break_subscriber_also_wants_reorder", [False, True])
async def test_break_reaches_separate_reorder_subscribers_without_double_delivery(
    db_session, alert_scheduler, break_subscriber_also_wants_reorder
):
    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session, stock=60)
    original = await db_session.scalar(select(NotificationProvider))
    original.on_stock_reorder_alert = break_subscriber_also_wants_reorder
    original.on_stock_break_alert = True
    reorder = NotificationProvider(
        name="Reorder only",
        provider_type="ntfy",
        config='{"server":"http://notify.invalid","topic":"reorder"}',
        on_stock_reorder_alert=True,
        on_stock_break_alert=False,
    )
    db_session.add(reorder)
    await db_session.commit()
    await scheduler.check_queue()
    assert sorted((log.provider_id, log.event_type) for log in await logs(db_session)) == [
        (original.id, "stock_break_alert"),
        (reorder.id, "stock_reorder_alert"),
    ]
    assert len(deliveries) == 2
    await scheduler.check_queue()
    assert len(deliveries) == 2
