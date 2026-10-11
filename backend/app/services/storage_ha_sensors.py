"""Storage cache and threshold transitions, driven by the shared HA poller."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.location import Location
from backend.app.models.storage_ha_sensor import StorageHASensor
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)


class StorageHASensorManager:
    def __init__(self):
        self._readings = {}
        self._last_alerting: dict[int, bool] = {}

    def forget(self, sensor_id: int):
        self._readings.pop(sensor_id, None)
        self._last_alerting.pop(sensor_id, None)

    def get_reading(self, sensor_id: int):
        return self._readings.get(sensor_id)

    def retain(self, sensors: list[StorageHASensor]):
        for sensor_id in set(self._readings) - {sensor.id for sensor in sensors}:
            self.forget(sensor_id)

    def unavailable(self, sensors: list[StorageHASensor]):
        from backend.app.services.ha_sensor_manager import SensorReading

        for sensor in sensors:
            self._readings[sensor.id] = SensorReading(None, None, False, False)

    async def refresh_one(self, db: AsyncSession, sensor: StorageHASensor):
        from backend.app.services.ha_sensor_manager import ha_sensor_manager
        from backend.app.services.homeassistant import homeassistant_service

        self.forget(sensor.id)
        if not await ha_sensor_manager._configure(db):
            self.unavailable([sensor])
            return
        states = await homeassistant_service.fetch_states([sensor.entity_id])
        await self.apply(db, [sensor], states, notify=False)
        await db.refresh(sensor)

    async def apply(self, db: AsyncSession, sensors: list[StorageHASensor], states: dict, *, notify: bool = True):
        from backend.app.services.ha_sensor_manager import evaluate, persist_sensor_reading

        now = utcnow_naive()
        staged = []
        alerts = []
        for sensor in sensors:
            payload = states.get(sensor.entity_id)
            # Changed units/classes cannot silently reinterpret saved thresholds.
            if isinstance(payload, dict):
                attrs = payload.get("attributes", {})
                if not isinstance(attrs, dict) or (
                    attrs.get("unit_of_measurement", sensor.unit) != sensor.unit
                    or attrs.get("device_class", sensor.device_class) != sensor.device_class
                ):
                    payload = None
            elif payload is not None:
                payload = None
            reading = evaluate(sensor, payload)
            if (
                notify
                and sensor.notify_on_alert
                and reading.reachable
                and reading.alerting
                and self._last_alerting.get(sensor.id) is False
            ):
                alerts.append((sensor, reading))
            sensor.last_checked = now
            persist_sensor_reading(sensor, reading, self._readings.get(sensor.id))
            if reading.reachable:
                sensor.last_read_at = now
            staged.append((sensor.id, reading))

        # A failed transaction must not publish fresh values or consume an edge.
        await db.commit()
        for sensor_id, reading in staged:
            self._readings[sensor_id] = reading
            if reading.reachable:
                self._last_alerting[sensor_id] = reading.alerting
        for sensor, reading in alerts:
            try:
                await send_storage_alert(db, sensor, reading)
            except Exception:
                logger.warning("Failed to send storage sensor alert for id=%s", sensor.id, exc_info=True)


async def send_storage_alert(db: AsyncSession, sensor: StorageHASensor, reading):
    from backend.app.services.ha_sensor_manager import describe_state
    from backend.app.services.notification_service import notification_service

    providers = await notification_service._get_providers_for_event(db, "on_storage_sensor_alert")
    # Printer-scoped providers must never receive unrelated warehouse telemetry.
    providers = [provider for provider in providers if provider.printer_id is None]
    if not providers:
        return
    location = await db.get(Location, sensor.location_id)
    if location is None:
        return
    variables = {"location": location.name, "sensor": sensor.name, "state": describe_state(sensor, reading)}
    title, message = await notification_service._build_message_from_template(db, "storage_sensor_alert", variables)
    await notification_service._send_to_providers(
        providers, title, message, db, "storage_sensor_alert", force_immediate=True, variables=variables
    )


storage_ha_sensor_manager = StorageHASensorManager()
