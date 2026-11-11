import logging
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text

from backend.app.models.notification import NotificationProvider
from backend.app.models.settings import Settings
from backend.app.models.smart_plug import SmartPlug
from backend.app.services.homeassistant import homeassistant_service
from backend.app.services.mqtt_relay import mqtt_relay
from backend.app.services.notification_service import notification_service
from backend.app.services.obico_detection import obico_detection_service
from backend.app.services.rest_smart_plug import rest_smart_plug_service
from backend.app.services.secret_fields import SECRET_PLACEHOLDER
from backend.app.services.tasmota import tasmota_service

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_settings_mask_credentials_and_reject_reusing_them_for_another_destination(
    async_client, db_session, monkeypatch
):
    monkeypatch.delenv("HA_TOKEN", raising=False)
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.setattr(mqtt_relay, "configure", AsyncMock())
    endpoint = "/api/v1/settings/"
    original = {"mqtt_broker": "mqtt.local", "mqtt_password": "fixture-mqtt", "prometheus_token": "fixture-metrics"}
    saved = await async_client.put(endpoint, json=original)
    assert saved.status_code == 200
    for response in (saved, await async_client.get(endpoint)):
        assert response.json()["mqtt_password"] == response.json()["prometheus_token"] == SECRET_PLACEHOLDER
        assert "fixture-" not in response.text

    for secret in ({}, {"mqtt_password": SECRET_PLACEHOLDER}):
        changed = await async_client.put(endpoint, json={"mqtt_broker": "elsewhere.local", **secret})
        assert changed.status_code == 400

    kept = await async_client.put(endpoint, json={"mqtt_broker": "mqtt.local", "mqtt_password": SECRET_PLACEHOLDER})
    assert kept.status_code == 200
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "mqtt_password")) == "fixture-mqtt"

    cleared = await async_client.put(endpoint, json={"mqtt_broker": "new.local", "mqtt_password": None})
    assert cleared.status_code == 200
    assert cleared.json()["mqtt_password"] == ""
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "mqtt_broker")) == "new.local"


async def test_environment_ha_and_stored_obico_tokens_are_bound_to_the_configured_url(
    async_client, db_session, monkeypatch
):
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.setenv("HA_TOKEN", "fixture-env-ha")
    db_session.add(Settings(key="ha_url", value="http://ha.local"))
    await db_session.commit()
    ha_test = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(homeassistant_service, "test_connection", ha_test)
    obico_test = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(obico_detection_service, "test_connection", obico_test)
    monkeypatch.setattr(
        obico_detection_service,
        "_load_settings",
        AsyncMock(return_value={"ml_url": "http://ml.local", "ml_token": "fixture-ml"}),
    )

    change = await async_client.put(
        "/api/v1/settings/", json={"ha_url": "http://elsewhere.local", "ha_token": SECRET_PLACEHOLDER}
    )
    assert change.status_code == 400
    for path, url, expected_token, client in (
        ("/api/v1/smart-plugs/ha/test-connection", "http://ha.local", "fixture-env-ha", ha_test),
        ("/api/v1/obico/test-connection", "http://ml.local", "fixture-ml", obico_test),
    ):
        refused = await async_client.post(path, json={"url": "http://elsewhere.local", "token": SECRET_PLACEHOLDER})
        assert refused.status_code == 400
        client.assert_not_awaited()
        accepted = await async_client.post(path, json={"url": url, "token": SECRET_PLACEHOLDER})
        assert accepted.status_code == 200
        client.assert_awaited_once_with(url, expected_token)


async def test_smtp_password_stays_bound_and_is_cleared_when_auth_is_disabled_during_a_move(async_client, db_session):
    endpoint = "/api/v1/auth/smtp"
    smtp = {
        "smtp_host": "mail.local",
        "smtp_port": 587,
        "smtp_from_email": "sender@example.test",
        "smtp_auth_enabled": True,
        "smtp_password": "fixture-smtp",
    }
    assert (await async_client.post(endpoint, json=smtp)).status_code == 200
    assert (await async_client.get(endpoint)).json()["smtp_password"] is None
    moved = {**smtp, "smtp_host": "new-mail.local", "smtp_password": SECRET_PLACEHOLDER}
    assert (await async_client.post(endpoint, json=moved)).status_code == 400
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "smtp_password")) == "fixture-smtp"

    moved.update(smtp_auth_enabled=False, smtp_password="")
    assert (await async_client.post(endpoint, json=moved)).status_code == 200
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "smtp_password")) == ""


