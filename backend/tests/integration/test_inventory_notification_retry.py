"""Real notification fan-out retries only undelivered inventory warnings."""

import httpx
import pytest
from sqlalchemy import select

from backend.app.models.notification import NotificationLog, NotificationProvider
from backend.app.services.notification_service import notification_service
from backend.app.services.print_scheduler import PrintScheduler
from backend.tests.integration.test_filament_low_producer import seed_low
from backend.tests.integration.test_stock_alert_producer import (
    alert_scheduler as alert_scheduler,
    model_engine as model_engine,
    run_alert_pass,
    seed_stock,
    test_engine as test_engine,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["reorder", "break", "low"])
@pytest.mark.parametrize("mixed", [False, True])
async def test_failed_provider_recovers_without_duplicating_successful_fanout(
    db_session, printer_factory, alert_scheduler, monkeypatch, event, mixed
):
    if event == "low":
        printer = await printer_factory(name="Own")
        _, _, failing = await seed_low(db_session, printer)
        flags = {"on_filament_low": True}
    else:
        await seed_stock(db_session, stock=60 if event == "break" else 80)
        failing = await db_session.scalar(select(NotificationProvider))
        flags = {"on_stock_reorder_alert": True, "on_stock_break_alert": True}
    failing.config = '{"server":"http://notify.invalid","topic":"failing"}'
    healthy = None
    if mixed:
        healthy = NotificationProvider(
            name="Healthy", provider_type="ntfy", config='{"server":"http://notify.invalid","topic":"healthy"}', **flags
        )
        db_session.add(healthy)
    await db_session.commit()
    state = {"fail": True, "time": 0}
    requests = []

    def notify_http(request):
        requests.append(request.url.path)
        return httpx.Response(503 if state["fail"] and request.url.path == "/failing" else 200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(notify_http))
    monkeypatch.setattr(notification_service, "_http_client", client)
    monkeypatch.setattr("backend.app.services.stock_alert_monitor.monotonic", lambda: state["time"])
    monkeypatch.setattr("backend.app.services.filament_low_monitor.monotonic", lambda: state["time"])
    scheduler, _ = alert_scheduler
    try:
        await run_alert_pass(scheduler)
        first = list(await db_session.scalars(select(NotificationLog).order_by(NotificationLog.id)))
        assert [(log.provider_id, log.success) for log in first] == [(failing.id, False)] + (
            [(healthy.id, True)] if mixed else []
        )
        state["time"] = 1
        await run_alert_pass(scheduler)
        assert len(requests) == 1 + int(mixed)  # No busy-loop retry.
        state.update(fail=False, time=61)
        await run_alert_pass(scheduler)
        records = list(await db_session.scalars(select(NotificationLog).order_by(NotificationLog.id)))
        assert [(log.provider_id, log.success) for log in records] == [(failing.id, False)] + (
            [(healthy.id, True)] if mixed else []
        ) + [(failing.id, True)]
        assert requests.count("/healthy") == int(mixed)
        state["time"] = 122
        await run_alert_pass(scheduler)
        assert requests.count("/failing") == 2
        if event != "low":
            restarted = PrintScheduler()
            try:
                await run_alert_pass(restarted)
                assert requests.count("/failing") == 2  # Per-provider success survives restart.
            finally:
                await restarted.close_inventory_alerts()
    finally:
        await scheduler.close_inventory_alerts()
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["stock", "low"])
async def test_quiet_hours_skip_is_retried_after_quiet_hours_and_digest_is_retained(
    db_session, printer_factory, alert_scheduler, monkeypatch, event
):
    from backend.app.models.notification import NotificationDigestQueue

    if event == "low":
        printer = await printer_factory()
        _, _, provider = await seed_low(db_session, printer)
    else:
        await seed_stock(db_session)
        provider = await db_session.scalar(select(NotificationProvider))
    provider.quiet_hours_enabled = True
    provider.daily_digest_enabled = True
    provider.daily_digest_time = "09:00"
    await db_session.commit()
    state = {"quiet": True, "time": 0}
    monkeypatch.setattr(notification_service, "_is_in_quiet_hours", lambda _provider: state["quiet"])
    monkeypatch.setattr("backend.app.services.stock_alert_monitor.monotonic", lambda: state["time"])
    monkeypatch.setattr("backend.app.services.filament_low_monitor.monotonic", lambda: state["time"])
    scheduler, deliveries = alert_scheduler
    await run_alert_pass(scheduler)
    assert deliveries == []
    assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1
    state.update(quiet=False, time=61)
    await run_alert_pass(scheduler)
    assert len(deliveries) == 1
    assert (
        len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 1
    )  # Retry is not another digest event.
