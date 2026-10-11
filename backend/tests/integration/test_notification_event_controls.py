"""Notification settings must survive the API and reach their real producer."""

import pytest
from sqlalchemy import delete, select

from backend.app.models.notification import NotificationLog, NotificationProvider
from backend.app.services.print_scheduler import PrintScheduler
from backend.tests.integration.test_stock_alert_producer import (
    alert_scheduler,  # noqa: F401
    model_engine,  # noqa: F401
    run_alert_pass,
    seed_stock,
    test_engine,  # noqa: F401
)

ALERT_FIELDS = (
    "on_stock_reorder_alert",
    "on_stock_break_alert",
    "on_storage_sensor_alert",
    "on_ha_sensor_alert",
)


def provider_payload(**overrides):
    return {
        "name": "Configured alerts",
        "provider_type": "ntfy",
        "config": {"server": "http://notify.invalid", "topic": "stock"},
        **overrides,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ALERT_FIELDS)
async def test_alert_toggle_create_read_update_and_persist(async_client, db_session, field):
    created = await async_client.post("/api/v1/notifications/", json=provider_payload(**{field: True}))
    assert created.status_code == 200
    payload = created.json()
    assert payload.get(field) is True
    provider_id = payload["id"]
    provider = await db_session.get(NotificationProvider, provider_id)
    assert getattr(provider, field) is True

    detail = await async_client.get(f"/api/v1/notifications/{provider_id}")
    listing = await async_client.get("/api/v1/notifications/")
    assert detail.status_code == listing.status_code == 200
    assert detail.json()[field] is True
    assert listing.json()[0][field] is True

    # An unrelated PATCH must not reset a subscription.
    renamed = await async_client.patch(f"/api/v1/notifications/{provider_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()[field] is True
    for enabled in (False, True):
        updated = await async_client.patch(f"/api/v1/notifications/{provider_id}", json={field: enabled})
        assert updated.status_code == 200
        assert updated.json()[field] is enabled
        await db_session.refresh(provider)
        assert getattr(provider, field) is enabled
        detail = await async_client.get(f"/api/v1/notifications/{provider_id}")
        assert detail.json()[field] is enabled


@pytest.mark.asyncio
async def test_new_alert_subscriptions_default_off(async_client, db_session):
    response = await async_client.post("/api/v1/notifications/", json=provider_payload())
    assert response.status_code == 200
    provider = await db_session.get(NotificationProvider, response.json()["id"])
    for field in ALERT_FIELDS:
        assert response.json().get(field) is False
        assert getattr(provider, field) is False


@pytest.mark.asyncio
async def test_all_existing_notification_event_controls_survive_roundtrip(async_client, db_session):
    # Exercise the public contract for every existing model event, including
    # default-on lifecycle/queue controls and PrintOps sensor subscriptions.
    enabled = {column.name: True for column in NotificationProvider.__table__.columns if column.name.startswith("on_")}
    created = await async_client.post("/api/v1/notifications/", json=provider_payload(**enabled))
    assert created.status_code == 200
    payload = created.json()
    assert {field: payload.get(field) for field in enabled} == enabled
    provider = await db_session.get(NotificationProvider, payload["id"])
    assert all(getattr(provider, field) is True for field in enabled)

    disabled = dict.fromkeys(enabled, False)
    updated = await async_client.patch(f"/api/v1/notifications/{provider.id}", json=disabled)
    assert updated.status_code == 200
    assert {field: updated.json().get(field) for field in disabled} == disabled
    await db_session.refresh(provider)
    assert all(getattr(provider, field) is False for field in disabled)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "stock", "event"),
    [("on_stock_reorder_alert", 80, "stock_reorder_alert"), ("on_stock_break_alert", 60, "stock_break_alert")],
)
async def test_api_configured_stock_subscription_drives_scheduler_http(
    async_client, db_session, alert_scheduler, field, stock, event
):
    scheduler, deliveries = alert_scheduler
    spool = await seed_stock(db_session, stock=stock)
    await db_session.execute(delete(NotificationProvider))
    await db_session.commit()

    response = await async_client.post("/api/v1/notifications/", json=provider_payload(**{field: True}))
    assert response.status_code == 200
    await run_alert_pass(scheduler)
    logs = list(await db_session.scalars(select(NotificationLog)))
    assert [(log.provider_id, log.event_type, log.success) for log in logs] == [(response.json()["id"], event, True)]
    assert len(deliveries) == 1
    assert deliveries[0].startswith(f"PLA Red|Own|{stock}|")
    await db_session.refresh(spool)
    assert spool.weight_used == 1000 - stock


@pytest.mark.asyncio
async def test_recreated_stock_provider_does_not_inherit_deleted_provider_success(
    async_client, db_session, alert_scheduler
):
    scheduler, deliveries = alert_scheduler
    await seed_stock(db_session)
    old_provider_id = await db_session.scalar(select(NotificationProvider.id))
    await run_alert_pass(scheduler)
    assert len(deliveries) == 1

    deleted = await async_client.delete(f"/api/v1/notifications/{old_provider_id}")
    assert deleted.status_code == 200
    recreated = await async_client.post("/api/v1/notifications/", json=provider_payload(on_stock_reorder_alert=True))
    assert recreated.status_code == 200
    assert recreated.json()["id"] == old_provider_id  # SQLite may reuse the last deleted ID.
    restarted = PrintScheduler()
    try:
        await run_alert_pass(restarted)
        assert len(deliveries) == 2
        await run_alert_pass(restarted)
        assert len(deliveries) == 2
    finally:
        await restarted.close_inventory_alerts()
