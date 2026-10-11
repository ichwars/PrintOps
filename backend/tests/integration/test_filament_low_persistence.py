"""Filament warning delivery and digest history survives monitor restarts."""

import json

import httpx
import pytest
from sqlalchemy import select

from backend.app.models.notification import NotificationDigestQueue, NotificationProvider
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.filament_low_monitor import FilamentLowMonitor
from backend.app.services.notification_service import notification_service
from backend.tests.integration.test_filament_low_producer import (
    low_scheduler as low_scheduler,
    seed_low,
)
from backend.tests.integration.test_stock_alert_producer import (
    alert_scheduler as alert_scheduler,
    logs,
    model_engine as model_engine,
    test_engine as test_engine,
)


@pytest.mark.asyncio
async def test_delivered_low_warning_survives_new_monitor_with_same_database(
    db_session, printer_factory, low_scheduler
):
    printer = await printer_factory(name="Restart")
    await seed_low(db_session, printer)
    _, deliveries = low_scheduler

    await FilamentLowMonitor().tick(db_session)
    await FilamentLowMonitor().tick(db_session)

    assert deliveries == ["Restart|Ext-R|10|Red"]
    assert [(record.event_type, record.success) for record in await logs(db_session)] == [("filament_low", True)]


@pytest.mark.asyncio
async def test_restart_retries_failed_provider_without_repeating_delivered_provider(
    db_session, printer_factory, low_scheduler, monkeypatch
):
    printer = await printer_factory(name="Fan-out")
    _, _, failing = await seed_low(db_session, printer)
    failing.config = '{"server":"http://notify.invalid","topic":"failing"}'
    healthy = NotificationProvider(
        name="Healthy",
        provider_type="ntfy",
        on_filament_low=True,
        config='{"server":"http://notify.invalid","topic":"healthy"}',
    )
    db_session.add(healthy)
    await db_session.commit()
    state = {"fail": True}
    requests = []

    def deliver(request):
        requests.append(request.url.path)
        return httpx.Response(503 if state["fail"] and request.url.path == "/failing" else 200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    monkeypatch.setattr(notification_service, "_http_client", client)
    try:
        await FilamentLowMonitor().tick(db_session)
        await FilamentLowMonitor().tick(db_session)
        state["fail"] = False
        await FilamentLowMonitor().tick(db_session)
        await FilamentLowMonitor().tick(db_session)
        assert requests == ["/failing", "/healthy", "/failing", "/failing"]
        assert [(record.provider_id, record.success) for record in await logs(db_session)] == [
            (failing.id, False),
            (healthy.id, True),
            (failing.id, False),
            (failing.id, True),
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_outcome", ["failed", "quiet"])
async def test_restart_retries_immediate_delivery_without_duplicate_digest(
    db_session, printer_factory, low_scheduler, monkeypatch, initial_outcome
):
    printer = await printer_factory()
    _, _, provider = await seed_low(db_session, printer)
    provider.daily_digest_enabled = True
    provider.daily_digest_time = "09:00"
    await db_session.commit()
    state = {"retry": False}
    requests = []

    def deliver(request):
        requests.append(request.url.path)
        return httpx.Response(200 if state["retry"] else 503, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    monkeypatch.setattr(notification_service, "_http_client", client)
    monkeypatch.setattr(
        notification_service, "_is_in_quiet_hours", lambda _provider: initial_outcome == "quiet" and not state["retry"]
    )
    try:
        await FilamentLowMonitor().tick(db_session)
        await FilamentLowMonitor().tick(db_session)
        assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1
        state["retry"] = True
        await FilamentLowMonitor().tick(db_session)
        await FilamentLowMonitor().tick(db_session)
        assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1
        assert len(requests) == (1 if initial_outcome == "quiet" else 3)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("subscription_change", ["enabled", "on_filament_low", "printer_id"])
async def test_absent_matching_subscription_preserves_delivered_history(
    db_session, printer_factory, low_scheduler, subscription_change
):
    printer = await printer_factory(name="Target")
    other = await printer_factory(name="Other")
    _, _, provider = await seed_low(db_session, printer)
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    original = getattr(provider, subscription_change)
    setattr(provider, subscription_change, other.id if subscription_change == "printer_id" else False)
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    setattr(provider, subscription_change, original)
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == ["Target|Ext-R|10|Red"]


@pytest.mark.asyncio
async def test_new_provider_receives_warning_without_forgetting_disabled_success(
    db_session, printer_factory, low_scheduler
):
    printer = await printer_factory(name="Subscribers")
    _, _, original = await seed_low(db_session, printer)
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    original.enabled = False
    new_provider = NotificationProvider(
        name="New subscriber",
        provider_type="ntfy",
        on_filament_low=True,
        config='{"server":"http://notify.invalid","topic":"new"}',
    )
    db_session.add(new_provider)
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    original.enabled = True
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == ["Subscribers|Ext-R|10|Red", "Subscribers|Ext-R|10|Red"]
    assert [record.provider_id for record in await logs(db_session)] == [original.id, new_provider.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("same_destination", [False, True])
async def test_recreated_provider_with_reused_sqlite_id_does_not_inherit_delivery(
    db_session, printer_factory, low_scheduler, same_destination
):
    printer = await printer_factory(name="Recreated")
    _, _, original = await seed_low(db_session, printer)
    original_id = original.id
    destination = original.config
    original.daily_digest_enabled = True
    original.daily_digest_time = "09:00"
    await db_session.commit()
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    await db_session.delete(original)
    await db_session.commit()
    replacement = NotificationProvider(
        name="Replacement",
        provider_type="ntfy",
        on_filament_low=True,
        config=destination if same_destination else '{"server":"http://notify.invalid","topic":"replacement"}',
        daily_digest_enabled=True,
        daily_digest_time="09:00",
    )
    db_session.add(replacement)
    await db_session.commit()
    assert replacement.id == original_id  # SQLite reuses the removed highest row ID.
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == ["Recreated|Ext-R|10|Red", "Recreated|Ext-R|10|Red"]
    assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1


@pytest.mark.asyncio
async def test_recreated_identical_spool_with_reused_id_starts_new_warning_and_digest(
    db_session, printer_factory, low_scheduler
):
    printer = await printer_factory(name="Replaced")
    original, _, provider = await seed_low(db_session, printer)
    original_id, created_at = original.id, original.created_at
    provider.daily_digest_enabled = True
    provider.daily_digest_time = "09:00"
    await db_session.commit()
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    await db_session.delete(original)
    await db_session.commit()
    replacement = Spool(material="PLA", color_name="Red", label_weight=250, weight_used=225, weight_used_baseline=225)
    db_session.add(replacement)
    await db_session.flush()
    db_session.add(SpoolAssignment(printer_id=printer.id, spool_id=replacement.id, ams_id=255, tray_id=1))
    await db_session.commit()
    assert replacement.id == original_id
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == ["Replaced|Ext-R|10|Red", "Replaced|Ext-R|10|Red"]
    assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 2
    assert replacement.created_at != created_at


@pytest.mark.asyncio
async def test_successful_unassigned_snapshot_rearms_same_spool_after_restart(
    db_session, printer_factory, low_scheduler
):
    printer = await printer_factory(name="Assignment")
    spool, assignment, _ = await seed_low(db_session, printer)
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    await db_session.delete(assignment)
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    db_session.add(SpoolAssignment(printer_id=printer.id, spool_id=spool.id, ams_id=255, tray_id=1))
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == ["Assignment|Ext-R|10|Red", "Assignment|Ext-R|10|Red"]


@pytest.mark.asyncio
async def test_recovery_and_spool_replacement_rearm_after_restart(db_session, printer_factory, low_scheduler):
    printer = await printer_factory(name="Recovery")
    spool, assignment, _ = await seed_low(db_session, printer)
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    spool.weight_used = 100
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    spool.weight_used = 225
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    replacement = Spool(material="PETG", color_name="Blue", label_weight=500, weight_used=475)
    db_session.add(replacement)
    await db_session.flush()
    assignment.spool_id = replacement.id
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assignment.spool_id = spool.id
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assert deliveries == [
        "Recovery|Ext-R|10|Red",
        "Recovery|Ext-R|10|Red",
        "Recovery|Ext-R|5|Blue",
        "Recovery|Ext-R|10|Red",
    ]


@pytest.mark.asyncio
async def test_unusable_weight_is_not_evidence_of_recovery(db_session, printer_factory, low_scheduler):
    printer = await printer_factory()
    spool, _, _ = await seed_low(db_session, printer)
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    spool.label_weight = 0
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    spool.label_weight = 250
    await db_session.commit()
    await FilamentLowMonitor().tick(db_session)
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_spoolman_outage_and_other_inventory_mode_preserve_delivered_history(
    db_session, printer_factory, low_scheduler, monkeypatch
):
    from backend.app.services.spoolman import SpoolmanClient

    printer = await printer_factory(name="Modes")
    await seed_low(db_session, printer)
    mode = Settings(key="spoolman_enabled", value="true")
    db_session.add_all(
        [mode, SpoolmanSlotAssignment(printer_id=printer.id, ams_id=255, tray_id=0, spoolman_spool_id=42)]
    )
    await db_session.commit()
    raw = {
        "id": 42,
        "registered": "2026-10-01T12:00:00+00:00",
        "initial_weight": 250,
        "remaining_weight": 25,
        "used_weight": 225,
        "archived": False,
        "filament": {"material": "PLA", "name": "PLA", "weight": 1000, "color_name": "Red", "vendor": {"name": "Own"}},
    }
    state = {"status": 200}
    inventory = SpoolmanClient("http://inventory.invalid")
    inventory._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(state["status"], json=[raw]))
    )

    async def get_client():
        return inventory

    monkeypatch.setattr("backend.app.services.filament_low_monitor.get_spoolman_client", get_client)
    _, deliveries = low_scheduler
    try:
        await FilamentLowMonitor().tick(db_session)
        state["status"] = 503
        await FilamentLowMonitor().tick(db_session)
        state["status"] = 200
        await FilamentLowMonitor().tick(db_session)
        assert deliveries == ["Modes|Ext-L|10|Red"]
        mode.value = "false"
        await db_session.commit()
        await FilamentLowMonitor().tick(db_session)
        mode.value = "true"
        await db_session.commit()
        await FilamentLowMonitor().tick(db_session)
        assert deliveries == ["Modes|Ext-L|10|Red", "Modes|Ext-R|10|Red"]
        raw["registered"] = "2026-10-02T12:00:00+00:00"
        await FilamentLowMonitor().tick(db_session)
        assert deliveries == ["Modes|Ext-L|10|Red", "Modes|Ext-R|10|Red", "Modes|Ext-L|10|Red"]
    finally:
        await inventory.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["{", "[]", '{"broken": true}', "null"])
async def test_malformed_persisted_state_does_not_block_low_warning(
    db_session, printer_factory, low_scheduler, caplog, stored
):
    printer = await printer_factory()
    await seed_low(db_session, printer)
    db_session.add(Settings(key="filament_low_alert_state", value=stored))
    await db_session.commit()
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    await FilamentLowMonitor().tick(db_session)
    assert len(deliveries) == 1
    assert "Low-filament notification check failed" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered,digest", [("true", "true"), (1, 1), ([], {}), (None, None)])
async def test_persisted_non_boolean_flags_cannot_suppress_delivery_or_digest(
    db_session, printer_factory, low_scheduler, caplog, delivered, digest
):
    printer = await printer_factory()
    spool, _, provider = await seed_low(db_session, printer)
    provider.daily_digest_enabled = True
    provider.daily_digest_time = "09:00"
    key = json.dumps(["internal", printer.id, 255, 1, spool.id])
    state = {
        key: {
            str(provider.id): {
                "identity": provider.created_at.isoformat(),
                "spool_identity": spool.created_at.isoformat(),
                "delivered": delivered,
                "digest": digest,
            }
        }
    }
    db_session.add(Settings(key="filament_low_alert_state", value=json.dumps(state)))
    await db_session.commit()
    _, deliveries = low_scheduler
    await FilamentLowMonitor().tick(db_session)
    await FilamentLowMonitor().tick(db_session)
    assert len(deliveries) == 1
    assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1
    assert "Low-filament notification check failed" not in caplog.text