async def test_rest_and_tasmota_test_only_use_saved_secrets_at_the_original_destinations(
    async_client, smart_plug_factory, db_session, monkeypatch
):
    rest = await smart_plug_factory(
        plug_type="rest", rest_on_url="http://plug.local/on", rest_headers='{"Authorization":"fixture-header"}'
    )
    tasmota = await smart_plug_factory(ip_address="192.168.1.11", password="fixture-plug")
    await db_session.commit()
    rest_test = AsyncMock(return_value={"success": True, "error": None})
    tasmota_test = AsyncMock(return_value={"success": True, "state": "ON"})
    monkeypatch.setattr(rest_smart_plug_service, "test_connection", rest_test)
    monkeypatch.setattr(tasmota_service, "test_connection", tasmota_test)

    prefix = "/api/v1/smart-plugs"
    assert (await async_client.get(f"{prefix}/{rest.id}")).json()["rest_headers"] == SECRET_PLACEHOLDER
    assert (await async_client.get(f"{prefix}/{tasmota.id}")).json()["password"] == SECRET_PLACEHOLDER
    edit = await async_client.patch(f"{prefix}/{rest.id}", json={"rest_on_url": "http://elsewhere.local/on"})
    assert edit.status_code == 400
    for path, payload, field, wrong, client in (
        (
            "/rest/test-connection",
            {"plug_id": rest.id, "url": rest.rest_on_url, "headers": SECRET_PLACEHOLDER},
            "url",
            "http://other.local/on",
            rest_test,
        ),
        (
            "/test-connection",
            {"plug_id": tasmota.id, "ip_address": tasmota.ip_address, "password": SECRET_PLACEHOLDER},
            "ip_address",
            "192.168.1.12",
            tasmota_test,
        ),
    ):
        refused = await async_client.post(prefix + path, json={**payload, field: wrong})
        assert refused.status_code == 400
        client.assert_not_awaited()
        assert (await async_client.post(prefix + path, json=payload)).status_code == 200
    rest_test.assert_awaited_once_with(rest.rest_on_url, "GET", rest.rest_headers)
    tasmota_test.assert_awaited_once_with(tasmota.ip_address, None, tasmota.password)
    persisted = await db_session.get(SmartPlug, rest.id, populate_existing=True)
    assert persisted.rest_on_url == "http://plug.local/on"


async def test_notification_credentials_round_trip_and_test_only_at_the_original_destination(
    async_client, db_session, monkeypatch
):
    prefix = "/api/v1/notifications"
    config = {"server": "https://notify.local", "topic": "printer", "auth_token": "fixture-notification"}
    create = await async_client.post(f"{prefix}/", json={"name": "Ntfy", "provider_type": "ntfy", "config": config})
    assert create.status_code == 200
    saved = create.json()
    assert saved["config"]["auth_token"] == SECRET_PLACEHOLDER
    assert "fixture-" not in create.text
    provider_id = saved["id"]
    test = AsyncMock(return_value=(True, "ok"))
    monkeypatch.setattr(notification_service, "send_test_notification", test)

    edited = await async_client.patch(f"{prefix}/{provider_id}", json={"config": saved["config"], "name": "New name"})
    assert edited.status_code == 200
    moved = {**saved["config"], "server": "https://elsewhere.local"}
    assert (await async_client.patch(f"{prefix}/{provider_id}", json={"config": moved})).status_code == 400
    assert (await async_client.patch(f"{prefix}/{provider_id}", json={"provider_type": "bark"})).status_code == 400
    body = {"provider_type": "ntfy", "config": saved["config"]}
    assert (await async_client.post(f"{prefix}/test-config", json=body)).status_code == 400
    assert (
        await async_client.post(f"{prefix}/test-config", json={**body, "provider_id": provider_id, "config": moved})
    ).status_code == 400
    test.assert_not_awaited()
    accepted = await async_client.post(f"{prefix}/test-config", json={**body, "provider_id": provider_id})
    assert accepted.status_code == 200
    assert test.await_args.args[:2] == ("ntfy", config)
    provider = await db_session.get(NotificationProvider, provider_id)
    assert "fixture-notification" in provider.config


async def test_debug_sql_hides_credential_parameters(async_client, caplog, monkeypatch):
    from backend.app.core import database

    monkeypatch.setattr(database.settings, "debug", True)
    engine = database._create_engine()
    try:
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine"):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT :value"), {"value": "fixture-secret-parameter"})
        assert "SQL parameters hidden" in caplog.text
        assert "fixture-secret-parameter" not in caplog.text
        assert logging.getLogger("aiosqlite").level == logging.WARNING
    finally:
        await engine.dispose()
