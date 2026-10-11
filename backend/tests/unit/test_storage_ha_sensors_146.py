"""Failure isolation, SSRF gating, and cross-database storage metadata."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from backend.app.models.storage_ha_sensor import StorageHASensor
from backend.app.services.ha_sensor_manager import HASensorManager, SensorReading
from backend.app.services.storage_ha_sensors import StorageHASensorManager, send_storage_alert


def sensor():
    return StorageHASensor(
        id=1,
        location_id=1,
        name="Humidity",
        entity_id="sensor.humidity",
        device_class="humidity",
        unit="%",
        alert_above=50,
        notify_on_alert=True,
    )


@pytest.mark.asyncio
async def test_failed_commit_does_not_publish_freshness_or_consume_alert_transition():
    manager = StorageHASensorManager()
    row = sensor()
    manager._last_alerting[row.id] = False
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("DB unavailable")
    with patch("backend.app.services.storage_ha_sensors.send_storage_alert", AsyncMock()) as notify:
        with pytest.raises(RuntimeError):
            await manager.apply(db, [row], {row.entity_id: {"state": "60"}})
        assert manager.get_reading(row.id) is None
        assert manager._last_alerting[row.id] is False
        notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_uses_only_unfiltered_providers_and_storage_variables():
    db = AsyncMock()
    db.get.return_value = MagicMock()
    db.get.return_value.name = "Dry box A"
    global_provider = MagicMock(printer_id=None)
    printer_provider = MagicMock(printer_id=1)
    service = "backend.app.services.notification_service.notification_service"
    with (
        patch(
            f"{service}._get_providers_for_event", AsyncMock(return_value=[global_provider, printer_provider])
        ) as providers,
        patch(f"{service}._build_message_from_template", AsyncMock(return_value=("title", "body"))) as template,
        patch(f"{service}._send_to_providers", AsyncMock()) as send,
    ):
        await send_storage_alert(db, sensor(), SensorReading("60", 60, True, True))
        providers.assert_awaited_once_with(db, "on_storage_sensor_alert")
        template.assert_awaited_once_with(
            db, "storage_sensor_alert", {"location": "Dry box A", "sensor": "Humidity", "state": "60 %"}
        )
        assert send.await_args.args[0] == [global_provider]
        assert send.await_args.args[4] == "storage_sensor_alert"
        assert "printer_id" not in send.await_args.kwargs


@pytest.mark.asyncio
async def test_shared_configure_blocks_unsafe_homeassistant_url():
    values = {"ha_enabled": True, "ha_url": "http://169.254.169.254", "ha_token": "test"}
    with (
        patch("backend.app.api.routes.settings.get_homeassistant_settings", AsyncMock(return_value=values)),
        patch("backend.app.services.ha_sensor_manager.homeassistant_service.configure") as configure,
    ):
        assert await HASensorManager()._configure(AsyncMock()) is False
        configure.assert_not_called()


@pytest.mark.asyncio
async def test_poller_survives_one_failed_pass():
    manager = HASensorManager()
    manager.poll_once = AsyncMock(side_effect=[RuntimeError("temporary DB failure"), None])
    with patch(
        "backend.app.services.ha_sensor_manager.asyncio.sleep",
        AsyncMock(side_effect=[None, None, asyncio.CancelledError()]),
    ):
        await manager._poll_loop()
    assert manager.poll_once.await_count == 2


def test_storage_metadata_is_valid_for_sqlite_and_postgresql():
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        ddl = str(CreateTable(StorageHASensor.__table__).compile(dialect=dialect))
        assert ("DEFAULT 0" if dialect.name == "sqlite" else "DEFAULT false") in ddl
        assert "UNIQUE (location_id, entity_id)" in ddl
        assert "REFERENCES locations (id) ON DELETE CASCADE" in ddl
        assert "last_state VARCHAR(64)" in ddl


@pytest.mark.parametrize("payload", [[], 5, {"state": "NaN"}, {"state": "inf"}])
def test_shared_evaluation_rejects_malformed_and_nonfinite_numeric_states(payload):
    from backend.app.services.ha_sensor_manager import evaluate

    assert not evaluate(sensor(), payload).reachable
